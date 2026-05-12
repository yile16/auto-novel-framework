"""Character schema models with full timeline support."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class OccupationChange(BaseModel):
    chapter: int
    occupation: str


class Identity(BaseModel):
    background: str = ""
    occupation_timeline: list[OccupationChange] = Field(default_factory=list)


class StaticTraits(BaseModel):
    personality: str = ""
    appearance: str = ""


class AbilityGain(BaseModel):
    chapter: int
    abilities: list[str] = Field(default_factory=list)
    context: str = ""


class RelationshipSnapshot(BaseModel):
    """A snapshot of relationships at a specific chapter."""
    chapter: int
    relations: dict[str, str] = Field(default_factory=dict)
    # e.g. {"林婉儿": "初遇，印象深刻", "王胖子": "结识为友"}


class CharacterState(BaseModel):
    """Character state at a specific chapter — core for novel reconstruction."""
    chapter: int
    emotional: str = ""
    goal: str = ""
    location: str = ""
    key_actions: list[str] = Field(default_factory=list)


class CharacterArc(BaseModel):
    growth_trajectory: str = ""
    core_conflict: str = ""
    key_turning_points: list[str] = Field(default_factory=list)


class CombatPowerProgression(BaseModel):
    """Character combat power level at a specific chapter."""
    chapter: int
    level: str = ""  # e.g. 筑基期, 金丹期
    sub_level: str = ""  # e.g. 初期/中期/后期/圆满
    change: str = ""  # description of what changed


class Character(BaseModel):
    name: str
    role: str = ""  # protagonist, antagonist, supporting, etc.
    aliases: list[str] = Field(default_factory=list)
    identity: Identity = Field(default_factory=Identity)
    static_traits: StaticTraits = Field(default_factory=StaticTraits)
    abilities_timeline: list[AbilityGain] = Field(default_factory=list)
    state_timeline: list[CharacterState] = Field(default_factory=list)
    relationship_snapshots: list[RelationshipSnapshot] = Field(default_factory=list)
    combat_power_timeline: list[CombatPowerProgression] = Field(default_factory=list)
    arc: CharacterArc = Field(default_factory=CharacterArc)
    introduction_chapter: int = 0
    death_chapter: Optional[int] = None
