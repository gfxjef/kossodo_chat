# Multi-Turn Function Calling Patterns

Complete guide for implementing agentic loops with Gemini function calling.

## Core Agentic Loop

```python
# app/core/agent.py
from google.genai import types

class Agent:
    def __init__(self, gemini_service, tool_registry):
        self.gemini = gemini_service
        self.tools = tool_registry
    
    async def process_message(
        self,
        session_id: str,
        user_message: str,
        history: list
    ) -> str:
        """
        Process user message with multi-turn function calling.
        
        CRITICAL: Never rebuild contents between tool calls.
        """
        # Build initial contents
        contents = self.gemini.build_initial_contents(history, user_message)
        
        # Get tool declarations
        tool_declarations = self.tools.get_declarations()
        
        # Agentic loop
        max_iterations = 10  # Safety limit
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            
            # Generate response
            response = await self.gemini.generate_with_cache(
                contents=contents,
                tools=tool_declarations
            )
            
            # Check for function calls
            function_calls = self._extract_function_calls(response)
            
            if not function_calls:
                # No more function calls - return text response
                return self._extract_text(response)
            
            # Execute ALL function calls and append results
            for call in function_calls:
                result = await self._execute_tool(call)
                
                # CRITICAL: Append to existing contents, don't rebuild
                self.gemini.append_function_result(contents, call, result)
        
        raise RuntimeError("Max iterations reached in agentic loop")
    
    def _extract_function_calls(self, response) -> list:
        """Extract all function calls from response."""
        calls = []
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    calls.append(part.function_call)
        return calls
    
    def _extract_text(self, response) -> str:
        """Extract text from response."""
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if hasattr(part, 'text') and part.text:
                    return part.text
        return ""
    
    async def _execute_tool(self, call) -> dict:
        """Execute a tool and return result."""
        tool = self.tools.get(call.name)
        if not tool:
            return {"error": f"Unknown tool: {call.name}"}
        
        try:
            # Convert args to dict
            args = dict(call.args) if call.args else {}
            result = await tool.execute(**args)
            return {"success": True, **result}
        except Exception as e:
            return {"error": str(e)}
```

## Contents Accumulation Pattern

The critical insight: Gemini requires the complete conversation history including all function calls and results to maintain context.

```python
# ✅ CORRECT: Contents grows with each tool execution
# Initial state:
contents = [
    Content(role="user", parts=[Part(text="Save my contact info")])
]

# After first generate (model calls save_contact):
contents = [
    Content(role="user", parts=[Part(text="Save my contact info")]),
    Content(role="model", parts=[Part(function_call=save_contact_call)]),
    Content(role="user", parts=[Part(function_response=save_contact_result)])
]

# After second generate (model calls end_conversation):
contents = [
    Content(role="user", parts=[Part(text="Save my contact info")]),
    Content(role="model", parts=[Part(function_call=save_contact_call)]),
    Content(role="user", parts=[Part(function_response=save_contact_result)]),
    Content(role="model", parts=[Part(function_call=end_conversation_call)]),
    Content(role="user", parts=[Part(function_response=end_conversation_result)])
]
```

## Handling Multiple Simultaneous Function Calls

Gemini can return multiple function calls in a single response:

```python
async def process_multiple_calls(self, response, contents):
    """Handle multiple function calls in one response."""
    function_calls = self._extract_function_calls(response)
    
    if len(function_calls) > 1:
        logger.info(f"Processing {len(function_calls)} simultaneous calls")
    
    # Execute sequentially (order matters for some tools)
    for call in function_calls:
        result = await self._execute_tool(call)
        self.gemini.append_function_result(contents, call, result)
    
    # Single API call after all tools executed
    return await self.gemini.generate_with_cache(contents)
```

## Tool Declaration Best Practices

```python
# app/services/tools/save_contact.py
from app.services.tools.base import BaseTool, ToolRegistry

@ToolRegistry.register
class SaveContactTool(BaseTool):
    name = "save_contact"
    description = """
    Save customer contact information. 
    ALL 5 fields are REQUIRED before calling this tool:
    - name: Customer's full name
    - phone: Phone number with country code
    - email: Valid email address
    - company_name: Company or organization name
    - ruc_dni: Tax ID (RUC) or personal ID (DNI)
    
    Do NOT call this tool until all fields have been collected from the customer.
    """
    
    def get_parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Customer's full name"
                },
                "phone": {
                    "type": "string", 
                    "description": "Phone number with country code"
                },
                "email": {
                    "type": "string",
                    "description": "Email address"
                },
                "company_name": {
                    "type": "string",
                    "description": "Company or organization name"
                },
                "ruc_dni": {
                    "type": "string",
                    "description": "Tax ID (RUC) or personal ID (DNI)"
                }
            },
            "required": ["name", "phone", "email", "company_name", "ruc_dni"]
        }
    
    async def execute(self, **params) -> dict:
        # Validate all fields present
        required = ["name", "phone", "email", "company_name", "ruc_dni"]
        missing = [f for f in required if not params.get(f)]
        
        if missing:
            return {
                "success": False,
                "error": f"Missing required fields: {missing}"
            }
        
        # Save to database
        contact = await self.repo.create(params)
        
        return {
            "success": True,
            "contact_id": contact.id,
            "message": "Contact saved successfully"
        }
```

## Error Recovery in Agentic Loop

```python
async def process_with_recovery(self, contents, max_retries=3):
    """Process with error recovery."""
    retries = 0
    
    while retries < max_retries:
        try:
            response = await self.gemini.generate_with_cache(contents)
            return response
        except Exception as e:
            retries += 1
            
            if "rate_limit" in str(e).lower():
                await asyncio.sleep(2 ** retries)  # Exponential backoff
                continue
            
            if "invalid_argument" in str(e).lower():
                # Possibly corrupted contents, try truncating
                if len(contents) > 2:
                    contents = contents[-2:]  # Keep only last exchange
                    continue
            
            raise
    
    raise RuntimeError("Max retries exceeded")
```

## Session State Management

```python
# app/core/session.py
from dataclasses import dataclass, field
from typing import Optional
import uuid

@dataclass
class ConversationSession:
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    company: Optional[str] = None  # "kossodo" or "kossomet"
    contact_complete: bool = False
    inquiry_saved: bool = False
    conversation_ended: bool = False
    contents: list = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "company": self.company,
            "contact_complete": self.contact_complete,
            "inquiry_saved": self.inquiry_saved,
            "conversation_ended": self.conversation_ended
        }
```

## Testing Function Calling

```python
# tests/test_agent.py
import pytest

@pytest.mark.asyncio
async def test_multi_turn_function_calling():
    """Test that context is preserved across function calls."""
    agent = Agent(gemini_service, tool_registry)
    
    # Simulate conversation
    response1 = await agent.process_message(
        session_id="test",
        user_message="Quiero cotizar una balanza",
        history=[]
    )
    
    # Agent should infer KOSSODO and ask for contact
    assert "nombre" in response1.lower() or "contacto" in response1.lower()
    
    # Continue conversation
    response2 = await agent.process_message(
        session_id="test", 
        user_message="Soy Juan Pérez de Laboratorios ABC",
        history=[
            {"role": "user", "content": "Quiero cotizar una balanza"},
            {"role": "assistant", "content": response1}
        ]
    )
    
    # Should ask for remaining fields
    assert any(field in response2.lower() for field in ["teléfono", "email", "ruc"])
```
