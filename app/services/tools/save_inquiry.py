from typing import Any, Dict

from app.db.repositories.conversation import InquiryRepository
from app.services.tools.base import BaseTool, ToolResult
from app.services.tools.registry import ToolRegistry


@ToolRegistry.register
class SaveInquiryTool(BaseTool):
    """Tool to save the client's inquiry or consultation."""

    name = "save_inquiry"
    description = (
        "Save the client's inquiry or consultation details. "
        "Use this when the client describes what product or service they are interested in, "
        "or what information they need. Capture the full context of their request."
    )

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": (
                        "A detailed description of the client's inquiry, "
                        "including what product/service they need, quantities, "
                        "or any specific requirements they mentioned."
                    ),
                }
            },
            "required": ["description"],
        }

    async def execute(self, description: str) -> ToolResult:
        """Execute the tool to save the inquiry."""
        if not description or not description.strip():
            return ToolResult(
                success=False,
                message="Inquiry description cannot be empty.",
            )

        repo = InquiryRepository(self.session)
        inquiry = await repo.upsert_inquiry(
            conversation_id=self.conversation_id,
            description=description.strip(),
        )

        return ToolResult(
            success=True,
            data={
                "inquiry_id": inquiry.id,
                "description": inquiry.description,
            },
            message="Inquiry saved successfully.",
        )
