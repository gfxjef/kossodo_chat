from typing import Any, Dict, Optional

from app.db.repositories.conversation import ConversationRepository
from app.models.database import ConversationStatus
from app.services.tools.base import BaseTool, ToolResult
from app.services.tools.registry import ToolRegistry


@ToolRegistry.register
class EndConversationTool(BaseTool):
    """Tool to mark the conversation as completed."""

    name = "end_conversation"
    description = (
        "Mark the conversation as completed. "
        "Use this when the client has provided all necessary information "
        "(company, contact details, and inquiry) and you have informed them "
        "that an advisor will contact them soon."
    )

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": (
                        "Optional brief summary of the conversation, "
                        "including key points discussed."
                    ),
                }
            },
            "required": [],
        }

    async def execute(self, summary: Optional[str] = None) -> ToolResult:
        """Execute the tool to end the conversation."""
        repo = ConversationRepository(self.session)
        conversation = await repo.get_by_id(self.conversation_id)

        if not conversation:
            return ToolResult(
                success=False,
                message="Conversation not found.",
            )

        await repo.set_status(conversation, ConversationStatus.COMPLETED.value)

        return ToolResult(
            success=True,
            data={
                "status": ConversationStatus.COMPLETED.value,
                "summary": summary,
            },
            message="Conversation marked as completed.",
        )
