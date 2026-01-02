# Cost Optimization Strategies

Production strategies to minimize Gemini API costs while maintaining quality.

## Cost Breakdown

| Token Type | Cost (2.5 Flash) | With Explicit Cache |
|------------|------------------|---------------------|
| Input tokens | $0.075/1M | - |
| Cached input | - | $0.0075/1M (90% off) |
| Output tokens | $0.30/1M | $0.30/1M (no discount) |
| Cache storage | - | $1.00/1M tokens/hour |

## Strategy 1: System Prompt Optimization

### Minimize System Prompt Size

```python
# ❌ Verbose (high token count)
SYSTEM_PROMPT = """
You are an AI assistant for Grupo Kossodo, a company that has two business 
units. The first business unit is called KOSSODO and it handles equipment 
sales including balances, microscopes, and laboratory instruments. The second
business unit is called KOSSOMET and it provides technical services such as
calibration, maintenance, repair, and certification services...
"""

# ✅ Concise (lower token count, same information)
SYSTEM_PROMPT = """
Eres el asistente de Grupo Kossodo:
- KOSSODO: Venta de equipos (balanzas, microscopios, instrumentos de laboratorio)
- KOSSOMET: Servicios técnicos (calibración, mantenimiento, reparación, certificación)

Infiere la unidad de negocio según el contexto. Nunca preguntes "¿es Kossodo o Kossomet?"
"""
```

### Token Count Comparison

```python
def estimate_cost_savings():
    verbose_tokens = 150
    concise_tokens = 80
    requests_per_day = 1000
    
    # Without caching
    verbose_cost = verbose_tokens * requests_per_day * 30 * 0.075 / 1_000_000
    concise_cost = concise_tokens * requests_per_day * 30 * 0.075 / 1_000_000
    
    print(f"Monthly savings from concise prompt: ${verbose_cost - concise_cost:.2f}")
```

## Strategy 2: Cache TTL Optimization

### Calculate Optimal TTL

```python
def calculate_optimal_ttl(
    cached_tokens: int,
    requests_per_hour: float,
    input_cost_per_m: float = 0.075,
    cache_cost_per_m_hour: float = 1.00
):
    """
    Find TTL where caching becomes cost-effective.
    
    Break-even: cache_storage_cost = input_cost_savings
    """
    # Cost without caching (per hour)
    no_cache_cost = cached_tokens * requests_per_hour * input_cost_per_m / 1_000_000
    
    # Cost with caching (per hour)
    # 90% discount on input + storage cost
    cached_input_cost = cached_tokens * requests_per_hour * (input_cost_per_m * 0.1) / 1_000_000
    storage_cost = cached_tokens * cache_cost_per_m_hour / 1_000_000
    cache_cost = cached_input_cost + storage_cost
    
    savings_per_hour = no_cache_cost - cache_cost
    
    return {
        "no_cache_hourly": no_cache_cost,
        "cache_hourly": cache_cost,
        "savings_hourly": savings_per_hour,
        "cache_worthwhile": savings_per_hour > 0,
        "min_requests_for_savings": storage_cost / (input_cost_per_m * 0.9 / 1_000_000 * cached_tokens)
    }

# Example
result = calculate_optimal_ttl(
    cached_tokens=5000,  # 5K token system prompt
    requests_per_hour=50
)
# Result shows if caching is worthwhile for your traffic
```

### Dynamic TTL Based on Traffic

```python
class AdaptiveCacheManager:
    def __init__(self, cache_service):
        self.cache_service = cache_service
        self.request_count = 0
        self.last_reset = datetime.now()
    
    def record_request(self):
        self.request_count += 1
    
    async def adjust_ttl(self):
        """Adjust TTL based on traffic patterns."""
        hours_elapsed = (datetime.now() - self.last_reset).total_seconds() / 3600
        requests_per_hour = self.request_count / max(hours_elapsed, 0.1)
        
        # High traffic: extend TTL
        if requests_per_hour > 100:
            self.cache_service.extend_ttl("main", 7200)  # 2 hours
        # Medium traffic: standard TTL
        elif requests_per_hour > 20:
            self.cache_service.extend_ttl("main", 3600)  # 1 hour
        # Low traffic: short TTL or no cache
        else:
            self.cache_service.extend_ttl("main", 1800)  # 30 min
```

## Strategy 3: Response Length Control

```python
# Limit output tokens to reduce costs
config = types.GenerateContentConfig(
    cached_content=cache_name,
    max_output_tokens=500,  # Limit response length
    stop_sequences=["---"]   # Stop early if pattern found
)
```

### System Prompt Instructions for Brevity

```python
SYSTEM_PROMPT += """
Reglas de respuesta:
- Respuestas concisas (máximo 3 oraciones por turno)
- No repetir información ya proporcionada
- Ir directo al punto sin preámbulos
"""
```

## Strategy 4: Batch Processing

For non-real-time tasks, use batch processing:

```python
# Batch multiple queries
async def batch_process(queries: list[str]):
    """Process multiple queries efficiently."""
    contents = []
    for q in queries:
        contents.append(types.Content(
            role="user",
            parts=[types.Part(text=q)]
        ))
        contents.append(types.Content(
            role="model",
            parts=[types.Part(text="[SEPARATOR]")]
        ))
    
    # Single API call for all queries
    response = await client.models.generate_content(
        model="gemini-2.5-flash-001",
        contents=contents,
        config=types.GenerateContentConfig(
            cached_content=cache_name
        )
    )
    
    # Parse responses
    return response.text.split("[SEPARATOR]")
```

## Strategy 5: Monitoring Dashboard

```python
# app/services/cost_monitor.py
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class UsageMetrics:
    timestamp: datetime
    prompt_tokens: int
    cached_tokens: int
    output_tokens: int
    
    @property
    def cache_hit_ratio(self) -> float:
        return self.cached_tokens / self.prompt_tokens if self.prompt_tokens else 0
    
    @property
    def estimated_cost(self) -> float:
        # Costs per million tokens
        input_rate = 0.075
        cached_rate = 0.0075
        output_rate = 0.30
        
        uncached_input = self.prompt_tokens - self.cached_tokens
        
        return (
            (uncached_input * input_rate / 1_000_000) +
            (self.cached_tokens * cached_rate / 1_000_000) +
            (self.output_tokens * output_rate / 1_000_000)
        )

class CostMonitor:
    def __init__(self):
        self.metrics: list[UsageMetrics] = []
    
    def record(self, response):
        meta = response.usage_metadata
        self.metrics.append(UsageMetrics(
            timestamp=datetime.now(),
            prompt_tokens=meta.prompt_token_count,
            cached_tokens=getattr(meta, 'cached_content_token_count', 0),
            output_tokens=meta.candidates_token_count
        ))
    
    def daily_summary(self) -> dict:
        today = datetime.now().date()
        today_metrics = [m for m in self.metrics if m.timestamp.date() == today]
        
        total_cost = sum(m.estimated_cost for m in today_metrics)
        total_cached = sum(m.cached_tokens for m in today_metrics)
        total_prompt = sum(m.prompt_tokens for m in today_metrics)
        
        return {
            "date": str(today),
            "requests": len(today_metrics),
            "total_cost_usd": round(total_cost, 4),
            "cache_hit_ratio": total_cached / total_prompt if total_prompt else 0,
            "estimated_savings_usd": round(
                total_cached * (0.075 - 0.0075) / 1_000_000, 4
            )
        }
```

## Cost Optimization Checklist

- [ ] System prompt under 3,000 tokens
- [ ] Explicit caching for prompts >2,048 tokens
- [ ] TTL matched to traffic patterns
- [ ] Output token limits configured
- [ ] Cache hit ratio monitored (target >80%)
- [ ] Daily cost alerts configured
- [ ] Concise response instructions in prompt
- [ ] Batch processing for non-real-time tasks
