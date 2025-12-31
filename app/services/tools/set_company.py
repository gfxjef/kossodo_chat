from typing import Any, Dict

from app.db.repositories.conversation import ConversationRepository
from app.services.tools.base import BaseTool, ToolResult
from app.services.tools.registry import ToolRegistry


@ToolRegistry.register
class SetCompanyTool(BaseTool):
    """Tool to set the target company for the inquiry."""

    name = "set_company"
    description = (
        "Set the company that the client's inquiry is directed to. "
        "Use this when the client indicates whether their inquiry is for Kossodo or Kossomet."
    )

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "company": {
                    "type": "string",
                    "enum": ["kossodo", "kossomet"],
                    "description": "The company name: 'kossodo' or 'kossomet'",
                }
            },
            "required": ["company"],
        }

    async def execute(self, company: str) -> ToolResult:
        """Execute the tool to set the company."""
        company = company.lower().strip()

        if company not in ["kossodo", "kossomet"]:
            return ToolResult(
                success=False,
                message=f"Invalid company: {company}. Must be 'kossodo' or 'kossomet'.",
            )

        repo = ConversationRepository(self.session)
        conversation = await repo.get_by_id(self.conversation_id)

        if not conversation:
            return ToolResult(
                success=False,
                message="Conversation not found.",
            )

        await repo.set_company(conversation, company)

        return ToolResult(
            success=True,
            data={"company": company},
            message=f"Company set to {company.capitalize()}.",
        )
