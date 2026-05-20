"""Project model — tracks the entire pipeline state for a character."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

from .character import CharacterProfile, KeyMoment
from .song import SongBrief, Lyrics, VoiceDesign, SongProduction
from .visual import VisualDesign, Storyboard, VideoProduction


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    CHECKING = "checking"  # quality check in progress
    REVISING = "revising"  # failed check, revising
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class AgentResult(BaseModel):
    """Result from a single agent run."""
    agent_name: str = ""
    status: AgentStatus = AgentStatus.PENDING
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    retry_count: int = 0
    quality_score: float = 0.0
    quality_notes: list[str] = Field(default_factory=list)
    output_paths: list[str] = Field(default_factory=list)  # files produced
    error_message: str = ""


class Project(BaseModel):
    """Complete project state tracking the entire pipeline."""

    # Project identity
    project_id: str = ""
    character_name: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # Agent results
    agent_results: dict[str, AgentResult] = Field(default_factory=dict)

    # Data outputs (populated as agents complete)
    character_profile: Optional[CharacterProfile] = None
    key_moments: list[KeyMoment] = Field(default_factory=list)
    song_brief: Optional[SongBrief] = None
    lyrics: Optional[Lyrics] = None
    voice_design: Optional[VoiceDesign] = None
    song_production: Optional[SongProduction] = None
    visual_design: Optional[VisualDesign] = None
    storyboard: Optional[Storyboard] = None
    video_production: Optional[VideoProduction] = None

    # Narrative text (from Agent 1)
    character_narrative: str = ""

    @property
    def current_stage(self) -> str:
        """Which stage the project is at."""
        stage_order = [
            "research", "angle", "lyrics", "voice",
            "song", "visual", "video"
        ]
        for stage in stage_order:
            result = self.agent_results.get(stage)
            if result is None or result.status != AgentStatus.DONE:
                return stage
        return "complete"
