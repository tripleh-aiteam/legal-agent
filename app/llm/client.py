"""LiteLLM 기반 멀티모델 LLM 클라이언트."""

import json
import logging
from typing import Any

import litellm

from app.config import settings

logger = logging.getLogger(__name__)

# LiteLLM 설정
litellm.set_verbose = False
litellm.success_callback = ["langsmith"]
litellm.failure_callback = ["langsmith"]


def _is_anthropic_model(model: str) -> bool:
    """모델명으로 Anthropic 모델 여부를 판별."""
    return model.startswith("claude") or model.startswith("anthropic/")


def _apply_cache_control(messages: list[dict], model: str) -> list[dict]:
    """Anthropic 모델의 시스템 메시지에 cache_control 헤더를 적용.

    프롬프트 캐싱을 통해 반복 호출 시 시스템 프롬프트 비용을 90% 절감.
    """
    if not _is_anthropic_model(model):
        return messages

    result = []
    for msg in messages:
        if msg["role"] == "system" and isinstance(msg["content"], str):
            result.append({
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": msg["content"],
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            })
        else:
            result.append(msg)
    return result


async def call_llm(
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.0,
    max_tokens: int = 4096,
    response_format: dict | None = None,
) -> dict[str, Any]:
    """LLM 호출 공통 함수.

    Args:
        model: 모델명 (e.g., "claude-sonnet-4-20250514", "gpt-4o-mini")
        system_prompt: 시스템 프롬프트
        user_prompt: 사용자 프롬프트
        temperature: 생성 온도
        max_tokens: 최대 토큰 수
        response_format: JSON 모드 등 응답 형식

    Returns:
        {"content": str, "usage": dict, "model": str}
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    messages = _apply_cache_control(messages, model)

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    if response_format:
        kwargs["response_format"] = response_format

    response = await litellm.acompletion(**kwargs)

    usage = response.usage
    usage_dict: dict[str, Any] = {
        "input_tokens": usage.prompt_tokens,
        "output_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
    }

    # Anthropic 프롬프트 캐시 히트 모니터링
    cached_tokens = getattr(usage, "cache_read_input_tokens", None)
    cache_creation_tokens = getattr(usage, "cache_creation_input_tokens", None)
    if cached_tokens:
        usage_dict["cached_tokens"] = cached_tokens
        logger.info("Prompt cache hit: %d tokens cached", cached_tokens)
    if cache_creation_tokens:
        usage_dict["cache_creation_input_tokens"] = cache_creation_tokens
        logger.info("Prompt cache created: %d tokens stored", cache_creation_tokens)
    if _is_anthropic_model(model) and not cached_tokens and not cache_creation_tokens:
        logger.warning("Anthropic cache miss: no cache metrics in response")

    return {
        "content": response.choices[0].message.content,
        "usage": usage_dict,
        "model": response.model,
    }


async def call_llm_json(
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """LLM 호출 후 JSON 파싱하여 반환."""
    result = await call_llm(
        model=model,
        system_prompt=system_prompt + "\n\n반드시 유효한 JSON으로만 응답하세요.",
        user_prompt=user_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )

    try:
        parsed = json.loads(result["content"])
    except json.JSONDecodeError:
        # JSON 파싱 실패 시 마크다운 코드블록 내 JSON 추출 시도
        content = result["content"]
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        parsed = json.loads(content)

    return {
        "data": parsed,
        "usage": result["usage"],
        "model": result["model"],
    }


async def get_embedding(text: str) -> list[float]:
    """텍스트 임베딩 생성."""
    response = await litellm.aembedding(
        model=settings.embedding_model,
        input=[text],
    )
    return response.data[0]["embedding"]


async def get_embeddings_batch(texts: list[str], batch_size: int = 100) -> list[list[float]]:
    """배치 임베딩 생성."""
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = await litellm.aembedding(
            model=settings.embedding_model,
            input=batch,
        )
        batch_embeddings = [item["embedding"] for item in response.data]
        all_embeddings.extend(batch_embeddings)

    return all_embeddings
