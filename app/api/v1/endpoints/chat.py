from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent import Agent
from app.db.session import get_db
from app.models.schemas import ChatRequest, ChatResponse, ConversationStatus

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """
    Send a message to the chat agent.

    - If session_id is provided, continues the existing conversation.
    - If session_id is not provided, starts a new conversation.
    """
    try:
        agent = Agent(db)
        result = await agent.process_message(
            message=request.message,
            session_id=request.session_id,
        )

        return ChatResponse(
            session_id=result["session_id"],
            message=result["message"],
            conversation_status=ConversationStatus(result["conversation_status"]),
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing message: {str(e)}",
        )
