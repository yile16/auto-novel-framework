"""Plot schema models with thread/stage/chapter-event hierarchy, foreshadowing, assets, combat power."""

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


class ForeshadowingItem(BaseModel):
    """A foreshadowing/suspense element — a 'hole' that gets planted and later resolved."""
    id: str  # unique identifier within the book
    description: str
    planted_chapter: int
    involved_characters: list[str] = Field(default_factory=list)
    estimated_purpose: str = ""  # what this suspense is expected to achieve
    resolved_chapter: int = 0  # 0 means unresolved
    resolution: str = ""  # how it was resolved
    resolution_quality: str = ""  # 圆满/勉强/未回收


class AssetChange(BaseModel):
    """A change in the protagonist's assets/inventory."""
    chapter: int
    operation: str = ""  # 获得/消耗/升级/转让
    item_name: str
    quantity: str = ""
    source_or_target: str = ""  # where it came from or where it went


class CombatPowerState(BaseModel):
    """Combat power level at a specific chapter."""
    chapter: int
    level: str  # e.g. 筑基期, 金丹期
    sub_level: str = ""  # e.g. 初期/中期/后期/圆满
    change_description: str = ""  # e.g. ➡️ 服用地火丹后突破至金丹初期


class CausalChain(BaseModel):
    """A compressed causal chain: trigger -> action -> consequence."""
    chapter: int
    chain: str  # "[触发因] -> [核心行动] -> [状态改变结果]"
    involved_characters: list[str] = Field(default_factory=list)


class Plot(BaseModel):
    threads: list[PlotThread] = Field(default_factory=list)
    chapter_events: list[ChapterEvent] = Field(default_factory=list)
    twists: list[PlotTwist] = Field(default_factory=list)
    foreshadowing_tracking: list[ForeshadowingItem] = Field(default_factory=list)
    asset_timeline: list[AssetChange] = Field(default_factory=list)
    combat_power_timeline: list[CombatPowerState] = Field(default_factory=list)
    causal_chains: list[CausalChain] = Field(default_factory=list)
