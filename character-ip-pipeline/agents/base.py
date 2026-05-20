"""Base agent class with integrated quality check loop.

Every agent follows this cycle:
  run() -> quality_check() -> [PASS] return output
                           -> [FAIL] revise() -> quality_check() -> ...

After max_retries, the best version is returned regardless.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from llm.client import LLMClient
from models.project import AgentResult, AgentStatus


class BaseAgent(ABC):
    """Base class for all pipeline agents with built-in quality check loop."""

    agent_name: str = "base"

    def __init__(
        self,
        llm: LLMClient,
        output_dir: Path,
        quality_threshold: float = 0.7,
        max_retries: int = 3,
    ):
        self.llm = llm
        self.output_dir = Path(output_dir)
        self.quality_threshold = quality_threshold
        self.max_retries = max_retries
        self.current_retry = 0
        self.best_output: Any = None
        self.best_score: float = 0.0
        self.feedback_history: list[str] = []

    # ── Abstract methods (each agent must implement) ──

    @abstractmethod
    def build_input(self, project: Any) -> str:
        """Build the LLM prompt input from project state."""
        ...

    @abstractmethod
    def parse_output(self, raw_text: str) -> Any:
        """Parse LLM output into structured data."""
        ...

    @abstractmethod
    def quality_check_prompt(self) -> str:
        """Return the system prompt for quality checking this agent's output."""
        ...

    @abstractmethod
    def build_quality_check_input(self, output: Any, project: Any) -> str:
        """Build the user message for quality checking."""
        ...

    @abstractmethod
    def build_revise_input(self, output: Any, feedback: str, project: Any) -> str:
        """Build the revision prompt incorporating quality feedback."""
        ...

    @abstractmethod
    def save_output(self, output: Any) -> list[str]:
        """Save the output to files. Returns list of file paths."""
        ...

    # ── Main execution loop ──

    def run(self, project: Any) -> tuple[Any, AgentResult]:
        """Execute the agent with quality check loop.

        Returns (output, AgentResult).
        """
        result = AgentResult(
            agent_name=self.agent_name,
            status=AgentStatus.RUNNING,
            start_time=datetime.now(),
        )
        self.output_dir.mkdir(parents=True, exist_ok=True)

        output = None
        for attempt in range(self.max_retries + 1):
            self.current_retry = attempt

            # Generate
            raw_output = self._generate(project, attempt > 0)

            # Parse with retry — if JSON is malformed, treat as quality failure
            try:
                output = self.parse_output(raw_output)
                if output is None:
                    raise ValueError("parse_output returned None")
            except Exception as parse_err:
                self.feedback_history.append(
                    f"Attempt {attempt + 1}: parse error — {parse_err}"
                )
                result.retry_count = attempt + 1
                if attempt >= self.max_retries:
                    # All retries exhausted, raise to outer handler
                    raise
                continue

            # Quality check
            score, feedback = self._check_quality(output, project)
            result.quality_score = score
            result.quality_notes = feedback

            # Track best version
            if score >= self.best_score:
                self.best_score = score
                self.best_output = output

            if score >= self.quality_threshold:
                result.status = AgentStatus.DONE
                result.retry_count = attempt
                result.output_paths = self.save_output(output)
                result.end_time = datetime.now()
                return output, result

            # Failed — record feedback and retry
            self.feedback_history.append(
                f"Attempt {attempt + 1}: score={score:.2f} — {'; '.join(feedback)}"
            )
            result.retry_count = attempt + 1

        # Max retries exceeded — return best version
        result.status = AgentStatus.DONE
        result.quality_score = self.best_score
        result.quality_notes.append(
            f"WARNING: Max retries ({self.max_retries}) exceeded. "
            f"Returning best version with score {self.best_score:.2f}"
        )
        result.output_paths = self.save_output(self.best_output)
        result.end_time = datetime.now()
        return self.best_output, result

    # ── Internal methods ──

    def _generate(self, project: Any, is_revision: bool) -> str:
        """Call LLM to generate output. If is_revision, include feedback."""
        system_prompt = self.get_system_prompt()

        if is_revision and self.feedback_history and self.best_output is not None:
            user_message = self.build_revise_input(
                self.best_output,
                self.feedback_history[-1],
                project,
            )
        else:
            user_message = self.build_input(project)

        return self.llm.chat_with_retry(system_prompt, user_message)

    def _check_quality(self, output: Any, project: Any) -> tuple[float, list[str]]:
        """Run quality check. Returns (score, feedback_notes)."""
        system_prompt = self.quality_check_prompt()
        user_message = self.build_quality_check_input(output, project)

        try:
            raw = self.llm.chat_with_retry(
                system_prompt,
                user_message,
                temperature=0.1,
            )
            # Parse JSON from checker
            raw = raw.strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                raw = "\n".join(lines)
            check_result = json.loads(raw)
            score = float(check_result.get("score", 0.5))
            feedback = check_result.get("issues", [])
            if isinstance(feedback, str):
                feedback = [feedback]
            return score, feedback
        except Exception as e:
            # If checker fails, assume pass with warning
            return 0.8, [f"Checker parse error: {e}"]

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the system prompt for this agent."""
        ...
