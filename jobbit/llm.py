"""Provider-agnostic structured LLM calls (Gemini or Claude), selected by `llm.provider` in settings.yaml.

Callers pass a JSON schema (as a tool definition) and get back a dict matching it.
If the active provider's API key is not set, `is_stubbed()` is True and callers use their stub
implementations instead. The pipeline refuses to persist stubbed output (dry-run only).
"""
from __future__ import annotations

import json
import logging
import time
from functools import lru_cache

from .config import secrets, settings

log = logging.getLogger(__name__)


def provider() -> str:
    return settings()["llm"]["provider"]


class QuotaExhausted(RuntimeError):
    """Every configured model for this task is out of daily quota. Stop the stage; retry next run."""


class ModelsOverloaded(QuotaExhausted):
    """Every configured model is temporarily overloaded (503). Handled like quota: retry next run."""


def models_for(task: str) -> list[str]:
    """task: 'scoring' | 'tailoring'. Settings may give one model or a fallback list."""
    m = settings()["llm"]["models"][provider()][task]
    return [m] if isinstance(m, str) else list(m)


def is_stubbed() -> bool:
    s = secrets()
    return (s.gemini_key if provider() == "gemini" else s.anthropic_key) is None


def call_tool(*, task: str, system: str, cached_context: str, prompt: str, tool: dict, max_tokens: int) -> dict:
    """Return a dict matching tool['input_schema']. `cached_context` is the master profile (identical every call)."""
    if provider() == "gemini":
        return _call_gemini(models=models_for(task), system=f"{system}\n{cached_context}", prompt=prompt,
                            tool=tool, max_tokens=max_tokens)
    return _call_anthropic(model=models_for(task)[0], system=system, cached_context=cached_context,
                           prompt=prompt, tool=tool, max_tokens=max_tokens)


# --------------------------------------------------------------------------- Gemini
_last_gemini_call = 0.0


@lru_cache
def _gemini():
    from google import genai

    return genai.Client(api_key=secrets().gemini_key)


_exhausted: set[str] = set()  # models out of daily quota for the rest of this process


def _is_daily_quota(e) -> bool:
    return e.code == 429 and "PerDay" in json.dumps(e.details, default=str)


def _call_gemini(*, models, system, prompt, tool, max_tokens) -> dict:
    """Try each model in order. Per-minute limits and overload (429/503) get short retries, then
    fall through to the next model; a daily-quota 429 marks the model exhausted immediately."""
    from google.genai import errors, types

    global _last_gemini_call
    min_interval = 60 / settings()["llm"]["gemini_requests_per_minute"]
    config = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",
        response_schema=tool["input_schema"],
        max_output_tokens=max_tokens,
        temperature=0.4,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    for model in [m for m in models if m not in _exhausted]:
        for attempt in range(3):
            wait = _last_gemini_call + min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            _last_gemini_call = time.monotonic()
            try:
                resp = _gemini().models.generate_content(model=model, contents=prompt, config=config)
            except errors.APIError as e:
                if _is_daily_quota(e) or e.code == 404:
                    log.warning("Gemini %s unavailable (%s); trying next model", model, e.code)
                    _exhausted.add(model)
                    break
                if e.code in (429, 500, 503) and attempt < 2:
                    delay = 15 * (attempt + 1)
                    log.warning("Gemini %s %s; retrying in %ss", model, e.code, delay)
                    time.sleep(delay)
                    continue
                if e.code in (429, 500, 503):
                    log.warning("Gemini %s still failing (%s); trying next model", model, e.code)
                    break
                raise
            cand = resp.candidates[0] if resp.candidates else None
            if cand is None or cand.finish_reason.name not in ("STOP", "FINISH_REASON_UNSPECIFIED"):
                raise RuntimeError(f"{tool['name']}: Gemini finished with {cand.finish_reason if cand else 'no candidates'}")
            u = resp.usage_metadata
            log.info("%s via %s: in=%s out=%s", tool["name"], model, u.prompt_token_count, u.candidates_token_count)
            return json.loads(resp.text)
    if all(m in _exhausted for m in models):
        raise QuotaExhausted(f"all models exhausted for today: {models}")
    raise ModelsOverloaded(f"{tool['name']}: all models overloaded: {models}")


# --------------------------------------------------------------------------- Anthropic
@lru_cache
def _anthropic():
    import anthropic

    return anthropic.Anthropic(api_key=secrets().anthropic_key, max_retries=4)


def _call_anthropic(*, model, system, cached_context, prompt, tool, max_tokens) -> dict:
    resp = _anthropic().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=[
            {"type": "text", "text": system},
            {"type": "text", "text": cached_context, "cache_control": {"type": "ephemeral"}},
        ],
        messages=[{"role": "user", "content": prompt}],
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
    )
    if resp.stop_reason == "max_tokens":
        raise RuntimeError(f"{tool['name']}: output truncated at max_tokens={max_tokens}")
    for block in resp.content:
        if block.type == "tool_use":
            u = resp.usage
            log.info("%s via %s: in=%s cached=%s out=%s", tool["name"], model,
                     u.input_tokens, getattr(u, "cache_read_input_tokens", 0), u.output_tokens)
            return block.input
    raise RuntimeError(f"{tool['name']}: model returned no tool call")
