from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================

class Company(str, Enum):
    KOSSODO = "kossodo"
    KOSSOMET = "kossomet"


class ConversationStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    TRANSFERRED = "transferred"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


# =============================================================================
# Request Schemas
# =============================================================================

class ChatRequest(BaseModel):
    """Request to send a message to the chat."""
    message: str = Field(..., min_length=1, max_length=5000)
    session_id: Optional[str] = Field(
        None,
        description="Session ID for continuing a conversation. If not provided, a new session will be created."
    )


# =============================================================================
# Response Schemas
# =============================================================================

class MessageResponse(BaseModel):
    """Single message in a conversation."""
    role: MessageRole
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class ChatResponse(BaseModel):
    """Response from the chat endpoint."""
    session_id: str
    message: str
    conversation_status: ConversationStatus = ConversationStatus.ACTIVE


class ConversationResponse(BaseModel):
    """Full conversation history."""
    session_id: str
    company: Optional[Company] = None
    status: ConversationStatus
    messages: List[MessageResponse]
    created_at: datetime

    class Config:
        from_attributes = True


class ContactResponse(BaseModel):
    """Contact information response."""
    id: int
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    company_name: Optional[str] = None
    ruc_dni: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class InquiryResponse(BaseModel):
    """Inquiry response."""
    id: int
    description: str
    created_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# Tool Schemas (for function calling)
# =============================================================================

class SetCompanyInput(BaseModel):
    """Input for set_company tool."""
    company: Company = Field(..., description="The company: 'kossodo' or 'kossomet'")


class SaveContactInput(BaseModel):
    """Input for save_contact tool."""
    name: Optional[str] = Field(None, description="Client's full name")
    phone: Optional[str] = Field(None, description="Client's phone number")
    email: Optional[str] = Field(None, description="Client's email address")
    company_name: Optional[str] = Field(None, description="Client's company name")
    ruc_dni: Optional[str] = Field(None, description="Client's RUC (business) or DNI (personal ID)")


class SaveInquiryInput(BaseModel):
    """Input for save_inquiry tool."""
    description: str = Field(..., description="Description of the client's inquiry")


class EndConversationInput(BaseModel):
    """Input for end_conversation tool."""
    summary: Optional[str] = Field(None, description="Optional summary of the conversation")


# =============================================================================
# Health Check
# =============================================================================

class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"
    version: str = "0.1.0"
