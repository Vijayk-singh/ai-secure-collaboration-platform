import asyncio
import json
import logging
import time
from typing import Callable, Dict, Optional
import redis.asyncio as redis
from app.core.redis import redis_service

logger = logging.getLogger(__name__)

# Dictionary holding registered task handler functions
handlers: Dict[str, Callable] = {}

def task_handler(name: str):
    """
    Decorator registering worker task handlers.
    """
    def decorator(func: Callable):
        handlers[name] = func
        return func
    return decorator

# ---------------------------------------------------------
# REGISTER CORE TASK HANDLERS
# ---------------------------------------------------------
@task_handler("send_email_notification")
async def send_email_notification(email: str, subject: str, body: str) -> None:
    """
    SMTP Mock task simulating secure email dispatching.
    """
    logger.info(f"--- SMTP MOCK: OUTBOX DISPATCH ---")
    logger.info(f"To:      {email}")
    logger.info(f"Subject: {subject}")
    logger.info(f"Body Preview:\n{body}")
    logger.info(f"----------------------------------")
    
    # Simulate network latency
    await asyncio.sleep(0.5)
    logger.info(f"SMTP MOCK: Email successfully delivered to {email}.")

@task_handler("mock_failed_task")
async def mock_failed_task() -> None:
    """
    Task designed to fail consistently, used to verify retries and DLQ promotions.
    """
    logger.info("Mock Task: Commencing execution...")
    await asyncio.sleep(0.2)
    logger.warning("Mock Task: Failure simulated!")
    raise RuntimeError("Simulated connection timeout during task execution.")

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    """
    Splits text recursively based on paragraph, sentence, and word boundaries
    to preserve logical semantic blocks inside chunks.
    """
    if not text:
        return []
    
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        # Heuristic boundary scanner within the overlap bounds
        if end < len(text):
            boundary = -1
            for separator in [". ", "\n\n", "\n", " "]:
                pos = text.rfind(separator, start + chunk_size - overlap, end)
                if pos != -1:
                    boundary = pos + len(separator)
                    break
            if boundary != -1:
                end = boundary
        
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = end - overlap
        if start >= end:
            start = end
            
    return [c for c in chunks if c]

@task_handler("generate_note_embeddings")
async def generate_note_embeddings(note_id: int) -> None:
    """
    Asynchronously extracts, chunks, and vectorizes markdown note documents,
    storing high-performance search indices in pgvector chunks table.
    """
    from app.core.database import async_session_maker
    from app.models.note import Note, NoteChunk
    from app.services.ai import AIService
    from sqlalchemy import select, delete

    logger.info(f"AI Worker: Commencing embedding generation for Note ID: {note_id}")

    async with async_session_maker() as db:
        # 1. Fetch note entity
        result = await db.execute(select(Note).filter(Note.id == note_id))
        note = result.scalars().first()
        if not note:
            logger.warning(f"AI Worker: Note {note_id} not found in database. Skipping vectorization.")
            return

        title = note.title or "Untitled"
        content = note.content or ""

        # 2. Extract semantic chunk slices
        chunks = chunk_text(content, chunk_size=500, overlap=100)
        if not chunks:
            chunks = ["(This document has no content body)"]

        # 3. Contact vector space AI model (Google Gemini or deterministic local engine)
        ai_service = AIService()
        chunk_objects = []
        
        for idx, chunk_body in enumerate(chunks):
            # Prepend parent structural context headers to avoid standalone retrieval ambiguity
            contextualized_chunk = f"Note Title: {title}\nContent:\n{chunk_body}"
            
            vector = await ai_service.generate_embedding(contextualized_chunk)
            
            chunk_objects.append({
                "note_id": note_id,
                "chunk_index": idx,
                "content": contextualized_chunk,
                "embedding": vector
            })

        # 4. Atomic Flush: Wipes stale chunks and bulk inserts fresh semantic indexes
        try:
            # Delete any existing chunks for this note
            await db.execute(delete(NoteChunk).filter(NoteChunk.note_id == note_id))
            
            for chunk_data in chunk_objects:
                new_chunk = NoteChunk(**chunk_data)
                db.add(new_chunk)
            
            await db.commit()
            logger.info(f"AI Worker: Note {note_id} successfully vectorized with {len(chunk_objects)} chunks.")
        except Exception as err:
            await db.rollback()
            logger.error(f"AI Worker: Database atomic flush failed for Note {note_id}: {err}")
            raise err

# ---------------------------------------------------------
# ASYNC WORKER IMPLEMENTATION
# ---------------------------------------------------------
class AsyncWorker:
    """
    Asynchronous queue worker block-popping tasks from Redis,
    managing idempotency keys, execution retries, and DLQ promotions.
    """
    def __init__(self, cache: redis.Redis) -> None:
        self.cache = cache
        self.running = False
        self.task: Optional[asyncio.Task] = None

    def start(self) -> None:
        """
        Spawns the background asyncio worker loop.
        """
        self.running = True
        self.task = asyncio.create_task(self._worker_loop())
        logger.info("Async Queue Worker started.")

    async def stop(self) -> None:
        """
        Terminates the background worker loop.
        """
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            logger.info("Async Queue Worker stopped.")

    async def _worker_loop(self) -> None:
        """
        Main worker execution loop popping tasks via BRPOP.
        """
        while self.running:
            try:
                # Block pop from default queue with a 3-second timeout
                res = await self.cache.brpop("queue:default", timeout=3)
                if not res:
                    continue  # Timeout occurred, poll again

                # brpop returns a tuple: (queue_name, payload_str)
                _, payload_str = res
                await self._process_task(payload_str)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Async Worker loop caught unhandled error: {e}")
                await asyncio.sleep(1)

    async def _process_task(self, payload_str: str) -> None:
        """
        Processes a single task payload, enforcing idempotency and retries.
        """
        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError as e:
            logger.error(f"Worker skipped corrupted task payload: {e}")
            return

        task_id = payload.get("task_id")
        name = payload.get("name")
        args = payload.get("args", [])
        kwargs = payload.get("kwargs", {})
        retry_count = payload.get("retry_count", 0)
        max_retries = payload.get("max_retries", 3)

        if not task_id or not name:
            logger.error("Worker skipped invalid task format.")
            return

        # 1. ENFORCE IDEMPOTENCY GUARD
        # Check if task is already processed or currently active
        idempotency_key = f"task:processed:{task_id}"
        lock_status = await self.cache.set(idempotency_key, "in_progress", ex=3600, nx=True)
        
        if not lock_status:
            state = await self.cache.get(idempotency_key)
            if state == "success":
                logger.info(f"Idempotency Guard: Task '{name}' (ID: {task_id}) already executed. Skipped.")
                return
            elif state == "in_progress":
                logger.warning(f"Idempotency Guard: Task '{name}' (ID: {task_id}) is currently in-progress. Skipped duplicate.")
                return

        # 2. RUN REGISTERED TASK HANDLER
        handler = handlers.get(name)
        if not handler:
            logger.error(f"Worker Task Error: No handler registered for task '{name}'. Shunting to DLQ.")
            await self._promote_to_dlq(payload, "No handler registered.")
            return

        logger.info(f"Worker: Starting execution of task '{name}' (ID: {task_id}, Attempt: {retry_count + 1}).")
        
        try:
            # Execute async handler
            await handler(*args, **kwargs)
            
            # Task succeeded: update idempotency status
            await self.cache.set(idempotency_key, "success", ex=86400)  # Persist success record for 24h
            logger.info(f"Worker: Task '{name}' (ID: {task_id}) completed successfully.")
            
        except Exception as execution_err:
            logger.error(f"Worker: Task '{name}' (ID: {task_id}) failed: {execution_err}")
            
            # 3. ATOMIC RETRY HANDLING & EXPONENTIAL BACKOFF
            if retry_count < max_retries:
                # Calculate backoff delay: 2, 4, 8, 16 seconds...
                backoff_delay = 2 ** retry_count
                payload["retry_count"] += 1
                
                # Re-package and enqueue to delayed sorted set
                retry_payload_str = json.dumps(payload)
                target_time = time.time() + backoff_delay
                
                # Delete in-progress lock so retry can run later
                await self.cache.delete(idempotency_key)
                
                await self.cache.zadd("queue:delayed", {retry_payload_str: target_time})
                logger.info(
                    f"Worker: Scheduled retry for task '{name}' (ID: {task_id}, "
                    f"Attempt: {payload['retry_count'] + 1}) in {backoff_delay}s."
                )
            else:
                # 4. RETRIES EXHAUSTED: PROMOTE TO DEAD-LETTER QUEUE
                await self._promote_to_dlq(payload, str(execution_err))
                await self.cache.set(idempotency_key, "failed", ex=86400)

    async def _promote_to_dlq(self, payload: dict, error_msg: str) -> None:
        """
        Shunts a permanently failed task to the dead-letter queue.
        """
        task_id = payload.get("task_id")
        name = payload.get("name")
        
        payload["dlq_timestamp"] = time.time()
        payload["dlq_reason"] = error_msg
        
        dlq_str = json.dumps(payload)
        await self.cache.lpush("queue:dlq", dlq_str)
        logger.error(f"Worker FAILURE: Task '{name}' (ID: {task_id}) exhausted all retries. Promoted to DLQ.")
