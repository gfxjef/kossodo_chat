import re
import uuid
from typing import Dict, List, Optional

from google.genai import types as genai_types
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.prompts.system_prompt import get_system_prompt
from app.db.repositories.conversation import (
    ConversationRepository,
    MessageRepository,
)
from app.models.database import ConversationStatus, MessageRole
from app.services.gemini import gemini_service
from app.services.tools import ToolRegistry


class Agent:
    """
    Main agent that orchestrates conversations using multi-agent routing.

    Architecture follows the Coordinator/Dispatcher Pattern:
    - Router phase: Detect intent (sales vs services) using minimal prompt
    - Kossodo phase: Specialized for equipment sales
    - Kossomet phase: Specialized for technical services

    All conversation logic is controlled by the system prompts.
    This class only handles:
    - Session management
    - Message persistence
    - Tool execution
    - Dynamic prompt/tool routing
    - Communication with Gemini
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        # Note: system_prompt is now dynamic, retrieved per-request based on company

    async def _get_or_create_conversation(
        self, session_id: Optional[str]
    ) -> tuple:
        """Get existing conversation or create a new one.

        Handles conversation expiration:
        - If conversation is ACTIVE but idle too long → mark as EXPIRED, create new
        - If conversation is COMPLETED or EXPIRED → create new
        """
        conv_repo = ConversationRepository(self.session)

        if session_id:
            conversation = await conv_repo.get_by_session_id(session_id)
            if conversation:
                # Check if conversation is still usable
                if conversation.status == ConversationStatus.ACTIVE.value:
                    # Check for idle timeout
                    if conv_repo.is_expired(conversation):
                        # Mark as expired and create new
                        await conv_repo.expire_conversation(conversation)
                        print(f"Conversation {session_id} expired due to inactivity")
                    else:
                        # Still active and not expired, continue
                        return conversation, session_id
                # If COMPLETED, EXPIRED, or just expired above → create new

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

    def _looks_like_contact_data(self, message: str) -> bool:
        """
        Detect if message likely contains contact data.

        This helps Gemini by adding contextual hints when the user
        sends data in list format (name, phone, email, etc.)
        """
        has_email = "@" in message and "." in message.split("@")[-1]
        numbers = re.findall(r'\d+', message)
        has_long_number = any(len(n) >= 8 for n in numbers)
        has_multiple_items = message.count(",") >= 1 or message.count(" ") >= 3

        # If has email OR (has long number AND multiple items)
        return has_email or (has_long_number and has_multiple_items)

    def _create_contact_hint(self) -> genai_types.Content:
        """Create a contextual hint for processing contact data."""
        return genai_types.Content(
            role="user",
            parts=[genai_types.Part.from_text(
                text="[Sistema: El mensaje anterior parece contener datos de contacto. "
                "Identifica: nombre, teléfono (9 dígitos), email (@), RUC (11 dígitos) o DNI (8 dígitos), "
                "y nombre de empresa. Usa save_contact con los datos identificados, luego responde "
                "preguntando SOLO por los datos que faltan.]"
            )],
        )

    async def _refresh_conversation(self, session_id: str):
        """Refresh conversation from database to get updated company."""
        conv_repo = ConversationRepository(self.session)
        return await conv_repo.get_by_session_id(session_id)

    async def process_message(
        self, message: str, session_id: Optional[str] = None
    ) -> Dict:
        """
        Process a user message and return the agent's response.

        Uses dynamic routing based on detected company:
        - No company: Router prompt (detect intent)
        - Kossodo: Sales specialist prompt
        - Kossomet: Services specialist prompt

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

        # DYNAMIC ROUTING: Get prompt and tools based on company
        current_company = conversation.company
        system_prompt = get_system_prompt(current_company)
        tools_schema = ToolRegistry.get_gemini_tools_for_group(
            current_company, self.session, conversation.id
        )

        print(f"INFO: Using {'router' if not current_company else current_company} "
              f"prompt with {len(tools_schema)} tools")

        # Build initial contents array
        contents = gemini_service.build_initial_contents(history, message)

        # Proactive hint: If message looks like contact data, add hint at END
        # Only apply hint if we're past the router phase (company is set)
        contents_for_generation = contents.copy()
        if current_company and self._looks_like_contact_data(message):
            print("INFO: Detected contact data pattern, adding contextual hint")
            contents_for_generation.append(self._create_contact_hint())

        # Generate initial response
        response = await gemini_service.generate_with_contents(
            system_prompt=system_prompt,
            contents=contents_for_generation,
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

                # ROUTING: If set_company was called, switch to specialized agent
                if tool_name == "set_company" and tool_result.get("success"):
                    # Refresh conversation to get updated company
                    conversation = await self._refresh_conversation(session_id)
                    current_company = conversation.company

                    # Switch prompt and tools for the specialized agent
                    system_prompt = get_system_prompt(current_company)
                    tools_schema = ToolRegistry.get_gemini_tools_for_group(
                        current_company, self.session, conversation.id
                    )

                    print(f"INFO: Switched to {current_company} agent with "
                          f"{len(tools_schema)} tools")

            # Generate next response with updated contents (and potentially new prompt/tools)
            response = await gemini_service.generate_with_contents(
                system_prompt=system_prompt,
                contents=contents,
                tools_schema=tools_schema,
            )

            iteration += 1

        # Extract final text response
        assistant_message = response.get("content", "")

        # Include any text collected before function calls
        if collected_text and not assistant_message:
            assistant_message = collected_text

        # Fallback for completely empty response (no tools, no text)
        # This can happen when Gemini gets confused with complex input
        if not assistant_message and not last_tool_name:
            # Retry with contextual hint (don't repeat same request)
            print("WARNING: Empty response from Gemini, retrying with hint...")

            # Add hint to help Gemini understand what to do
            retry_contents = contents.copy()
            retry_contents.append(self._create_contact_hint())

            retry_response = await gemini_service.generate_with_contents(
                system_prompt=system_prompt,
                contents=retry_contents,
                tools_schema=tools_schema,
            )

            # Handle retry response - could be text or function_call
            if retry_response["type"] == "function_call":
                # Process any function calls from retry
                retry_calls = retry_response.get("all_function_calls", [])
                for func_call in retry_calls:
                    tool_name = func_call["name"]
                    tool_args = func_call["args"]
                    last_tool_name = tool_name
                    print(f"Executing tool (retry): {tool_name} with args: {tool_args}")
                    tool_result = await self._execute_tool(
                        conversation.id, tool_name, tool_args
                    )
                    # Use original contents to avoid polluting with hint
                    contents = gemini_service.append_function_call_and_result(
                        contents, tool_name, tool_args, tool_result
                    )

                # Get final response after retry tools
                final_retry = await gemini_service.generate_with_contents(
                    system_prompt=system_prompt,
                    contents=contents,
                    tools_schema=tools_schema,
                )
                assistant_message = final_retry.get("content", "")
            else:
                assistant_message = retry_response.get("content", "")

            # If still empty after retry, provide contextual fallback
            if not assistant_message:
                # Check message patterns for better fallback
                if self._looks_like_contact_data(message):
                    assistant_message = (
                        "Gracias por tu información. ¿Podrías confirmar tu nombre completo, "
                        "teléfono, email, RUC/DNI y nombre de empresa?"
                    )
                else:
                    assistant_message = "¿En qué puedo ayudarte?"

        # Fallback message if Gemini didn't return text after tool execution
        if not assistant_message and last_tool_name:
            if last_tool_name == "end_conversation":
                assistant_message = (
                    "¡Gracias por contactar al Grupo Kossodo! "
                    "Un asesor se comunicará contigo pronto. ¡Que tengas un excelente día!"
                )
            elif last_tool_name == "save_inquiry":
                # Customize message based on company
                if current_company == "kossomet":
                    assistant_message = (
                        "Perfecto. Un técnico especializado de Kossomet "
                        "se pondrá en contacto contigo a la brevedad. "
                        "¿Hay algo más en lo que pueda ayudarte?"
                    )
                else:
                    assistant_message = (
                        "Perfecto. Un asesor de ventas de Kossodo "
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
