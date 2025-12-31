from typing import Dict, List, Type

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.tools.base import BaseTool


class ToolRegistry:
    """Registry for managing available tools."""

    _tools: Dict[str, Type[BaseTool]] = {}

    @classmethod
    def register(cls, tool_class: Type[BaseTool]) -> Type[BaseTool]:
        """Decorator to register a tool class."""
        cls._tools[tool_class.name] = tool_class
        return tool_class

    @classmethod
    def get_tool(
        cls, name: str, session: AsyncSession, conversation_id: int
    ) -> BaseTool:
        """Get a tool instance by name."""
        if name not in cls._tools:
            raise ValueError(f"Tool '{name}' not found in registry")
        return cls._tools[name](session, conversation_id)

    @classmethod
    def get_all_tools(
        cls, session: AsyncSession, conversation_id: int
    ) -> List[BaseTool]:
        """Get instances of all registered tools."""
        return [
            tool_class(session, conversation_id)
            for tool_class in cls._tools.values()
        ]

    @classmethod
    def get_gemini_tools(
        cls, session: AsyncSession, conversation_id: int
    ) -> List[Dict]:
        """Get all tools in Gemini function declaration format."""
        tools = cls.get_all_tools(session, conversation_id)
        return [tool.to_gemini_tool() for tool in tools]

    @classmethod
    def get_tool_names(cls) -> List[str]:
        """Get list of all registered tool names."""
        return list(cls._tools.keys())
