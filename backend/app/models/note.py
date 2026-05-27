import datetime
from sqlalchemy import Table, Column, String, ForeignKey, DateTime, func
from sqlalchemy.types import UserDefinedType
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

# Association table representing the Many-to-Many relationship between Notes and Tags
note_tags = Table(
    "note_tags",
    Base.metadata,
    Column("note_id", ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

class PGVector(UserDefinedType):
    """
    Custom SQLAlchemy UserDefinedType representing the pgvector vector type.
    Allows native interaction with pgvector without requiring any compiled host libraries.
    """
    def __init__(self, dim: int) -> None:
        self.dim = dim

    def get_col_spec(self, **kw) -> str:
        return f"vector({self.dim})"

    def bind_processor(self, dialect):
        def process(value):
            if value is None:
                return None
            if isinstance(value, list):
                return "[" + ",".join(map(str, value)) + "]"
            return value
        return process

    def result_processor(self, dialect, coltype):
        def process(value):
            if value is None:
                return None
            if isinstance(value, str):
                return [float(x) for x in value.strip("[]").split(",")]
            return value
        return process

class Tag(Base):
    """
    SQLAlchemy database model for note Tags.
    """
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    notes = relationship("Note", secondary=note_tags, back_populates="tags")

class Note(Base):
    """
    SQLAlchemy database model for collaborative markdown Notes.
    """
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=True)  # Markdown text body
    
    # Scoped workspace and note owner indexes
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    workspace = relationship("Workspace", back_populates="notes")
    owner = relationship("User")
    tags = relationship("Tag", secondary=note_tags, back_populates="notes")
    chunks = relationship("NoteChunk", back_populates="note", cascade="all, delete-orphan")

class NoteChunk(Base):
    """
    SQLAlchemy database model representing chunks of a collaborative Note.
    Used for semantic vector indexing and RAG completions.
    """
    __tablename__ = "note_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    note_id: Mapped[int] = mapped_column(
        ForeignKey("notes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    
    # pgvector embedding representation (768 dimensions for Google Gemini embeddings)
    embedding: Mapped[list] = mapped_column(PGVector(dim=768), nullable=False)

    # Relationships
    note = relationship("Note", back_populates="chunks")
