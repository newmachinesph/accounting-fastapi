from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional, Union
from datetime import datetime

class APIResponse(BaseModel):
    """Standard API response wrapper"""
    success: bool = Field(description="Whether the request was successful")
    data: Optional[Any] = Field(None, description="Response data")
    message: Optional[str] = Field(None, description="Human-readable message")
    errors: Optional[List[str]] = Field(None, description="List of error messages")
    meta: Optional[Dict[str, Any]] = Field(None, description="Metadata about the response")

class PaginatedResponse(BaseModel):
    """Paginated response with metadata"""
    data: List[Any] = Field(description="Array of items")
    pagination: Dict[str, Any] = Field(description="Pagination metadata")
    total: int = Field(description="Total number of items")
    page: int = Field(description="Current page number")
    per_page: int = Field(description="Items per page")
    pages: int = Field(description="Total number of pages")

class ErrorResponse(BaseModel):
    """Standard error response"""
    success: bool = Field(False, description="Always false for errors")
    error: str = Field(description="Error type")
    message: str = Field(description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.now, description="When the error occurred")
    request_id: Optional[str] = Field(None, description="Unique request identifier")

class HealthResponse(BaseModel):
    """Health check response"""
    status: str = Field(description="Service status")
    timestamp: datetime = Field(default_factory=datetime.now)
    version: str = Field(description="API version")
    database: str = Field(description="Database status")
    dependencies: Dict[str, Any] = Field(description="Status of external dependencies")

class DownloadResponse(BaseModel):
    """Download link response"""
    download_url: str = Field(description="Temporary download URL")
    filename: str = Field(description="Original filename")
    expires_at: datetime = Field(description="When the download link expires")
    expires_in: int = Field(description="Seconds until expiration")
    token: str = Field(description="Unique download token")
    size_bytes: Optional[int] = Field(None, description="File size in bytes")
    format: str = Field(description="File format (csv, json)")

class BulkOperationResponse(BaseModel):
    """Response for bulk operations"""
    total_requested: int = Field(description="Number of items requested")
    successful: int = Field(description="Number of items processed successfully")
    failed: int = Field(description="Number of items that failed")
    errors: Optional[List[Dict[str, Any]]] = Field(None, description="Details of any failures")
    created_ids: Optional[List[str]] = Field(None, description="IDs of created items")

class SearchResponse(BaseModel):
    """Search operation response"""
    query: Dict[str, Any] = Field(description="Search parameters used")
    results: List[Any] = Field(description="Search results")
    total_results: int = Field(description="Total number of matching items")
    search_time_ms: float = Field(description="Time taken to execute search")
    suggestions: Optional[List[str]] = Field(None, description="Search suggestions")
