from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

from app.config.settings import settings


class GeminiService:
    """Service for interacting with Google Gemini API."""

    def __init__(self):
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model_name = settings.gemini_model

    def _create_tools(
        self, tools_schema: List[Dict[str, Any]]
    ) -> Optional[List[types.Tool]]:
        """Create Gemini tools from tool schemas."""
        if not tools_schema:
            return None

        function_declarations = []
        for tool_schema in tools_schema:
            func_decl = types.FunctionDeclaration(
                name=tool_schema["name"],
                description=tool_schema["description"],
                parameters=tool_schema["parameters"],
            )
            function_declarations.append(func_decl)

        return [types.Tool(function_declarations=function_declarations)]

    def _build_history(
        self, messages: List[Dict[str, str]]
    ) -> List[types.Content]:
        """Convert message history to Gemini format."""
        history = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            history.append(
                types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=msg["content"])],
                )
            )
        return history

    async def generate_response(
        self,
        system_prompt: str,
        history: List[Dict[str, str]],
        user_message: str,
        tools_schema: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a response from Gemini.

        Returns:
            Dict with either:
            - {"type": "text", "content": str} for text responses
            - {"type": "function_call", "name": str, "args": dict} for function calls
        """
        # Build conversation contents
        contents = self._build_history(history)
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_message)],
            )
        )

        # Prepare tools
        tools = self._create_tools(tools_schema) if tools_schema else None

        # Generate response
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                tools=tools,
            ),
        )

        # Parse response
        candidate = response.candidates[0]
        part = candidate.content.parts[0]

        # Check if it's a function call
        if part.function_call:
            return {
                "type": "function_call",
                "name": part.function_call.name,
                "args": dict(part.function_call.args) if part.function_call.args else {},
            }

        # It's a text response
        return {
            "type": "text",
            "content": part.text,
        }

    async def generate_response_with_tool_result(
        self,
        system_prompt: str,
        history: List[Dict[str, str]],
        user_message: str,
        function_name: str,
        function_result: Dict[str, Any],
        tools_schema: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Continue generation after a function call with its result.

        This is used to feed back the result of a function call to Gemini
        so it can generate the final response to the user.
        """
        # Build conversation contents
        contents = self._build_history(history)

        # Add user message
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_message)],
            )
        )

        # Add model's function call (simulated)
        contents.append(
            types.Content(
                role="model",
                parts=[
                    types.Part.from_function_call(
                        name=function_name,
                        args=function_result.get("data", {}),
                    )
                ],
            )
        )

        # Add function response
        contents.append(
            types.Content(
                role="user",
                parts=[
                    types.Part.from_function_response(
                        name=function_name,
                        response=function_result,
                    )
                ],
            )
        )

        # Prepare tools
        tools = self._create_tools(tools_schema) if tools_schema else None

        # Generate response
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                tools=tools,
            ),
        )

        # Parse response
        candidate = response.candidates[0]
        part = candidate.content.parts[0]

        # Check for another function call
        if part.function_call:
            return {
                "type": "function_call",
                "name": part.function_call.name,
                "args": dict(part.function_call.args) if part.function_call.args else {},
            }

        return {
            "type": "text",
            "content": part.text,
        }


# Singleton instance
gemini_service = GeminiService()
