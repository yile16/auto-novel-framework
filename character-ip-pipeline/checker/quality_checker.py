"""Universal quality checker — can check any agent's output with specialized criteria."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from llm.client import LLMClient, load_prompt


class QualityChecker:
    """Standalone quality checker that evaluates any agent's output.

    Each agent type has a dedicated check prompt in prompts/checker/check_<agent>.txt
    """

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def check(
        self,
        agent_name: str,
        output: Any,
        context: dict | None = None,
    ) -> tuple[float, list[str]]:
        """Run quality check for an agent's output.

        Args:
            agent_name: e.g. 'research', 'angle', 'lyrics', 'voice', 'song', 'visual', 'storyboard', 'video'
            output: The agent's output data (will be serialized for the checker)
            context: Additional context (character name, song brief, etc.)

        Returns:
            (score 0-1, list of issue descriptions)
        """
        system_prompt = self._load_check_prompt(agent_name)
        user_message = self._build_check_input(agent_name, output, context or {})

        try:
            raw = self.llm.chat_with_retry(system_prompt, user_message, temperature=0.1)
            raw = raw.strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                raw = "\n".join(lines)
            result = json.loads(raw)
            score = float(result.get("score", 0.5))
            # Clamp score to [0, 1]
            score = max(0.0, min(1.0, score))
            issues = result.get("issues", [])
            if isinstance(issues, str):
                issues = [issues]
            # Also collect pass points if available
            passes = result.get("passes", [])
            return score, issues + [f"[PASS] {p}" for p in passes]
        except Exception as e:
            return 0.5, [f"Checker error: {e}"]

    def _load_check_prompt(self, agent_name: str) -> str:
        """Load the quality check prompt for a specific agent."""
        try:
            return load_prompt("checker", f"check_{agent_name}")
        except FileNotFoundError:
            # Fall back to generic check prompt
            return load_prompt("checker", "check_generic")

    def _build_check_input(
        self, agent_name: str, output: Any, context: dict
    ) -> str:
        """Build the check input message."""
        parts = []

        if context:
            parts.append("## 上下文信息")
            for key, value in context.items():
                parts.append(f"- **{key}**: {value}")

        parts.append("## Agent 输出内容")
        parts.append("```json")
        parts.append(self._serialize_output(output))
        parts.append("```")
        parts.append("")
        parts.append("请对该输出进行质量评分（0.0-1.0），并列出通过项和问题项。")

        return "\n".join(parts)

    def _serialize_output(self, output: Any) -> str:
        """Serialize output to JSON string for the checker."""
        if hasattr(output, "model_dump"):
            return json.dumps(output.model_dump(), ensure_ascii=False, indent=2, default=str)
        elif isinstance(output, dict):
            return json.dumps(output, ensure_ascii=False, indent=2, default=str)
        elif isinstance(output, list):
            items = []
            for item in output:
                if hasattr(item, "model_dump"):
                    items.append(item.model_dump())
                else:
                    items.append(item)
            return json.dumps(items, ensure_ascii=False, indent=2, default=str)
        else:
            return str(output)
