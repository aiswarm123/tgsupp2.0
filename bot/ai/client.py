from bot.config import settings

# Module-level singletons — initialized once at import time
if settings.ai_provider == "claude":
    from anthropic import AsyncAnthropic as _AsyncAnthropic
    _claude_client = _AsyncAnthropic(api_key=settings.ai_api_key)
    _openai_client = None
else:
    from openai import AsyncOpenAI as _AsyncOpenAI
    _claude_client = None
    _openai_client = _AsyncOpenAI(
        api_key=settings.ai_api_key,
        base_url=settings.ai_base_url or None,
    )


async def send_message(history: list[dict], system_prompt: str) -> str | None:
    """Send message to AI provider and return reply text, or None if AI is unavailable."""
    if not settings.ai_available:
        return None
    if settings.ai_provider == "claude":
        return await _send_claude(history, system_prompt)
    else:
        return await _send_openai(history, system_prompt)


async def _send_claude(history: list[dict], system_prompt: str) -> str:
    response = await _claude_client.messages.create(
        model=settings.ai_model,
        max_tokens=1024,
        system=system_prompt,
        messages=history,
        timeout=30,
    )
    return response.content[0].text


async def _send_openai(history: list[dict], system_prompt: str) -> str:
    messages = [{"role": "system", "content": system_prompt}] + history
    response = await _openai_client.chat.completions.create(
        model=settings.ai_model,
        messages=messages,
        timeout=30,
    )
    return response.choices[0].message.content
