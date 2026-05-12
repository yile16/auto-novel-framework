"""Book-level finalizer — merges all arc states into the complete decomposition."""

from __future__ import annotations

import logging
import yaml

from config import DecomposeConfig
from llm.client import LLMClient, _load_prompt
from core.models.story import StoryDecomposition

logger = logging.getLogger(__name__)


class BookFinalizer:
    """
    Takes all arc-level accumulated states and produces the final, complete
    StoryDecomposition for the entire novel.
    """

    def __init__(self, config: DecomposeConfig):
        self.config = config
        self.llm = LLMClient(config)
        self._system_prompt: str | None = None

    @property
    def system_prompt(self) -> str:
        if self._system_prompt is None:
            self._system_prompt = _load_prompt("decompose/finalize_book")
        return self._system_prompt

    def finalize(
        self,
        arc_states: list[dict],
        title: str = "",
        author: str = "",
        total_chapters: int = 0,
    ) -> StoryDecomposition:
        """
        Merge all arc states into the final book decomposition.

        Args:
            arc_states: List of arc-level accumulated states (YAML dicts)
            title: Novel title
            author: Novel author
            total_chapters: Total number of chapters

        Returns:
            Complete StoryDecomposition model
        """
        # Build the user message with all arc states
        arc_yamls = []
        for i, state in enumerate(arc_states):
            yaml_str = yaml.dump(state, allow_unicode=True, sort_keys=False)
            arc_yamls.append(f"### 弧段 {i + 1}\n```yaml\n{yaml_str}\n```")

        all_arcs_text = "\n\n".join(arc_yamls)

        user_message = (
            f"书名: {title}\n"
            f"作者: {author}\n"
            f"总章节数: {total_chapters}\n\n"
            f"以下是所有弧段的累积状态，请合并为完整的全书拆解文档：\n\n"
            f"{all_arcs_text}"
        )

        logger.info("Finalizing book decomposition from %d arc states", len(arc_states))
        result = self.llm.extract_yaml(self.system_prompt, user_message)

        # Add metadata
        result["title"] = title
        result["author"] = author
        result["total_chapters"] = total_chapters

        logger.info("Book finalization complete")
        return StoryDecomposition.model_validate(result)
