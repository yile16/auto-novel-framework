"""Relationship schema models — character relations and faction relations with evolution."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class RelationEvolution(BaseModel):
    chapter: int
    status: str


class CharacterRelation(BaseModel):
    from_char: str = Field(alias="from")
    to: str
    type: str = ""  # 道侣, 兄弟, 师徒, 仇敌, etc.
    start_chapter: int = 0
    end_chapter: Optional[int] = None
    evolution: list[RelationEvolution] = Field(default_factory=list)

    class Config:
        populate_by_name = True


class FacRelationTimeline(BaseModel):
    chapter: int
    event: str
    new_relation: str


class FactionRelation(BaseModel):
    factions: list[str] = Field(default_factory=list)
    relation: str = ""
    timeline: list[FacRelationTimeline] = Field(default_factory=list)


class Relationships(BaseModel):
    character_relations: list[CharacterRelation] = Field(default_factory=list)
    faction_relations: list[FactionRelation] = Field(default_factory=list)
