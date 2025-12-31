import uuid
from typing import Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.prompts.system_prompt import get_system_prompt
from app.db.repositories.conversation import (
    ConversationRepository,
    MessageRepository,
)
from app.models.database import MessageRole
from app.services.gemini import gemini_service
from app.services.tools import ToolRegistry


class Agent:
    """
    Main agent that orchestrates conversations.

    All conversation logic is controlled by the system prompt.
    This class only handles:
    - Session management
    - Message persistence
    - Tool execution
    - Communication with Gemini
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.system_prompt = get_system_prompt()

    async def _get_or_create_conversation(
        self, session_id: Optional[str]
    ) -> tuple:
        """Get existing conversation or create a new one."""
        conv_repo = ConversationRepository(self.session)

        if session_id:
            conversation = await conv_repo.get_by_session_id(session_id)
            if conversation:
                return conversation, session_id

        # Create new conversation with UUID
        new_session_id = str(uuid.uuid4())
        conversation = await conv_repo.create_conversation(new_session_id)
        return conversation, new_session_id

    async def _get_message_history(
        self, conversation_id: int
    ) -> List[Dict[str, str]]:
        """Get conversation history in format for Gemini."""
        msg_repo = MessageRepository(self.session)
        messages = await msg_repo.get_conversation_messages(conversation_id)

        return [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

    async def _save_message(
        self, conversation_id: int, role: str, content: str
    ) -> None:
        """Save a message to the database."""
        msg_repo = MessageRepository(self.session)
        await msg_repo.add_message(
            conversation_id=conversation_id,
            role=role,
            content=content,
        )

    async def _execute_tool(
        self, conversation_id: int, tool_name: str, args: Dict
    ) -> Dict:
        """Execute a tool and return its result."""
        tool = ToolRegistry.get_tool(tool_name, self.session, conversation_id)
        result = await tool.execute(**args)
        return {
            "success": result.success,
            "message": result.message,
            "data": result.data,
        }

    async def process_message(
        self, message: str, session_id: Optional[str] = None
    ) -> Dict:
        """
        Process a user message and return the agent's response.

        Args:
            message: The user's message
            session_id: Optional session ID for continuing a conversation

        Returns:
            Dict with 'session_id', 'message', and 'conversation_status'
        """
        # Get or create conversation
        conversation, session_id = await self._get_or_create_conversation(
            session_id
        )

        # Save user message
        await self._save_message(
            conversation.id, MessageRole.USER.value, message
        )

        # Get message history
        history = await self._get_message_history(conversation.id)
        # Remove the last message (the one we just added) since we'll send it separately
        history = history[:-1]

        # Get tools schema
        tools_schema = ToolRegistry.get_gemini_tools(
            self.session, conversation.id
        )

        # Generate response from Gemini
        response = await gemini_service.generate_response(
            system_prompt=self.system_prompt,
            history=history,
            user_message=message,
            tools_schema=tools_schema,
        )

        # Handle function calls (may be chained)
        max_iterations = 5  # Prevent infinite loops
        iteration = 0

        while response["type"] == "function_call" and iteration < max_iterations:
            tool_name = response["name"]
            tool_args = response["args"]

            # Execute the tool
            tool_result = await self._execute_tool(
                conversation.id, tool_name, tool_args
            )

            # Get updated response with tool result
            response = await gemini_service.generate_response_with_tool_result(
                system_prompt=self.system_prompt,
                history=history,
                user_message=message,
                function_name=tool_name,
                function_result=tool_result,
                tools_schema=tools_schema,
            )

            iteration += 1

        # Extract final text response
        assistant_message = response.get("content", "")

        # Save assistant response
        await self._save_message(
            conversation.id, MessageRole.ASSISTANT.value, assistant_message
        )

        # Refresh conversation to get updated status
        conv_repo = ConversationRepository(self.session)
        conversation = await conv_repo.get_by_session_id(session_id)

        return {
            "session_id": session_id,
            "message": assistant_message,
            "conversation_status": conversation.status,
        }
