from typing import Any, Dict, List, Optional, Tuple

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

    def _parse_response(self, response) -> Dict[str, Any]:
        """Parse Gemini response and extract function calls or text."""
        if not response.candidates:
            return {"type": "text", "content": "", "all_function_calls": []}

        candidate = response.candidates[0]

        if not candidate.content or not candidate.content.parts:
            return {"type": "text", "content": "", "all_function_calls": []}

        # Collect ALL function calls and text from ALL parts
        text_content = ""
        all_function_calls = []

        for part in candidate.content.parts:
            if part.function_call:
                all_function_calls.append({
                    "name": part.function_call.name,
                    "args": dict(part.function_call.args) if part.function_call.args else {},
                })
            if part.text:
                text_content += part.text

        # If there are function calls, return them all
        if all_function_calls:
            return {
                "type": "function_call",
                "name": all_function_calls[0]["name"],
                "args": all_function_calls[0]["args"],
                "all_function_calls": all_function_calls,
                "text_before_calls": text_content,  # Any text before function calls
            }

        # No function calls, return text
        return {
            "type": "text",
            "content": text_content,
            "all_function_calls": [],
        }

    def build_initial_contents(
        self,
        history: List[Dict[str, str]],
        user_message: str,
    ) -> List[types.Content]:
        """Build initial contents array from history and user message."""
        contents = self._build_history(history)
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_message)],
            )
        )
        return contents

    def append_function_call_and_result(
        self,
        contents: List[types.Content],
        function_name: str,
        function_args: Dict[str, Any],
        function_result: Dict[str, Any],
    ) -> List[types.Content]:
        """
        Append a function call (from model) and its result (from user) to contents.

        This preserves the conversation history properly for multi-turn function calling.
        """
        # Add model's function call
        contents.append(
            types.Content(
                role="model",
                parts=[
                    types.Part.from_function_call(
                        name=function_name,
                        args=function_args,
                    )
                ],
            )
        )

        # Add function response (as user role per Gemini API)
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

        return contents

    async def generate_with_contents(
        self,
        system_prompt: str,
        contents: List[types.Content],
        tools_schema: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a response using the provided contents array.

        This is the core method that handles both initial requests and
        continuation after function calls.
        """
        tools = self._create_tools(tools_schema) if tools_schema else None

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                tools=tools,
            ),
        )

        # Debug logging
        print(f"\n{'='*50}")
        print(f"GEMINI RESPONSE:")
        print(f"Contents length: {len(contents)}")
        print(f"Candidates: {len(response.candidates) if response.candidates else 0}")
        if response.candidates:
            candidate = response.candidates[0]
            print(f"Finish reason: {candidate.finish_reason}")
            if candidate.content and candidate.content.parts:
                for i, part in enumerate(candidate.content.parts):
                    if part.function_call:
                        print(f"Part {i}: FUNCTION_CALL({part.function_call.name}, {dict(part.function_call.args) if part.function_call.args else {}})")
                    elif part.text:
                        print(f"Part {i}: TEXT({part.text[:100]}...)" if len(part.text or "") > 100 else f"Part {i}: TEXT({part.text})")
                    else:
                        print(f"Part {i}: {part}")
        print(f"{'='*50}\n")

        return self._parse_response(response)

    # Legacy methods for backwards compatibility
    async def generate_response(
        self,
        system_prompt: str,
        history: List[Dict[str, str]],
        user_message: str,
        tools_schema: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Generate a response from Gemini (legacy method)."""
        contents = self.build_initial_contents(history, user_message)
        return await self.generate_with_contents(system_prompt, contents, tools_schema)

    async def generate_response_with_tool_result(
        self,
        system_prompt: str,
        history: List[Dict[str, str]],
        user_message: str,
        function_name: str,
        function_args: Dict[str, Any],
        function_result: Dict[str, Any],
        tools_schema: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Continue generation after a function call (legacy method)."""
        contents = self.build_initial_contents(history, user_message)
        contents = self.append_function_call_and_result(
            contents, function_name, function_args, function_result
        )
        return await self.generate_with_contents(system_prompt, contents, tools_schema)


# Singleton instance
gemini_service = GeminiService()
