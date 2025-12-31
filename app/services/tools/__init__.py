# Tools Package - Function calling tools
# Import all tools to register them with the registry

from app.services.tools.base import BaseTool, ToolResult
from app.services.tools.registry import ToolRegistry
from app.services.tools.set_company import SetCompanyTool
from app.services.tools.save_contact import SaveContactTool
from app.services.tools.save_inquiry import SaveInquiryTool
from app.services.tools.end_conversation import EndConversationTool

__all__ = [
    "BaseTool",
    "ToolResult",
    "ToolRegistry",
    "SetCompanyTool",
    "SaveContactTool",
    "SaveInquiryTool",
    "EndConversationTool",
]
