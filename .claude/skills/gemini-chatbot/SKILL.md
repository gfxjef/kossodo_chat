---
name: gemini-chatbot
description: FastAPI + Gemini chatbot development with context caching, multi-turn function calling, and cost optimization. Use when building conversational AI agents with Gemini 2.5 models, implementing agentic loops with tool execution, managing conversation sessions, or optimizing API costs with explicit/implicit caching. Triggers on projects using google-genai SDK, FastAPI chat endpoints, function calling patterns, or system prompt optimization.
---

# Gemini Chatbot Skill

Build production-ready conversational AI agents with FastAPI and Google Gemini, optimized for cost and performance.

## Core Architecture

```
Client → FastAPI → Agent → GeminiService → Tool Execution → Database
                              ↓
                    Context Caching (90% cost reduction)
```

## Context Caching Strategy

### Implicit Caching (Automatic)
Enabled by default on Gemini 2.5 models. No code changes needed. Automatic cost savings when requests share common prefixes.

**Maximize hits:**
- Keep system prompt at the START of contents
- Send requests with similar prefixes in short time windows
- Check `usage_metadata.cached_content_token_count` in responses

### Explicit Caching (Recommended for Production)
Guarantees 90% discount on cached tokens. Ideal for:
- Large system prompts (>2,048 tokens for 2.5 Flash)
- High-volume chatbots with consistent instructions
- Multi-user scenarios with shared context

**Implementation pattern:** See `references/caching_patterns.md`

## Multi-Turn Function Calling

**Critical rule:** NEVER rebuild contents array between tool calls.

```python
# ✅ CORRECT: Accumulate context
contents = build_initial_contents(history, user_message)
while True:
    response = generate(contents)
    if not response.function_calls:
        break
    for call in response.function_calls:
        result = execute(call)
        append_to_contents(contents, call, result)  # APPEND, don't rebuild

# ❌ WRONG: Rebuilding loses tool execution context
while True:
    contents = build_contents()  # This breaks multi-turn
    response = generate(contents)
```

**Pattern details:** See `references/function_calling.md`

## Conversation Flow Architecture: 3 Eslabones Model

Most customer service chatbots follow a **3-stage conversation model**. Understanding this helps organize tools and system prompts:

```
┌─────────────────────────────────────────────────────────────────┐
│  ESLABÓN 1: Greeting + Data Collection                          │
│  ─────────────────────────────────────                          │
│  • Agent introduction                                           │
│  • Identify customer need/intent                                │
│  • Collect required contact/identification data                 │
│                                                                 │
│  Typical tools: set_context, save_contact, identify_user        │
│  Stability: HIGH (rarely changes)                               │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│  ESLABÓN 2: Query Resolution  ⚡ PRIMARY EXTENSION POINT        │
│  ─────────────────────────────                                  │
│  • Capture specific customer request                            │
│  • Execute business logic tools                                 │
│  • THIS IS WHERE MOST NEW TOOLS GO                              │
│                                                                 │
│  Example tools:                                                 │
│    - save_inquiry      (capture request)                        │
│    - get_quote         (pricing)                                │
│    - check_inventory   (availability)                           │
│    - schedule_service  (appointments)                           │
│    - search_products   (catalog)                                │
│    - process_order     (transactions)                           │
│                                                                 │
│  Stability: LOW (frequently extended with new business needs)   │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│  ESLABÓN 3: Closure                                             │
│  ──────────────────                                             │
│  • Confirm next steps                                           │
│  • Close conversation gracefully                                │
│                                                                 │
│  Typical tools: end_conversation, send_summary                  │
│  Stability: HIGH (rarely changes)                               │
└─────────────────────────────────────────────────────────────────┘
```

**Design Principles:**

1. **Tool Classification**: When adding new tools, identify which eslabón they belong to
2. **System Prompt Updates**: Each new tool requires prompt instructions for when/how Gemini should use it
3. **Eslabón 2 Focus**: 90% of new features are Eslabón 2 tools
4. **Flow Control**: System prompt defines transitions between eslabones (e.g., "only proceed to save_inquiry after all contact fields collected")

**Example System Prompt Structure:**
```python
SYSTEM_PROMPT = """
## ESLABÓN 1: Saludo y Datos
- Presentarte como [Agent Name]
- Identificar necesidad del cliente
- Recopilar datos de contacto usando save_contact

## ESLABÓN 2: Resolución
- [Tool-specific instructions here]
- Usar get_quote cuando cliente pida cotización
- Usar check_inventory cuando pregunte disponibilidad

## ESLABÓN 3: Cierre
- Confirmar siguientes pasos
- Usar end_conversation al finalizar
"""
```

## Project Structure

Standard FastAPI + Gemini chatbot layout:

```
app/
├── core/
│   ├── agent.py           # Orchestration, session management
│   └── prompts/
│       └── system_prompt.py
├── services/
│   ├── gemini.py          # Gemini API wrapper + caching
│   └── tools/             # Tool implementations
│       ├── __init__.py    # ToolRegistry
│       └── base.py        # BaseTool class
├── repositories/          # Async SQLAlchemy repos
└── main.py                # FastAPI app
```

## GeminiService Implementation

Key methods for your `app/services/gemini.py`:

```python
from google import genai
from google.genai import types

class GeminiService:
    def __init__(self):
        self.client = genai.Client()
        self.model = "gemini-2.5-flash-001"  # Use explicit version
        self.cache = None
    
    async def init_cache(self, system_prompt: str, ttl: str = "3600s"):
        """Initialize explicit cache for system prompt."""
        self.cache = self.client.caches.create(
            model=self.model,
            config=types.CreateCachedContentConfig(
                display_name="chatbot-system-prompt",
                system_instruction=system_prompt,
                ttl=ttl,
            )
        )
    
    def build_initial_contents(self, history: list, user_message: str) -> list:
        """Build contents array from history + new message."""
        contents = []
        for msg in history:
            contents.append(types.Content(
                role=msg["role"],
                parts=[types.Part(text=msg["content"])]
            ))
        contents.append(types.Content(
            role="user",
            parts=[types.Part(text=user_message)]
        ))
        return contents
    
    def append_function_result(self, contents: list, call, result: dict):
        """Append function call and result to context. CRITICAL for multi-turn."""
        contents.append(types.Content(
            role="model",
            parts=[types.Part(function_call=call)]
        ))
        contents.append(types.Content(
            role="user",
            parts=[types.Part(function_response=types.FunctionResponse(
                name=call.name,
                response=result
            ))]
        ))
```

## Tool System Pattern

Plugin architecture with auto-registration:

```python
# app/services/tools/base.py
class ToolRegistry:
    _tools = {}
    
    @classmethod
    def register(cls, tool_class):
        instance = tool_class()
        cls._tools[instance.name] = instance
        return tool_class
    
    @classmethod
    def get_declarations(cls) -> list:
        return [t.get_declaration() for t in cls._tools.values()]

class BaseTool:
    name: str
    description: str
    
    def get_parameters_schema(self) -> dict:
        raise NotImplementedError
    
    async def execute(self, **params) -> dict:
        raise NotImplementedError
    
    def get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=self.get_parameters_schema()
        )
```

## Cost Monitoring

Always log cache performance:

```python
def log_usage(response):
    meta = response.usage_metadata
    cached = getattr(meta, 'cached_content_token_count', 0)
    total = meta.prompt_token_count
    
    if cached > 0:
        savings = (cached / total) * 90  # 90% discount on cached
        logger.info(f"Cache hit: {cached}/{total} tokens ({savings:.1f}% savings)")
```

## Quick Reference

| Aspect | Value |
|--------|-------|
| Min tokens for cache | 2,048 (Flash), 4,096 (Pro) |
| Default TTL | 60 minutes |
| Cached token discount | 90% |
| Model version format | `gemini-2.5-flash-001` |

## Additional Resources

- `references/caching_patterns.md` - Complete caching implementation
- `references/function_calling.md` - Multi-turn patterns and edge cases
- `references/cost_optimization.md` - Production cost strategies
- `scripts/cache_manager.py` - Cache lifecycle management script
