from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession


class ToolResult(BaseModel):
    """Result from tool execution."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    message: str


class BaseTool(ABC):
    """Base class for all agent tools."""

    name: str
    description: str

    def __init__(self, session: AsyncSession, conversation_id: int):
        self.session = session
        self.conversation_id = conversation_id

    @abstractmethod
    def get_parameters_schema(self) -> Dict[str, Any]:
        """Return the JSON schema for the tool parameters."""
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with the given parameters."""
        pass

    def to_gemini_tool(self) -> Dict[str, Any]:
        """Convert to Gemini function declaration format."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.get_parameters_schema(),
        }
