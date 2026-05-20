"""LLM client abstraction — supports DeepSeek (OpenAI-compatible) and Anthropic APIs."""

from __future__ import annotations

import json
import os
import time
import yaml
from pathlib import Path
from typing import Any

from openai import OpenAI

from config import DecomposeConfig


def _load_prompt(name: str) -> str:
    """Load a prompt template from the prompts directory."""
    prompt_path = Path(__file__).parent / "prompts" / f"{name}.txt"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Prompt file not found: {prompt_path}")


class LLMClient:
    """Wrapper around OpenAI-compatible / Anthropic APIs for structured novel decomposition."""

    def __init__(self, config: DecomposeConfig):
        self.config = config
        self._client = None  # lazy init on first use

    def _ensure_client(self):
        if self._client is not None:
            return
        api_key = self.config.api_key or os.environ.get("ANTHROPIC_API_KEY", "") or os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            raise ValueError(
                "API key not set. Set ANTHROPIC_API_KEY or DEEPSEEK_API_KEY env var, "
                "or pass api_key in config."
            )
        self._client = OpenAI(api_key=api_key, base_url=self.config.base_url)

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
            model=self.config.model,
            max_tokens=max_tokens or self.config.max_tokens,
            temperature=temperature or self.config.temperature,
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
                is_rate_limit = any(k in err_str for k in ("rate_limit", "rate limit", "429"))
                is_server_err = any(k in err_str for k in ("500", "502", "503", "504", "server_error", "internal_error"))
                if (is_rate_limit or is_server_err) and attempt < max_retries - 1:
                    wait = 2 ** attempt * 5
                    time.sleep(wait)
                else:
                    raise

    def extract_json(self, system_prompt: str, user_message: str, **kwargs: Any) -> dict:
        """Extract structured JSON from a chat response."""
        full_system = (
            system_prompt
            + "\n\nIMPORTANT: You must output ONLY valid JSON. No markdown fences, no commentary."
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

    def _repair_yaml(self, text: str) -> str:
        """Attempt to repair common YAML formatting issues from LLM output."""
        import re
        lines = text.split("\n")
        repaired = []
        for line in lines:
            # If line has unbalanced quotes, try to fix by closing them
            dq_count = line.count('"')
            sq_count = line.count("'")
            stripped = line.lstrip()
            # Fix unclosed double quotes in key: "value pattern
            if dq_count % 2 != 0 and ':"' in line:
                # Find the last unclosed double quote and close it
                line = line.rstrip() + '"'
            # Fix unclosed single quotes
            if sq_count % 2 != 0 and ":'" in line:
                line = line.rstrip() + "'"
            # Fix flow mappings with problematic characters
            if ":" in line and not stripped.startswith("#") and not stripped.startswith("- "):
                indent = line[:len(line) - len(stripped)]
                match = re.match(r'^([^:]+):\s*(.*)', stripped)
                if match:
                    key = match.group(1)
                    value = match.group(2)
                    if value and not value.startswith('"') and not value.startswith("'"):
                        if any(c in value for c in ('{', '}', '[', ']', '#', '&', '*', '!', '|', '>')):
                            value = f'"{value}"'
                    repaired.append(f"{indent}{key}: {value}")
                    continue
            repaired.append(line)
        return "\n".join(repaired)

    def extract_yaml(self, system_prompt: str, user_message: str, **kwargs: Any) -> dict:
        """Extract structured YAML from a chat response, returns parsed dict."""
        full_system = (
            system_prompt
            + "\n\nIMPORTANT: You must output ONLY valid YAML. No markdown fences, no commentary."
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
            try:
                repaired = self._repair_yaml(text)
                return yaml.safe_load(repaired)
            except yaml.YAMLError:
                # Last resort: retry with a fix-it prompt
                fix_prompt = (
                    "The following YAML has syntax errors. Fix ONLY the YAML syntax "
                    "(unclosed quotes, bad indentation, etc.) without changing any content. "
                    "Output ONLY the corrected YAML, no commentary:\n\n" + text
                )
                try:
                    fixed = self.chat(
                        "You are a YAML syntax validator. Fix the YAML syntax errors.",
                        fix_prompt,
                        max_tokens=self.config.max_tokens,
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
                        f"Failed to parse YAML from LLM response after repair attempts. "
                        f"Raw output (first 500 chars): {text[:500]}"
                    )
