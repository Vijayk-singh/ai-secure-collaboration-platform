from typing import Generic, TypeVar, List
from pydantic import BaseModel, Field

# Generic Type variable to serialize lists of any Pydantic model
T = TypeVar("T")

class PageParams(BaseModel):
    """
    Standard pagination query parameters.
    """
    limit: int = Field(20, ge=1, le=100, description="Number of items to return per page")
    offset: int = Field(0, ge=0, description="Pagination index offset")

class Page(BaseModel, Generic[T]):
    """
    Standard paginated envelope response.
    """
    items: List[T] = Field(..., description="List of paginated items")
    total: int = Field(..., description="Total items available in the query")
    limit: int = Field(..., description="Limit parameter used in lookup")
    offset: int = Field(..., description="Offset parameter used in lookup")
