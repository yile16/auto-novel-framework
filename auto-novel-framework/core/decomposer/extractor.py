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

    def extract_one(self, chunk: Chunk) -> RawChapterExtraction:
        """
        Extract structured data from a single chapter chunk.
        """
        user_message = (
            f"章节号: {chunk.chapter_start}\n"
            f"章节标题: {chunk.title}\n\n"
            f"--- 章节正文 ---\n{chunk.text}"
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
        )

    def extract_batch(
        self, chunks: list[Chunk], max_workers: int | None = None
    ) -> list[RawChapterExtraction]:
        """
        Extract from multiple chapters in parallel.
        Results are returned in chunk order.
        """
        if max_workers is None:
            max_workers = self.config.max_parallel_extractions

        results: dict[int, RawChapterExtraction] = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(self.extract_one, chunk): chunk.index
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
