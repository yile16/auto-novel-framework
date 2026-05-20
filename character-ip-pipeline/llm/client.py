"""LLM client — wraps OpenAI-compatible APIs with retry, JSON/YAML extraction.

Supports: Groq (free), DeepSeek, OpenAI, and any OpenAI-compatible API.
"""

from __future__ import annotations

import json
import os
import time
import yaml
from pathlib import Path
from typing import Any

from openai import OpenAI

# API presets for quick setup
API_PRESETS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "models": ["llama-3.1-8b-instant", "qwen-2.5-32b", "deepseek-r1-distill-llama-70b"],
        "default_model": "llama-3.1-8b-instant",
        "max_tokens": 4096,
        "description": "Groq — 免费使用，注册即得 API Key (console.groq.com)",
        "signup_url": "https://console.groq.com",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "default_model": "deepseek-chat",
        "max_tokens": 4096,
        "description": "DeepSeek — 新用户赠送免费额度 (platform.deepseek.com)",
        "signup_url": "https://platform.deepseek.com",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini"],
        "default_model": "gpt-4o-mini",
        "max_tokens": 4096,
        "description": "OpenAI — 付费使用",
        "signup_url": "https://platform.openai.com",
    },
}


def load_prompt(*parts: str) -> str:
    """Load a prompt template from the prompts directory. E.g. load_prompt('research', 'structure_profile')"""
    prompt_path = Path(__file__).parent.parent / "prompts" / Path(*parts).with_suffix(".txt")
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Prompt file not found: {prompt_path}")


class LLMClient:
    """Wrapper around OpenAI-compatible APIs with multi-provider support."""

    def __init__(
        self,
        model: str = "llama-3.1-8b-instant",
        max_tokens: int = 4096,
        temperature: float = 0.3,
        base_url: str = "https://api.groq.com/openai/v1",
        api_key: str = "",
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.base_url = base_url
        self.api_key = api_key
        self._client = None

    @classmethod
    def from_preset(cls, preset_name: str, api_key: str, model: str | None = None) -> "LLMClient":
        """Create a client from a named preset (groq, deepseek, openai)."""
        preset = API_PRESETS.get(preset_name)
        if not preset:
            raise ValueError(f"Unknown preset: {preset_name}. Available: {list(API_PRESETS.keys())}")
        return cls(
            model=model or preset["default_model"],
            max_tokens=preset.get("max_tokens", 4096),
            base_url=preset["base_url"],
            api_key=api_key,
        )

    def _ensure_client(self):
        if self._client is not None:
            return
        api_key = self.api_key or os.environ.get(
            "GROQ_API_KEY", ""
        ) or os.environ.get("DEEPSEEK_API_KEY", "") or os.environ.get(
            "OPENAI_API_KEY", ""
        ) or os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError(
                "API key not set. Set GROQ_API_KEY or DEEPSEEK_API_KEY env var, "
                "or get a free key at https://console.groq.com"
            )
        self._client = OpenAI(api_key=api_key, base_url=self.base_url)

    def chat(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """Send a message and return the text response."""
        self._ensure_client()
        response = self._client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            temperature=temperature if temperature is not None else self.temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        return response.choices[0].message.content or ""

    def chat_with_retry(
        self,
        system_prompt: str,
        user_message: str,
        max_retries: int = 3,
        **kwargs: Any,
    ) -> str:
        """Chat with automatic retry on transient errors."""
        for attempt in range(max_retries):
            try:
                return self.chat(system_prompt, user_message, **kwargs)
            except Exception as e:
                err_str = str(e).lower()
                is_rate_limit = any(
                    k in err_str for k in ("rate_limit", "rate limit", "429")
                )
                is_server_err = any(
                    k in err_str
                    for k in ("500", "502", "503", "504", "server_error", "internal_error")
                )
                if (is_rate_limit or is_server_err) and attempt < max_retries - 1:
                    wait = 2**attempt * 5
                    time.sleep(wait)
                else:
                    raise

    def extract_json(
        self, system_prompt: str, user_message: str, **kwargs: Any
    ) -> dict:
        """Extract structured JSON from a chat response."""
        full_system = (
            system_prompt
            + "\n\nIMPORTANT: Output ONLY valid JSON. No markdown fences, no commentary."
        )
        text = self.chat_with_retry(full_system, user_message, **kwargs)
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        return json.loads(text)

    def extract_yaml(
        self, system_prompt: str, user_message: str, **kwargs: Any
    ) -> dict:
        """Extract structured YAML from a chat response."""
        full_system = (
            system_prompt
            + "\n\nIMPORTANT: Output ONLY valid YAML. No markdown fences, no commentary."
        )
        text = self.chat_with_retry(full_system, user_message, **kwargs)
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError:
            # Retry with fix-it prompt
            fix_prompt = (
                "The following YAML has syntax errors. Fix ONLY the YAML syntax "
                "(unclosed quotes, bad indentation, etc.) without changing any content. "
                "Output ONLY the corrected YAML:\n\n" + text
            )
            try:
                fixed = self.chat(
                    "You are a YAML syntax validator. Fix the YAML syntax errors.",
                    fix_prompt,
                    max_tokens=self.max_tokens,
                    temperature=0,
                )
                fixed = fixed.strip()
                if fixed.startswith("```"):
                    flines = fixed.split("\n")
                    if flines[0].startswith("```"):
                        flines = flines[1:]
                    if flines and flines[-1].strip() == "```":
                        flines = flines[:-1]
                    fixed = "\n".join(flines)
                return yaml.safe_load(fixed)
            except Exception:
                raise RuntimeError(
                    f"Failed to parse YAML from LLM response. "
                    f"Raw output (first 500 chars): {text[:500]}"
                )
