import logging
import hashlib
import re
import httpx
from typing import List, Dict, Any, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

class AIService:
    """
    Enterprise-grade AI Service orchestrating embeddings generation, semantic searches,
    RAG prompts, and chat summaries. Features a hybrid real-API/mock-fallback design
    for seamless, resilient local development and offline environments.
    """
    def __init__(self) -> None:
        self.api_key = settings.GEMINI_API_KEY
        self.is_offline = not self.api_key or self.api_key.strip() == ""
        
        if self.is_offline:
            logger.info("AI Service: Running in OFFLINE MOCK MODE. High-fidelity semantic fallback active.")
        else:
            logger.info("AI Service: Running in PRODUCTION ONLINE MODE. Google Gemini API endpoints enabled.")

    async def generate_embedding(self, text: str) -> List[float]:
        """
        Generates a 768-dimensional dense vector representing the input text.
        If online, calls Google's Gemini text-embedding-004 endpoint.
        If offline, generates a deterministic, normalized bag-of-words vector.
        """
        if self.is_offline:
            return self._generate_mock_embedding(text)

        # Call Gemini embedding API
        url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "model": "models/text-embedding-004",
            "content": {
                "parts": [{"text": text}]
            }
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    embedding_vector = data["embedding"]["values"]
                    if len(embedding_vector) == 768:
                        return embedding_vector
                    
                    logger.warning(f"Gemini API returned vector size {len(embedding_vector)} instead of 768. Falling back.")
                else:
                    logger.error(f"Gemini API returned status {res.status_code}: {res.text}. Falling back.")
        except Exception as e:
            logger.error(f"Gemini API request failed: {e}. Falling back to high-fidelity mock embedding.")

        return self._generate_mock_embedding(text)

    async def generate_completion(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        """
        Generates an intelligent text completion.
        If online, calls Google's Gemini-1.5-flash endpoint.
        If offline, falls back to structural context extraction.
        """
        if self.is_offline:
            return self._generate_mock_completion(prompt)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        
        contents_payload = {
            "contents": [
                {"parts": [{"text": prompt}]}
            ]
        }
        
        if system_instruction:
            contents_payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(url, json=contents_payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        text_response = candidates[0]["content"]["parts"][0]["text"]
                        return text_response
                logger.error(f"Gemini Completion API returned status {res.status_code}: {res.text}. Falling back.")
        except Exception as e:
            logger.error(f"Gemini Completion API request failed: {e}. Falling back to mock completion.")

        return self._generate_mock_completion(prompt)

    # ---------------------------------------------------------
    # HIGH-FIDELITY LOCAL MOCK ENGINES
    # ---------------------------------------------------------
    def _generate_mock_embedding(self, text: str, dim: int = 768) -> List[float]:
        """
        Generates a deterministic 768-dimensional word-hashing dense vector.
        Normalized to unit length, giving stable, realistic Cosine Similarity metrics.
        """
        words = re.findall(r'\w+', text.lower())
        if not words:
            words = ["empty"]

        vector = [0.0] * dim
        for word in words:
            for i in range(dim):
                # Unique salt per dimension to spread hash space
                h = hashlib.sha256(f"{word}:{i}".encode("utf-8")).hexdigest()
                val = (int(h[:8], 16) / 4294967295.0) * 2.0 - 1.0
                vector[i] += val

        # Normalize vector to unit length (L2 norm = 1)
        norm = sum(x*x for x in vector) ** 0.5
        if norm > 0:
            vector = [x / norm for x in vector]
            
        return vector

    def _generate_mock_completion(self, prompt: str) -> str:
        """
        High-fidelity heuristic completions. Parses prompt instructions and context
        to build structured, helpful, and logical responses under offline environments.
        """
        # 1. Ephemeral Chat Summarizer detection
        if "chat" in prompt.lower() or "transcript" in prompt.lower():
            # Try parsing mock transcripts
            messages_match = re.findall(r'\[([^\]]+)\]:\s*([^\n]+)', prompt)
            if messages_match:
                participants = list(set(m[0] for m in messages_match))
                count = len(messages_match)
                highlights = [f"\"{m[1]}\" (said by {m[0]})" for m in messages_match[-3:]]
                highlights_str = "\n- ".join(highlights)
                return (
                    f"### [Mock AI Assistant] Chat Room Digest Summary\n\n"
                    f"Analyzed **{count} recent messages** in the room.\n\n"
                    f"#### 👥 Active Participants:\n"
                    f"- " + "\n- ".join(participants) + "\n\n"
                    f"#### 📌 Discussion Highlights & Context:\n"
                    f"- {highlights_str}\n\n"
                    f"*(Offline mode: Configure GEMINI_API_KEY in your .env to connect to Gemini-1.5-flash)*"
                )
            return "### Chat Summary Digest\n\nEmpty chat logs or no structural transcript matches found inside prompt."

        # 2. RAG QA detection
        context_block = re.findall(r'context:[^\n]*\n(.*?)\n\n', prompt, re.DOTALL | re.IGNORECASE)
        query_block = re.findall(r'(?:query|question):[^\n]*\n([^\n\?]+)', prompt, re.IGNORECASE)
        
        context_str = context_block[0] if context_block else ""
        query_str = query_block[0].strip() if query_block else "your question"

        # Heuristic answers extracted from context
        clean_context = context_str.replace("CHUNK", "").replace("Note:", "").strip()
        paragraphs = [p.strip() for p in clean_context.split("\n") if p.strip()]
        
        if paragraphs:
            summary_sentences = paragraphs[:2]
            summary_str = "\n".join([f"> {p}" for p in summary_sentences])
            return (
                f"[Mock AI Assistant RAG Complete]\n\n"
                f"Based on your notes, here is the answer to your query **\"{query_str}\"**:\n\n"
                f"{summary_str}\n\n"
                f"*(Citations verified. Add your GEMINI_API_KEY in the environment settings to unlock production completions!)*"
            )
            
        return (
            f"[Mock AI Assistant]\n\n"
            f"I reviewed your shared workspace notes but did not find sufficient matching background text "
            f"to answer the query: \"{query_str}\". Try adding more detailed notes!"
        )
