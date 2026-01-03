from typing import Dict, List, Optional, Type

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.tools.base import BaseTool


# Tool groups for different agents
ROUTER_TOOLS = ["set_company"]
KOSSODO_TOOLS = ["save_contact", "save_inquiry", "end_conversation"]
KOSSOMET_TOOLS = ["save_contact", "save_inquiry", "end_conversation"]


class ToolRegistry:
    """Registry for managing available tools with group support."""

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
    def get_tools_for_group(
        cls,
        group: Optional[str],
        session: AsyncSession,
        conversation_id: int
    ) -> List[BaseTool]:
        """
        Get tool instances for a specific group (company).

        Args:
            group: The company/group name ("kossodo", "kossomet", or None for router)
            session: Database session
            conversation_id: Current conversation ID

        Returns:
            List of tool instances for the specified group
        """
        if group == "kossodo":
            tool_names = KOSSODO_TOOLS
        elif group == "kossomet":
            tool_names = KOSSOMET_TOOLS
        else:
            # Router phase - only set_company
            tool_names = ROUTER_TOOLS

        return [
            cls._tools[name](session, conversation_id)
            for name in tool_names
            if name in cls._tools
        ]

    @classmethod
    def get_gemini_tools_for_group(
        cls,
        group: Optional[str],
        session: AsyncSession,
        conversation_id: int
    ) -> List[Dict]:
        """
        Get tools in Gemini function declaration format for a specific group.

        Args:
            group: The company/group name ("kossodo", "kossomet", or None for router)
            session: Database session
            conversation_id: Current conversation ID

        Returns:
            List of tool declarations for Gemini
        """
        tools = cls.get_tools_for_group(group, session, conversation_id)
        return [tool.to_gemini_tool() for tool in tools]

    # Legacy methods for backward compatibility
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

    @classmethod
    def get_tool_names_for_group(cls, group: Optional[str]) -> List[str]:
        """Get list of tool names for a specific group."""
        if group == "kossodo":
            return KOSSODO_TOOLS
        elif group == "kossomet":
            return KOSSOMET_TOOLS
        else:
            return ROUTER_TOOLS
