"""
System prompt coordinator for the Grupo Kossodo customer service agent.

This module coordinates the multi-agent prompt system:
- Router prompt: Initial intent detection (sales vs services)
- Kossodo prompt: Specialized for equipment sales
- Kossomet prompt: Specialized for technical services

Architecture follows the Coordinator/Dispatcher Pattern from Google ADK.
"""

from typing import Optional

from app.core.prompts.router_prompt import get_router_prompt
from app.core.prompts.kossodo_prompt import get_kossodo_prompt
from app.core.prompts.kossomet_prompt import get_kossomet_prompt


def get_system_prompt(company: Optional[str] = None) -> str:
    """
    Get the appropriate system prompt based on the detected company.

    Args:
        company: The detected business unit ("kossodo", "kossomet", or None)

    Returns:
        The appropriate system prompt string

    Flow:
        1. company=None -> Router prompt (detect intent)
        2. company="kossodo" -> Kossodo prompt (sales)
        3. company="kossomet" -> Kossomet prompt (services)
    """
    if company == "kossodo":
        return get_kossodo_prompt()
    elif company == "kossomet":
        return get_kossomet_prompt()
    else:
        # No company detected yet, use router prompt
        return get_router_prompt()


# Re-export individual prompt getters for direct access if needed
__all__ = [
    "get_system_prompt",
    "get_router_prompt",
    "get_kossodo_prompt",
    "get_kossomet_prompt",
]
