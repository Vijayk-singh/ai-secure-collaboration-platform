from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, declared_attr
from app.core.config import settings

class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy database models.
    Automatically generates the tablename by converting the class name to lowercase.
    """
    @declared_attr.directive
    def __tablename__(cls) -> str:
        return cls.__name__.lower()

# Create async engine with pooling capabilities
# pool_pre_ping checks the connection health before executing commands
engine = create_async_engine(
    settings.async_database_uri,
    pool_pre_ping=True,
    echo=False,  # Set to True for debugging SQL queries locally
    future=True,
)

# Async session factory
async_session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a database session.
    Transactions are automatically closed when the request lifecycle ends.
    """
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()

# Import all models here so that they are registered on Base.metadata
# before Alembic or SQLAlchemy attempts to access them.
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.models.note import Note, Tag
from app.models.chat import ChatRoom, ChatMessage
