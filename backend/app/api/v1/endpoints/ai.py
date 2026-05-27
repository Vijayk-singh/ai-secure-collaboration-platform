import logging
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Tuple

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.note import Note, NoteChunk
from app.models.chat import ChatRoom, ChatMessage
from app.repositories.workspace import WorkspaceMemberRepository
from app.repositories.chat import ChatRoomRepository, ChatMessageRepository
from app.schemas.ai import SemanticSearchResponse, SemanticSearchMatch, RAGRequest, RAGResponse, ChatSummaryRequest, ChatSummaryResponse
from app.services.ai import AIService

logger = logging.getLogger(__name__)
router = APIRouter()

async def verify_workspace_membership(
    workspace_id: int,
    user_id: int,
    db: AsyncSession
) -> None:
    """
    Helper guarding workspace information boundaries.
    """
    member_repo = WorkspaceMemberRepository(db)
    membership = await member_repo.get_by_workspace_and_user(workspace_id, user_id)
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: You must be a member of this workspace to access its AI context."
        )

@router.get("/search", response_model=SemanticSearchResponse)
async def semantic_search(
    workspace_id: int = Query(..., description="ID of the workspace note catalog to search inside"),
    q: str = Query(..., min_length=2, description="Natural language search query"),
    limit: int = Query(3, ge=1, le=10, description="Maximum matching chunks to return"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Semantic Search: Vectorizes user search query, runs high-performance
    PostgreSQL pgvector cosine similarity scans, and scopes results strictly
    inside the active workspace boundaries.
    """
    # 1. Enforce RBAC Workspace boundary check
    await verify_workspace_membership(workspace_id, current_user.id, db)

    # 2. Vectorize Search Query
    ai_service = AIService()
    query_vector = await ai_service.generate_embedding(q)

    # 3. Execute pgvector Cosine Distance Query
    # <=> computes Cosine Distance. Cosine Similarity is (1 - Cosine Distance)
    distance_expr = NoteChunk.embedding.op("<=>")(query_vector)
    stmt = (
        select(NoteChunk, Note.title, distance_expr.label("distance"))
        .join(Note, Note.id == NoteChunk.note_id)
        .filter(Note.workspace_id == workspace_id)
        .order_by(distance_expr)
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()

    # 4. Format Results
    matches = []
    for chunk, note_title, distance in rows:
        # Distance ranges from 0.0 (identical) to 2.0 (orthogonal/opposite)
        score = 1.0 - float(distance or 0.0)
        matches.append({
            "note_id": chunk.note_id,
            "note_title": note_title,
            "chunk_index": chunk.chunk_index,
            "content": chunk.content,
            "score": max(score, -1.0)  # Bound score cleanly
        })

    return {
        "query": q,
        "results": matches
    }

@router.post("/rag", response_model=RAGResponse)
async def retrieval_augmented_generation(
    payload: RAGRequest,
    workspace_id: int = Query(..., description="Workspace catalog to context-audit"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    RAG Pipeline: Executes semantic search to collect context note snippets,
    compiles context into a structured generative prompt, invokes Gemini
    completions, and returns citations alongside the generative response.
    """
    # 1. Workspace membership gate
    await verify_workspace_membership(workspace_id, current_user.id, db)

    # 2. Gather Context via Semantic Search (retrieve top 3 relevant chunks)
    search_results = await semantic_search(
        workspace_id=workspace_id,
        q=payload.query,
        limit=3,
        current_user=current_user,
        db=db
    )
    
    matches = search_results["results"]

    # 3. Assemble Generative Prompt Injection
    context_text = ""
    for idx, match in enumerate(matches):
        context_text += f"\n[CHUNK {idx+1}] (Source Note: '{match['note_title']}', ID: {match['note_id']})\n{match['content']}\n"

    system_instruction = (
        "You are a highly secure, intelligent assistant. "
        "Answer the user's question using ONLY the provided workspace notes context. "
        "Inject explicit numbered citations matching the source note titles when stating facts. "
        "If the context contains no relevant details to answer, state that clearly."
    )
    
    prompt = (
        f"Context Snippets:\n{context_text if context_text else 'No matching notes found.'}\n\n"
        f"User Question:\n{payload.query}\n\n"
        f"Answer the user's question clearly with markdown formatting."
    )

    # 4. Generate AI Completion
    ai_service = AIService()
    completion = await ai_service.generate_completion(prompt, system_instruction=system_instruction)

    return {
        "query": payload.query,
        "answer": completion,
        "sources": matches
    }

@router.post("/summarize-chat", response_model=ChatSummaryResponse)
async def summarize_chat(
    payload: ChatSummaryRequest,
    room_id: int = Query(..., description="ID of the chat room to summarize"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Chat Summarization: Fetches recent room transcript history, compiles them,
    and requests a structured, quick-read digest bulleted summary.
    """
    # 1. Fetch Chat Room and verify access boundary
    room_repo = ChatRoomRepository(db)
    room = await room_repo.get(room_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat room not found."
        )

    await verify_workspace_membership(room.workspace_id, current_user.id, db)

    # 2. Retrieve Recent Message History
    message_repo = ChatMessageRepository(db)
    messages = await message_repo.get_room_history(room_id, limit=payload.limit)
    if not messages:
        return {
            "room_id": room_id,
            "summary": "### Empty Room Logs\n\nNo message logs are recorded in this chat room yet. Go write some messages first!",
            "message_count": 0
        }

    # 3. Format Transcript
    # Reverse messages to match chronological read order
    chronological_msgs = list(reversed(messages))
    transcript_lines = []
    for msg in chronological_msgs:
        author = msg.user.full_name if msg.user else f"User {msg.user_id}"
        transcript_lines.append(f"[{author}]: {msg.content}")

    transcript_text = "\n".join(transcript_lines)

    # 4. Request Summary Completion
    system_instruction = (
        "You are an expert workspace intelligence agent. "
        "Provide a concise, professional markdown bulleted summary digest of the chat room transcript. "
        "Highlight participants, central topics discussed, and action items if any exist."
    )
    
    prompt = (
        f"Chat Transcript:\n{transcript_text}\n\n"
        f"Summarize the discussions and decisions made."
    )

    ai_service = AIService()
    summary = await ai_service.generate_completion(prompt, system_instruction=system_instruction)

    return {
        "room_id": room_id,
        "summary": summary,
        "message_count": len(chronological_msgs)
    }
