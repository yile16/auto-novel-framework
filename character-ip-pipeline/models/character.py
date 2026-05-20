"""Character profile model — the central data type for the entire pipeline."""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class LifeEvent(BaseModel):
    """A key event in the character's life timeline."""
    time_label: str = ""  # e.g. "出生", "大闹天宫时期", "被压五行山"
    event_title: str = ""
    description: str = ""
    emotional_tone: str = ""  # 悲壮/热血/孤独/释然...
    visual_potential: int = Field(default=0, ge=0, le=10)  # 画面感评分
    song_potential: int = Field(default=0, ge=0, le=10)  # 歌曲改编潜力评分


class Relationship(BaseModel):
    """A relationship with another character."""
    name: str = ""
    relation_type: str = ""  # 师徒/朋友/敌人/爱人/亲人
    description: str = ""
    emotional_dynamic: str = ""  # 爱恨交织/忠诚/背叛/和解...


class CharacterProfile(BaseModel):
    """Complete character profile from Agent 1: Character Research."""

    # Basic info
    name: str = ""
    aliases: list[str] = Field(default_factory=list)
    origin: str = ""  # 来源：西游记原著/三国演义/历史人物...
    era: str = ""  # 时代背景
    identity: str = ""  # 身份：齐天大圣/美猴王/斗战胜佛

    # Appearance
    appearance: str = ""  # 外貌描述汇总
    appearance_variants: dict[str, str] = Field(default_factory=dict)  # 不同版本的外貌

    # Personality
    personality_traits: list[str] = Field(default_factory=list)  # 核心性格特质
    personality_contradictions: list[str] = Field(default_factory=list)  # 性格矛盾
    character_arc: str = ""  # 成长弧光描述

    # Life timeline
    life_events: list[LifeEvent] = Field(default_factory=list)
    highlight_moments: list[str] = Field(default_factory=list)  # 高光时刻
    lowlight_moments: list[str] = Field(default_factory=list)  # 至暗时刻

    # Relationships
    relationships: list[Relationship] = Field(default_factory=list)

    # Quotes & Voice
    classic_quotes: list[str] = Field(default_factory=list)  # 经典语录
    speech_style: str = ""  # 说话风格描述
    inner_voice: str = ""  # 内心独白风格

    # Symbols & Imagery
    signature_items: list[str] = Field(default_factory=list)  # 标志性物品
    signature_actions: list[str] = Field(default_factory=list)  # 标志性动作
    core_imagery: list[str] = Field(default_factory=list)  # 核心意象
    color_palette: list[str] = Field(default_factory=list)  # 代表色

    # Multi-perspective
    different_interpretations: list[str] = Field(default_factory=list)  # 不同解读视角
    controversies: list[str] = Field(default_factory=list)  # 争议点

    # Metadata
    research_sources: list[str] = Field(default_factory=list)  # 研究来源
    completeness_score: float = Field(default=0.0)  # 资料完整度 0-1


class KeyMoment(BaseModel):
    """A key moment extracted for content creation."""
    title: str = ""
    event: str = ""
    emotion: str = ""
    angle_hints: list[str] = Field(default_factory=list)  # 可用的歌曲角度
    visual_hints: list[str] = Field(default_factory=list)  # 可用的画面描述
    viral_score: int = Field(default=0, ge=0, le=10)
