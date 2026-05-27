from typing import Optional
from pydantic import BaseModel

class Token(BaseModel):
    """
    Standard OAuth2 compatible token pair response payload.
    """
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class TokenPayload(BaseModel):
    """
    Validation schema to represent decoded JWT token claims.
    """
    sub: Optional[str] = None  # Holds the unique User ID
    exp: Optional[int] = None  # Token expiration unix timestamp
    role: Optional[str] = None # Holds the user role for client-side pre-evaluation

class TokenRefreshRequest(BaseModel):
    """
    Validates token rotation execution requests.
    """
    refresh_token: str
