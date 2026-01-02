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

        # Get message history (excluding the message we just added)
        history = await self._get_message_history(conversation.id)
        history = history[:-1]

        # Get tools schema
        tools_schema = ToolRegistry.get_gemini_tools(
            self.session, conversation.id
        )

        # Build initial contents array
        contents = gemini_service.build_initial_contents(history, message)

        # Generate initial response
        response = await gemini_service.generate_with_contents(
            system_prompt=self.system_prompt,
            contents=contents,
            tools_schema=tools_schema,
        )

        # Handle function calls with ACCUMULATED contents
        max_iterations = 10  # Increased to handle multiple sequential calls
        iteration = 0
        last_tool_name = None
        collected_text = ""  # Collect any text returned before/between function calls

        while response["type"] == "function_call" and iteration < max_iterations:
            # Collect any text that came before function calls
            if response.get("text_before_calls"):
                collected_text += response["text_before_calls"]

            # Get ALL function calls from this response
            all_function_calls = response.get("all_function_calls", [])

            # Execute ALL function calls and append each to contents
            for func_call in all_function_calls:
                tool_name = func_call["name"]
                tool_args = func_call["args"]
                last_tool_name = tool_name

                print(f"Executing tool: {tool_name} with args: {tool_args}")

                # Execute the tool
                tool_result = await self._execute_tool(
                    conversation.id, tool_name, tool_args
                )

                # CRITICAL: Append function call AND result to contents
                # This preserves the conversation context for the next call
                contents = gemini_service.append_function_call_and_result(
                    contents, tool_name, tool_args, tool_result
                )

            # Generate next response with updated contents
            response = await gemini_service.generate_with_contents(
                system_prompt=self.system_prompt,
                contents=contents,
                tools_schema=tools_schema,
            )

            iteration += 1

        # Extract final text response
        assistant_message = response.get("content", "")

        # Include any text collected before function calls
        if collected_text and not assistant_message:
            assistant_message = collected_text

        # Fallback message if Gemini didn't return text after tool execution
        if not assistant_message and last_tool_name:
            if last_tool_name == "end_conversation":
                assistant_message = (
                    "¡Gracias por contactar al Grupo Kossodo! "
                    "Un asesor se comunicará contigo pronto. ¡Que tengas un excelente día!"
                )
            elif last_tool_name == "save_inquiry":
                assistant_message = (
                    "Perfecto. Un asesor de nuestro equipo "
                    "se pondrá en contacto contigo a la brevedad. "
                    "¿Hay algo más en lo que pueda ayudarte?"
                )
            elif last_tool_name == "save_contact":
                assistant_message = (
                    "Gracias. ¿Me podrías proporcionar los datos que aún faltan?"
                )
            elif last_tool_name == "set_company":
                assistant_message = (
                    "Entendido. Para que un asesor pueda contactarte, "
                    "necesito algunos datos. ¿Cuál es tu nombre completo?"
                )
            else:
                assistant_message = "¿En qué más puedo ayudarte?"

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
