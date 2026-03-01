import json
import re

from openai import AsyncAzureOpenAI

from app.config import settings

_client: AsyncAzureOpenAI | None = None


def get_client() -> AsyncAzureOpenAI:
    global _client
    if _client is None:
        _client = AsyncAzureOpenAI(
            api_key=settings.azure_api_key,
            azure_endpoint=settings.azure_endpoint,
            api_version=settings.azure_api_version,
        )
    return _client


async def chat_mini(
    messages: list[dict],
    max_tokens: int = 4096,
    reasoning_effort: str = "low",
    json_mode: bool = False,
) -> str:
    client = get_client()
    kwargs: dict = {
        "model": settings.azure_deployment_mini,
        "messages": messages,
        "max_completion_tokens": max_tokens,
        "reasoning_effort": reasoning_effort,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    response = await client.chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""


async def chat_full(
    messages: list[dict],
    max_tokens: int = 16384,
    reasoning_effort: str = "high",
    json_mode: bool = False,
) -> str:
    client = get_client()
    kwargs: dict = {
        "model": settings.azure_deployment_full,
        "messages": messages,
        "max_completion_tokens": max_tokens,
        "reasoning_effort": reasoning_effort,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    response = await client.chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""


def extract_json(text: str) -> dict:
    """Extract a JSON object from model output, handling markdown fences and stray text."""
    text = text.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0].strip()
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Find the outermost JSON object with regex
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Could not extract JSON from model response: {text[:200]}")
