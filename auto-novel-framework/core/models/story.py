"""Combined story decomposition model — the complete output of the decompose pipeline."""

from pydantic import BaseModel, Field

from .character import Character
from .plot import Plot
from .setting import WorldSetting
from .relationship import Relationships
from .style import Style


class StoryDecomposition(BaseModel):
    """The complete decomposition of a novel — all 5 blocks."""
    title: str = ""
    author: str = ""
    total_chapters: int = 0
    characters: list[Character] = Field(default_factory=list)
    plot: Plot = Field(default_factory=Plot)
    world_setting: WorldSetting = Field(default_factory=WorldSetting)
    relationships: Relationships = Field(default_factory=Relationships)
    style: Style = Field(default_factory=Style)


class RawChapterExtraction(BaseModel):
    """Raw extraction from a single chapter — before merging into accumulated state."""
    chapter: int
    chapter_title: str = ""

    # New characters introduced or appearing in this chapter
    characters: list[Character] = Field(default_factory=list)

    # Events in this chapter (causal chains: trigger -> action -> consequence)
    events: list = Field(default_factory=list)  # list of dict, loosely structured

    # Locations appearing in this chapter
    locations: list = Field(default_factory=list)

    # World rules / setting info revealed in this chapter
    setting_revelations: list = Field(default_factory=list)

    # Relationship changes in this chapter
    relationship_changes: list = Field(default_factory=list)

    # Ability gains in this chapter
    ability_gains: list = Field(default_factory=list)

    # Foreshadowing: new holes planted or old ones resolved
    foreshadowing: list = Field(default_factory=list)

    # Combat power level changes for protagonist
    combat_power_changes: list = Field(default_factory=list)

    # Asset/inventory changes in this chapter
    asset_changes: list = Field(default_factory=list)

    # Golden finger/cheat system changes
    cheat_system_changes: list = Field(default_factory=list)
