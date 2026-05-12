"""Arc-level merger — combines chapter extractions into aggregated arc state."""

from __future__ import annotations

import json
import logging
import yaml

from config import DecomposeConfig
from llm.client import LLMClient, _load_prompt
from core.models.story import RawChapterExtraction, StoryDecomposition

logger = logging.getLogger(__name__)


def _raw_extractions_to_json(extractions: list[RawChapterExtraction]) -> str:
    """Convert a list of raw extractions to a compact JSON string for the LLM."""
    data = []
    for ext in extractions:
        entry = {
            "chapter": ext.chapter,
            "chapter_title": ext.chapter_title,
            "characters": [
                c.model_dump(exclude_none=True) for c in ext.characters
            ],
            "events": ext.events,
            "locations": ext.locations,
            "setting_revelations": ext.setting_revelations,
            "relationship_changes": ext.relationship_changes,
            "ability_gains": ext.ability_gains,
            "foreshadowing": ext.foreshadowing,
            "combat_power_changes": ext.combat_power_changes,
            "asset_changes": ext.asset_changes,
            "cheat_system_changes": ext.cheat_system_changes,
        }
        data.append(entry)
    return json.dumps(data, ensure_ascii=False, indent=2)


class ArcMerger:
    """
    Merges chapter-level raw extractions into arc-level accumulated state.

    Processes 10-15 chapters at a time. Can also merge a new batch into
    an existing accumulated state from a previous arc.
    """

    def __init__(self, config: DecomposeConfig):
        self.config = config
        self.llm = LLMClient(config)
        self._system_prompt: str | None = None

    @property
    def system_prompt(self) -> str:
        if self._system_prompt is None:
            self._system_prompt = _load_prompt("decompose/merge_arc")
        return self._system_prompt

    def merge_new_arc(
        self,
        extractions: list[RawChapterExtraction],
        previous_state_yaml: str | None = None,
    ) -> dict:
        """
        Merge a batch of chapter extractions into arc state.

        Args:
            extractions: Raw chapter extractions for this arc (10-15 chapters)
            previous_state_yaml: YAML string of accumulated state from previous arcs

        Returns:
            Parsed dict of the merged arc state
        """
        start_ch = extractions[0].chapter
        end_ch = extractions[-1].chapter

        extractions_json = _raw_extractions_to_json(extractions)

        if previous_state_yaml:
            user_message = (
                f"## 已有累积状态（前几个弧段的合并结果）\n\n"
                f"```yaml\n{previous_state_yaml}\n```\n\n"
                f"## 第 {start_ch}-{end_ch} 章的原始提取数据\n\n"
                f"```json\n{extractions_json}\n```\n\n"
                f"请将新章节的信息合并到已有累积状态中，输出更新后的完整 YAML。"
            )
        else:
            user_message = (
                f"这是第一个弧段（第 {start_ch}-{end_ch} 章）的原始提取数据。"
                f"请将它们合并为统一的弧段状态。\n\n"
                f"```json\n{extractions_json}\n```"
            )

        result = self.llm.extract_yaml(self.system_prompt, user_message)
        logger.info(f"Arc merge complete: chapters {start_ch}-{end_ch}")
        return result

    def merge_all_arcs_sequentially(
        self,
        extraction_batches: list[list[RawChapterExtraction]],
    ) -> list[dict]:
        """
        Merge extraction batches sequentially, carrying state forward.

        Each batch (arc) is merged with the accumulated state from all previous arcs.
        Returns a list of arc states, one per batch.
        """
        arc_states: list[dict] = []
        previous_yaml: str | None = None

        for i, batch in enumerate(extraction_batches):
            logger.info(f"Merging arc {i + 1}/{len(extraction_batches)} "
                        f"(chapters {batch[0].chapter}-{batch[-1].chapter})")
            state = self.merge_new_arc(batch, previous_yaml)
            arc_states.append(state)
            previous_yaml = yaml.dump(state, allow_unicode=True, sort_keys=False)

        return arc_states
