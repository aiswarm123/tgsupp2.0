from bot.config import settings


async def send_message(history: list[dict], system_prompt: str) -> str:
    """Send message to AI provider and return reply text.

    Args:
        history: List of {"role": "user"/"assistant", "content": "..."} dicts.
        system_prompt: System prompt for the AI.

    Returns:
        AI reply text.
    """
    if settings.ai_provider == "claude":
        return await _send_claude(history, system_prompt)
    else:
        return await _send_openai(history, system_prompt)


async def _send_claude(history: list[dict], system_prompt: str) -> str:
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.ai_api_key)
    response = await client.messages.create(
        model=settings.ai_model,
        max_tokens=1024,
        system=system_prompt,
        messages=history,
    )
    return response.content[0].text


async def _send_openai(history: list[dict], system_prompt: str) -> str:
    from openai import AsyncOpenAI

    kwargs = {"api_key": settings.ai_api_key}
    if settings.ai_base_url:
        kwargs["base_url"] = settings.ai_base_url

    client = AsyncOpenAI(**kwargs)
    messages = [{"role": "system", "content": system_prompt}] + history
    response = await client.chat.completions.create(
        model=settings.ai_model,
        messages=messages,
    )
    return response.choices[0].message.content
