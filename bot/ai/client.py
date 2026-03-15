from typing import Any

from bot.config import settings

# Module-level singletons — initialized once at import time based on provider
_anthropic_client = None
_openai_client = None

if settings.AI_PROVIDER == "claude":
    from anthropic import AsyncAnthropic

    _anthropic_client = AsyncAnthropic(api_key=settings.AI_API_KEY)
else:
    from openai import AsyncOpenAI

    _openai_client = AsyncOpenAI(
        api_key=settings.AI_API_KEY,
        base_url=settings.AI_BASE_URL or None,
    )


async def send_message(history: list[dict[str, Any]], system_prompt: str) -> str:
    """Send conversation history to the configured AI provider and return the reply text."""
    if settings.AI_PROVIDER == "claude":
        response = await _anthropic_client.messages.create(
            model=settings.AI_MODEL,
            max_tokens=1024,
            system=system_prompt,
            messages=history,
        )
        return response.content[0].text
    else:
        messages = [{"role": "system", "content": system_prompt}] + history
        response = await _openai_client.chat.completions.create(
            model=settings.AI_MODEL,
            messages=messages,
        )
        return response.choices[0].message.content
