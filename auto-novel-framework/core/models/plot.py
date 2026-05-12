"""Plot schema models with thread/stage/chapter-event hierarchy."""

from pydantic import BaseModel, Field


class KeyMilestone(BaseModel):
    chapter: int
    event: str


class PlotStage(BaseModel):
    stage: str
    chapters: list[int] = Field(default_factory=list)
    summary: str = ""
    key_milestones: list[KeyMilestone] = Field(default_factory=list)


class PlotThread(BaseModel):
    id: str
    name: str
    type: str = ""  # main, subplot, romance, revenge, etc.
    span: list[int] = Field(default_factory=list)  # [start_chapter, end_chapter]
    stages: list[PlotStage] = Field(default_factory=list)


class ChapterEvent(BaseModel):
    """Per-chapter event — the basis for chapter-by-chapter novel reconstruction."""
    chapter: int
    title: str = ""
    timeline_point: str = ""
    location: str = ""
    characters: list[str] = Field(default_factory=list)
    summary: str = ""
    cause: str = ""
    consequence: str = ""
    tone: str = ""
    key_moments: list[str] = Field(default_factory=list)


class PlotTwist(BaseModel):
    chapter: int
    event: str
    impact: str


class Plot(BaseModel):
    threads: list[PlotThread] = Field(default_factory=list)
    chapter_events: list[ChapterEvent] = Field(default_factory=list)
    twists: list[PlotTwist] = Field(default_factory=list)
