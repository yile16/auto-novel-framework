"""World setting schema models — power systems, locations, factions, items."""

from pydantic import BaseModel, Field


class PowerStage(BaseModel):
    name: str
    levels: str = ""
    description: str = ""


class RuleDiscovery(BaseModel):
    chapter: int
    rule: str
    revealed_through: str = ""


class PowerSystem(BaseModel):
    name: str = ""
    stages: list[PowerStage] = Field(default_factory=list)
    special_rules: list[str] = Field(default_factory=list)
    rule_discovery_timeline: list[RuleDiscovery] = Field(default_factory=list)


class FacTimelineEntry(BaseModel):
    chapter: int
    event: str


class Faction(BaseModel):
    name: str
    type: str = ""  # 正道宗门, 魔教, 散修联盟, etc.
    description: str = ""
    key_members: list[str] = Field(default_factory=list)
    timeline: list[FacTimelineEntry] = Field(default_factory=list)


class LocationEvent(BaseModel):
    chapter: int
    event: str


class Location(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)
    type: str = ""  # 城市, 宗门, 秘境, 建筑, etc.
    description: str = ""
    atmosphere: str = ""
    parent: str = ""
    sub_locations: list[str] = Field(default_factory=list)
    first_chapter: int = 0
    appearances: list[int] = Field(default_factory=list)
    events_here: list[LocationEvent] = Field(default_factory=list)


class RevealedAbility(BaseModel):
    chapter: int
    ability: str
    context: str = ""


class SpecialItem(BaseModel):
    name: str
    first_chapter: int = 0
    revealed_abilities: list[RevealedAbility] = Field(default_factory=list)


class CheatStage(BaseModel):
    """A stage in the golden finger / cheat system evolution."""
    stage: str = ""  # e.g. 初始觉醒, 第一次进化
    chapter: int
    form_description: str = ""  # what the cheat looks like at this stage
    new_functions: list[str] = Field(default_factory=list)
    limitations: str = ""  # what the cheat CAN'T do


class CheatSystem(BaseModel):
    """Golden finger / cheat system evolution log."""
    name: str = ""  # e.g. 系统, 混沌珠, 血脉
    evolution_stages: list[CheatStage] = Field(default_factory=list)


class WorldSetting(BaseModel):
    world_name: str = ""
    world_type: str = ""  # 东方玄幻, 西方奇幻, 都市, 科幻, etc.
    era: str = ""
    power_system: PowerSystem = Field(default_factory=PowerSystem)
    cheat_system: CheatSystem = Field(default_factory=CheatSystem)
    factions: list[Faction] = Field(default_factory=list)
    locations: list[Location] = Field(default_factory=list)
    special_items: list[SpecialItem] = Field(default_factory=list)
