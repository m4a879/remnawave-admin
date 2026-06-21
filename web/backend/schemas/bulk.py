"""Schemas for bulk operations."""
from pydantic import BaseModel, Field
from typing import List, Optional


class BulkUserRequest(BaseModel):
    """Request to perform a bulk operation on multiple users."""
    uuids: List[str] = Field(..., min_length=1, max_length=100)


class BulkOperationError(BaseModel):
    """Details about a single failed operation within a bulk request."""
    uuid: str
    error: str


class BulkOperationResult(BaseModel):
    """Result of a bulk operation."""
    success: int
    failed: int
    errors: List[BulkOperationError] = []


class BulkReassignRequest(BaseModel):
    """Request to reassign multiple users to a new admin."""
    uuids: List[str] = Field(..., min_length=1, max_length=100)
    new_admin_id: int = Field(..., description="ID of the admin to assign users to")


class BulkNodeRequest(BaseModel):
    """Request to perform a bulk operation on multiple nodes."""
    uuids: List[str] = Field(..., min_length=1, max_length=500)


class BulkNodeTokenItem(BaseModel):
    """Single node token result."""
    node_uuid: str
    token: Optional[str] = None
    name: Optional[str] = None
    error: Optional[str] = None


class BulkNodeTokenResult(BaseModel):
    """Result of bulk token generation."""
    success: int
    failed: int
    tokens: List[BulkNodeTokenItem] = []


class BulkNodeInstallItem(BaseModel):
    """Single node install command result."""
    node_uuid: str
    name: Optional[str] = None
    token: Optional[str] = None
    install_command: Optional[str] = None
    error: Optional[str] = None


class BulkNodeInstallResult(BaseModel):
    """Result of bulk install command generation."""
    success: int
    failed: int
    items: List[BulkNodeInstallItem] = []
