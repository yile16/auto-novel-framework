"""Per-chapter raw extraction engine."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import DecomposeConfig
from llm.client import LLMClient, _load_prompt
from core.models.story import RawChapterExtraction
from core.models.character import (
    Character, CharacterState, Identity, StaticTraits, AbilityGain,
)
from utils.text import Chunk

logger = logging.getLogger(__name__)


def _parse_character(data: dict) -> Character:
    """Parse a raw character dict into a Character model. Handles LLM format variations."""
    if isinstance(data, str):
        return Character(name=data)

    ch_num = data.get("_chapter", 0)

    # chapter_state might be dict or string
    cs = data.get("chapter_state", {})
    if isinstance(cs, str):
        state = CharacterState(chapter=ch_num, emotional=cs)
    elif isinstance(cs, dict):
        state = CharacterState(
            chapter=ch_num,
            emotional=cs.get("emotional", ""),
            goal=cs.get("goal", ""),
            location=cs.get("location", ""),
            key_actions=cs.get("key_actions", []),
        )
    else:
        state = CharacterState(chapter=ch_num)

    # new_traits might be a string or a dict with personality/appearance
    traits = data.get("new_traits", {})
    if isinstance(traits, str):
        static = StaticTraits(personality=traits, appearance="")
    elif isinstance(traits, dict):
        static = StaticTraits(
            personality=traits.get("personality", ""),
            appearance=traits.get("appearance", ""),
        )
    else:
        static = StaticTraits()

    # ability_changes — highly variable LLM output, normalize aggressively
    ab_changes = data.get("ability_changes", [])
    if not ab_changes:
        ab_changes = data.get("abilities", [])
    if isinstance(ab_changes, str):
        ab_changes = [ab_changes]
    abilities_timeline = []
    if ab_changes and isinstance(ab_changes, list) and len(ab_changes) > 0:
        if isinstance(ab_changes[0], str):
            abilities_timeline.append(AbilityGain(
                chapter=ch_num,
                abilities=ab_changes,
            ))
        elif isinstance(ab_changes[0], dict):
            for ab in ab_changes:
                raw_abs = ab.get("abilities", ab.get("ability", []))
                if isinstance(raw_abs, str):
                    raw_abs = [raw_abs]
                if not isinstance(raw_abs, list):
                    raw_abs = []
                abilities_timeline.append(AbilityGain(
                    chapter=ab.get("chapter", ch_num),
                    abilities=raw_abs,
                    context=ab.get("context", ""),
                ))

    first = data.get("first_appearance", False)
    return Character(
        name=data.get("name", ""),
        role=data.get("role", ""),
        introduction_chapter=ch_num if first else 0,
        static_traits=static,
        state_timeline=[state],
        abilities_timeline=abilities_timeline,
    )


def _parse_location(data: dict) -> dict:
    """Parse a raw location dict (returns dict for raw extraction)."""
    if isinstance(data, str):
        return {"name": data}
    return {
        "name": data.get("name", ""),
        "type": data.get("type", ""),
        "description": data.get("description", ""),
        "atmosphere": data.get("atmosphere", ""),
        "parent": data.get("parent", ""),
    }


class ChapterExtractor:
    """Extracts structured data from a single chapter using LLM."""

    def __init__(self, config: DecomposeConfig):
        self.config = config
        self.llm = LLMClient(config)
        self._system_prompt: str | None = None

    @property
    def system_prompt(self) -> str:
        if self._system_prompt is None:
            self._system_prompt = _load_prompt("decompose/extract_chapter")
        return self._system_prompt

    def extract_one(self, chunk: Chunk, previous_context: str = "") -> RawChapterExtraction:
        """
        Extract structured data from a single chapter chunk.

        Args:
            chunk: The chapter chunk to extract from.
            previous_context: Summary of previous extractions to carry context forward.
        """
        user_message = (
            f"章节号: {chunk.chapter_start}\n"
            f"章节标题: {chunk.title}\n\n"
            f"--- 章节正文 ---\n{chunk.text}"
        )
        if previous_context:
            user_message = (
                f"## 前序章节关键信息（上下文接力，请在此基础上继续提取）\n"
                f"{previous_context}\n\n"
                f"---\n\n"
                + user_message
            )

        raw = self.llm.extract_json(self.system_prompt, user_message)

        ch_num = chunk.chapter_start

        # Attach chapter number to sub-items for tracking
        raw_chars = raw.get("characters", [])
        if isinstance(raw_chars, list):
            for c in raw_chars:
                if isinstance(c, dict):
                    c["_chapter"] = ch_num

        raw_events = raw.get("events", [])
        if isinstance(raw_events, list):
            for e in raw_events:
                if isinstance(e, dict):
                    e["chapter"] = ch_num

        characters = [_parse_character(c) for c in raw_chars if isinstance(c, (dict, str))]
        locations_data = [_parse_location(loc) for loc in raw.get("locations", []) if isinstance(loc, (dict, str))]

        return RawChapterExtraction(
            chapter=ch_num,
            chapter_title=chunk.title,
            characters=characters,
            events=raw.get("events", []),
            locations=locations_data,
            setting_revelations=raw.get("setting_revelations", []),
            relationship_changes=raw.get("relationship_changes", []),
            ability_gains=raw.get("ability_gains", []),
            foreshadowing=raw.get("foreshadowing", []),
            combat_power_changes=raw.get("combat_power_changes", []),
            asset_changes=raw.get("asset_changes", []),
            cheat_system_changes=raw.get("cheat_system_changes", []),
        )

    def extract_batch(
        self, chunks: list[Chunk], max_workers: int | None = None, previous_context: str = ""
    ) -> list[RawChapterExtraction]:
        """
        Extract from multiple chapters in parallel.
        Provides context relay to each chunk.
        Results are returned in chunk order.
        """
        if max_workers is None:
            max_workers = self.config.max_parallel_extractions

        results: dict[int, RawChapterExtraction] = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(self.extract_one, chunk, previous_context): chunk.index
                for chunk in chunks
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                    logger.info(f"Chapter extraction complete: chunk {idx}")
                except Exception as e:
                    logger.error(f"Failed to extract chunk {idx}: {e}")

        return [results[i] for i in sorted(results)]

    def build_context_summary(self, extractions: list[RawChapterExtraction], max_chars: int = 6000) -> str:
        """
        Build a compact context summary from previous extractions for relay to next chunk.
        Focuses on: characters, key events, foreshadowing, combat power state, active settings.
        """
        if not extractions:
            return ""

        lines = []
        # Collect unresolved foreshadowing
        foreshadowing = []
        # Last known combat power
        last_combat = None
        # Active characters
        chars_seen = set()

        for ext in extractions:
            for c in ext.characters:
                if c.name not in chars_seen:
                    chars_seen.add(c.name)
                    lines.append(f"- 角色 {c.name}（{c.role or '未知定位'}）登场于第{ext.chapter}章")
            for f_item in (ext.foreshadowing or []):
                if isinstance(f_item, dict) and f_item.get("type") == "新挖的坑":
                    foreshadowing.append(f"- [未回收] 第{ext.chapter}章挖坑：{f_item.get('description', '')}")
                elif isinstance(f_item, dict) and f_item.get("type") == "已回收的坑":
                    foreshadowing.append(f"- [已回收] 第{ext.chapter}章填坑：{f_item.get('description', '')}（回收方式：{f_item.get('resolution', '')}）")
            for cp in (ext.combat_power_changes or []):
                if isinstance(cp, dict):
                    last_combat = f"第{ext.chapter}章：{cp.get('level_after', '?')}（{cp.get('change_description', '')}）"

        if chars_seen:
            lines.insert(0, f"## 已登场角色（{len(chars_seen)}人）")
        if foreshadowing:
            lines.append(f"\n## 伏笔状态（{len(foreshadowing)}条）")
            lines.extend(foreshadowing[-10:])  # keep last 10
        if last_combat:
            lines.append(f"\n## 主角当前战力\n{last_combat}")

        summary = "\n".join(lines)
        if len(summary) > max_chars:
            summary = summary[-max_chars:]
        return summary
