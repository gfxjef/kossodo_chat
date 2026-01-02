# Context Caching Patterns

Complete implementation guide for Gemini context caching in production chatbots.

## Explicit Cache Service

```python
# app/services/cache_service.py
from google import genai
from google.genai import types
import datetime
import logging

logger = logging.getLogger(__name__)

class CacheService:
    """Manages explicit caches for system prompts."""
    
    def __init__(self, api_key: str = None):
        self.client = genai.Client(api_key=api_key) if api_key else genai.Client()
        self._caches = {}
    
    def create_cache(
        self,
        cache_id: str,
        system_instruction: str,
        model: str = "gemini-2.5-flash-001",
        ttl_seconds: int = 3600,
        display_name: str = None
    ) -> str:
        """
        Create an explicit cache for a system prompt.
        
        Args:
            cache_id: Internal identifier for this cache
            system_instruction: The system prompt to cache
            model: Model version (must use explicit suffix like -001)
            ttl_seconds: Time to live in seconds (default 1 hour)
            display_name: Human-readable name for the cache
        
        Returns:
            Cache resource name for use in generate_content
        """
        cache = self.client.caches.create(
            model=model,
            config=types.CreateCachedContentConfig(
                display_name=display_name or f"cache-{cache_id}",
                system_instruction=system_instruction,
                ttl=f"{ttl_seconds}s",
            )
        )
        
        self._caches[cache_id] = cache
        logger.info(f"Created cache '{cache_id}': {cache.name}")
        logger.info(f"Cached tokens: {cache.usage_metadata.total_token_count}")
        
        return cache.name
    
    def get_cache_name(self, cache_id: str) -> str | None:
        """Get cache resource name by internal ID."""
        cache = self._caches.get(cache_id)
        return cache.name if cache else None
    
    def extend_ttl(self, cache_id: str, additional_seconds: int = 3600):
        """Extend cache TTL."""
        cache = self._caches.get(cache_id)
        if not cache:
            raise ValueError(f"Cache '{cache_id}' not found")
        
        self.client.caches.update(
            name=cache.name,
            config=types.UpdateCachedContentConfig(
                ttl=f"{additional_seconds}s"
            )
        )
        logger.info(f"Extended TTL for '{cache_id}' by {additional_seconds}s")
    
    def delete_cache(self, cache_id: str):
        """Delete a cache."""
        cache = self._caches.get(cache_id)
        if cache:
            self.client.caches.delete(cache.name)
            del self._caches[cache_id]
            logger.info(f"Deleted cache '{cache_id}'")
    
    def list_all_caches(self) -> list:
        """List all caches from the API."""
        return list(self.client.caches.list())
    
    def cleanup_expired(self):
        """Remove expired caches from internal tracking."""
        for cache_id in list(self._caches.keys()):
            try:
                self.client.caches.get(name=self._caches[cache_id].name)
            except Exception:
                del self._caches[cache_id]
                logger.info(f"Removed expired cache '{cache_id}'")
```

## Integration with GeminiService

```python
# app/services/gemini.py
from google import genai
from google.genai import types
from app.services.cache_service import CacheService

class GeminiService:
    def __init__(self, system_prompt: str):
        self.client = genai.Client()
        self.model = "gemini-2.5-flash-001"
        self.system_prompt = system_prompt
        self.cache_service = CacheService()
        self._cache_name = None
    
    async def initialize(self):
        """Initialize the service with cached system prompt."""
        self._cache_name = self.cache_service.create_cache(
            cache_id="main-chatbot",
            system_instruction=self.system_prompt,
            model=self.model,
            ttl_seconds=3600,
            display_name="Kossodo Chatbot System Prompt"
        )
    
    async def generate_with_cache(
        self,
        contents: list,
        tools: list = None
    ):
        """Generate content using cached system prompt."""
        config = types.GenerateContentConfig(
            cached_content=self._cache_name
        )
        
        if tools:
            config.tools = tools
        
        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=config
        )
        
        # Log cache performance
        self._log_cache_metrics(response)
        
        return response
    
    def _log_cache_metrics(self, response):
        """Log caching metrics for monitoring."""
        meta = response.usage_metadata
        cached = getattr(meta, 'cached_content_token_count', 0)
        prompt = meta.prompt_token_count
        output = meta.candidates_token_count
        
        if cached > 0:
            cache_ratio = (cached / prompt) * 100
            # 90% discount on cached tokens
            effective_cost_ratio = ((prompt - cached) + cached * 0.1) / prompt * 100
            
            logger.info(
                f"Tokens - Prompt: {prompt}, Cached: {cached} ({cache_ratio:.1f}%), "
                f"Output: {output}, Effective cost: {effective_cost_ratio:.1f}%"
            )
```

## Cache Lifecycle Management

```python
# Startup: Initialize cache
@app.on_event("startup")
async def startup():
    gemini_service = GeminiService(SYSTEM_PROMPT)
    await gemini_service.initialize()
    app.state.gemini = gemini_service

# Periodic: Extend TTL before expiration
@app.on_event("startup")
@repeat_every(seconds=1800)  # Every 30 min
async def extend_cache_ttl():
    app.state.gemini.cache_service.extend_ttl("main-chatbot", 3600)

# Shutdown: Clean up
@app.on_event("shutdown")
async def shutdown():
    app.state.gemini.cache_service.delete_cache("main-chatbot")
```

## When to Use Each Caching Type

| Scenario | Caching Type | Reason |
|----------|--------------|--------|
| Development/testing | Implicit | No setup needed |
| Production with large system prompt | Explicit | Guaranteed 90% savings |
| Sporadic traffic | Implicit | No storage costs |
| High-volume (>100 req/hour) | Explicit | Predictable costs |
| Multiple distinct chatbots | Explicit per bot | Isolated caches |

## Token Count Requirements

Before creating a cache, verify token count:

```python
def count_tokens(text: str, model: str = "gemini-2.5-flash-001") -> int:
    """Count tokens in text."""
    response = client.models.count_tokens(
        model=model,
        contents=text
    )
    return response.total_tokens

# Check before caching
tokens = count_tokens(SYSTEM_PROMPT)
if tokens < 2048:
    logger.warning(f"System prompt ({tokens} tokens) below cache minimum (2048)")
    # Fall back to implicit caching
```

## Error Handling

```python
async def generate_with_fallback(self, contents: list):
    """Generate with cache, fall back to non-cached if cache fails."""
    try:
        return await self.generate_with_cache(contents)
    except Exception as e:
        if "cache" in str(e).lower():
            logger.warning(f"Cache error, falling back: {e}")
            # Regenerate without cache
            return self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_prompt
                )
            )
        raise
```
