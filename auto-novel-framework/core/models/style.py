"""Style schema models — narrative style, pacing, hooks."""

from pydantic import BaseModel, Field


class Style(BaseModel):
    narrative_pov: str = ""
    pacing_patterns: list[str] = Field(default_factory=list)
    average_chapter_length: str = ""
    climax_spacing: str = ""
    dialogue_style: str = ""
    description_density: str = ""
    hook_patterns: list[str] = Field(default_factory=list)
