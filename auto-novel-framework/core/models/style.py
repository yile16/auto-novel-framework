"""Style schema models — narrative style, pacing, hooks."""

from typing import Any

from pydantic import BaseModel, Field, field_validator


class Style(BaseModel):
    narrative_pov: str = ""
    pacing_patterns: list[str] = Field(default_factory=list)
    average_chapter_length: Any = ""
    climax_spacing: Any = ""
    dialogue_style: str = ""
    description_density: str = ""
    hook_patterns: list[str] = Field(default_factory=list)

    @field_validator("average_chapter_length", "climax_spacing", mode="before")
    @classmethod
    def coerce_to_str(cls, v):
        if v is None:
            return ""
        return str(v)
