from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class SemanticSearchMatch(BaseModel):
    """
    Schema representing a semantic match chunk.
    """
    note_id: int = Field(..., description="ID of the matching Note document")
    note_title: str = Field(..., description="Title of the parent Note document")
    chunk_index: int = Field(..., description="Order of this chunk inside the document")
    content: str = Field(..., description="Text content body of the chunk")
    score: float = Field(..., description="Cosine similarity score (higher is more similar)")

class SemanticSearchResponse(BaseModel):
    """
    Schema representing the list of semantic search results.
    """
    query: str = Field(..., description="Original search string")
    results: List[SemanticSearchMatch] = Field(..., description="List of highly relevant matching note chunks")

class RAGRequest(BaseModel):
    """
    Schema representing a RAG request payload.
    """
    query: str = Field(..., min_length=3, description="Natural language question to ask the AI assistant")

class RAGResponse(BaseModel):
    """
    Schema representing a RAG completion response with citations.
    """
    query: str = Field(..., description="Original natural language query")
    answer: str = Field(..., description="Generated AI response contextually answered from your notes")
    sources: List[SemanticSearchMatch] = Field(..., description="Note document chunks utilized as context citations")

class ChatSummaryRequest(BaseModel):
    """
    Schema representing a request to summarize chat room logs.
    """
    limit: Optional[int] = Field(50, ge=5, le=200, description="Number of recent messages to analyze for context")

class ChatSummaryResponse(BaseModel):
    """
    Schema representing a chat room summary digest.
    """
    room_id: int = Field(..., description="ID of the summarized chat room")
    summary: str = Field(..., description="Markdown-formatted concise chat summary")
    message_count: int = Field(..., description="Total messages processed to build this summary")
    generated_at: datetime = Field(default_factory=datetime.utcnow, description="Timestamp of summary generation")
