# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Chat Kossodo is a conversational AI agent built with FastAPI and Google Gemini for **Grupo Kossodo**, which has two business units:
- **KOSSODO**: Equipment sales (balances, microscopes, lab instruments)
- **KOSSOMET**: Technical services (calibration, maintenance, repair, certification)

The agent automatically infers which business unit the customer needs based on their query context, captures contact information, and registers inquiries for human advisors to follow up.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application (development with auto-reload)
python -m app.main
# Or with uvicorn directly:
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
pytest

# Run a single test file
pytest tests/test_file.py

# Run a specific test
pytest tests/test_file.py::test_function_name

# Linting
ruff check .

# Formatting
black .
```

## Architecture

### Core Flow
```
Client → FastAPI (/api/v1/chat) → Agent → GeminiService → Tool Execution → Database
```

### Key Components

**Agent (`app/core/agent.py`)**: Main orchestration layer. Manages conversation sessions, message persistence, and tool execution loop. All conversation logic is controlled by the system prompt—no hardcoded conversation logic exists in code.

**GeminiService (`app/services/gemini.py`)**: Wrapper around Google Gemini API. Handles function calling (agentic loop) with accumulated context. Uses model `gemini-2.5-flash`.

Key methods:
- `build_initial_contents()`: Creates initial conversation array
- `append_function_call_and_result()`: Adds function call + result to context (CRITICAL for multi-turn)
- `generate_with_contents()`: Core generation method with full context

**Tool System (`app/services/tools/`)**: Plugin-based architecture with automatic registration via `@ToolRegistry.register` decorator. Tools extend `BaseTool` and implement `execute()` method.

**Available Tools**:
- `set_company`: Sets business unit (kossodo/kossomet). Called automatically when agent infers the unit.
- `save_contact`: Stores customer contact info. **All 5 fields required before proceeding**: name, phone, email, company_name, ruc_dni
- `save_inquiry`: Saves customer's inquiry description. Only called after all contact fields are complete.
- `end_conversation`: Marks conversation as completed

**Multi-Agent Prompt System (`app/core/prompts/`)**: Follows the **Coordinator/Dispatcher Pattern** from Google ADK. Dynamic routing based on detected business unit:

```
app/core/prompts/
├── system_prompt.py      # Coordinator - routes to appropriate prompt
├── router_prompt.py      # Phase 1: Detect intent (sales vs services)
├── kossodo_prompt.py     # Phase 2a: Specialized for equipment SALES
└── kossomet_prompt.py    # Phase 2b: Specialized for technical SERVICES
```

**Prompt Routing Flow:**
1. `company=None` → Router prompt (minimal, only detects intent)
2. `company="kossodo"` → Kossodo prompt (sales specialist with usage inquiry)
3. `company="kossomet"` → Kossomet prompt (services specialist)

**Key Differences Between Prompts:**
- **Router**: Only greeting + intent detection. Single tool: `set_company`
- **Kossodo**: Contact collection + **usage inquiry** (asks "what will you use the equipment for?")
- **Kossomet**: Contact collection + service details (no usage inquiry - customer already has equipment)

**Tool Groups** (defined in `registry.py`):
- `ROUTER_TOOLS`: `["set_company"]`
- `KOSSODO_TOOLS`: `["save_contact", "save_inquiry", "end_conversation"]`
- `KOSSOMET_TOOLS`: `["save_contact", "save_inquiry", "end_conversation"]`

**Privacy rule**: Never mentions "saving", "registering", or "storing" customer data
**Natural conversation**: Doesn't repeat data back to the customer; just asks for missing fields

### Conversation Flow: 3 Eslabones (Stages)

The conversation follows a **3-stage model**. This architecture is critical for understanding where new tools belong:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  ESLABÓN 1: Saludo + Recopilación de Datos                              │
│  ─────────────────────────────────────────                              │
│  • Presentación del agente                                              │
│  • Identificar necesidad del cliente → set_company                      │
│  • Recopilar 5 campos de contacto → save_contact                        │
│  • Tools: set_company, save_contact                                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  ESLABÓN 2: Obtener Consulta y Resolver  ⚡ EXTENSIBLE                  │
│  ────────────────────────────────────────                               │
│  • Capturar la consulta/necesidad específica                            │
│  • Ejecutar herramientas de negocio                                     │
│  • AQUÍ VAN TODAS LAS TOOLS DE NEGOCIO FUTURAS                          │
│                                                                         │
│  Tools actuales:                                                        │
│    - save_inquiry: Registra la consulta para seguimiento                │
│                                                                         │
│  Tools futuras (ejemplos):                                              │
│    - get_quote: Cotizaciones automáticas                                │
│    - check_inventory: Consulta de disponibilidad                        │
│    - schedule_service: Agendar servicios técnicos                       │
│    - track_order: Seguimiento de pedidos                                │
│    - get_product_info: Información técnica de productos                 │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  ESLABÓN 3: Despedida                                                   │
│  ────────────────────                                                   │
│  • Confirmar que un asesor contactará al cliente                        │
│  • Cerrar conversación cordialmente                                     │
│  • Tools: end_conversation                                              │
└─────────────────────────────────────────────────────────────────────────┘
```

**Important for Development:**
- When adding new tools, identify which **eslabón** they belong to
- **Eslabón 2 is the primary extension point** - most new business features go here
- Eslabones 1 and 3 are relatively stable (contact capture + goodbye)
- The system prompt (`system_prompt.py`) must be updated to teach Gemini when/how to use new tools
- Each tool should have clear conditions in the prompt for when it should be called

### Database Layer

Async SQLAlchemy 2.0 with SQLite. Uses repository pattern:
- `ConversationRepository`: Manages conversations, eager-loads related entities
- `MessageRepository`, `ContactRepository`, `InquiryRepository`: Entity-specific operations

**Models**: `Conversation`, `Message`, `Contact`, `Inquiry` (one-to-one relationships between Conversation and Contact/Inquiry)

### API Endpoints

- `GET /api/v1/health`: Health check
- `POST /api/v1/chat`: Main chat endpoint. Accepts `{message, session_id?}`, returns `{session_id, message, conversation_status}`

## Key Patterns

- **Async-first**: All DB operations and service calls are async
- **Repository pattern**: Clean separation of database access logic
- **Plugin architecture**: Tools auto-register via decorator
- **Session-based conversations**: UUID `session_id` tracks conversation continuity
- **Accumulated context**: Function calls and results are appended to `contents` array (Gemini API requirement for multi-turn function calling)

## Important: Multi-Turn Function Calling

Gemini can return multiple function calls in one response. The agent:
1. Builds `contents` array with history + user message
2. Gets response with `all_function_calls` list
3. Executes ALL function calls, appending each call+result to `contents`
4. Calls Gemini again with full accumulated context
5. Repeats until text response (no more function calls)

**Never rebuild contents from scratch between tool calls** - this breaks context and causes the model to "forget" what tools it already executed.

## Configuration

Environment variables in `.env`:
- `GEMINI_API_KEY`: Required for Gemini API
- `APP_ENV`: `development` or `production` (controls CORS, docs visibility)
- `DATABASE_URL`: SQLite connection string

## Adding New Tools

1. Create file in `app/services/tools/`
2. Extend `BaseTool` class
3. Add `@ToolRegistry.register` decorator
4. Implement `name`, `description`, `get_parameters_schema()`, and `execute()`
5. **Add to appropriate tool group** in `registry.py`:
   - `ROUTER_TOOLS`: Tools for intent detection phase
   - `KOSSODO_TOOLS`: Tools for sales conversations
   - `KOSSOMET_TOOLS`: Tools for services conversations
6. **Update the corresponding prompt** to teach Gemini when/how to use the new tool

**Example: Adding a tool for Kossodo only:**
```python
# 1. In registry.py, add to KOSSODO_TOOLS:
KOSSODO_TOOLS = ["save_contact", "save_inquiry", "end_conversation", "get_quote"]

# 2. In kossodo_prompt.py, add instructions:
# - When to call get_quote
# - What parameters to use
# - How to present the result to customer
```

## Code Style

- Line length: 100 characters (Black)
- Ruff rules: E, W, F, I, B, C4
- Async mode: All database and external service calls
