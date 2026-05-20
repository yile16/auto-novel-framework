"""Models for song-related agents: angle planning, lyrics, voice, song production."""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class SongAngle(BaseModel):
    """A candidate song angle/topic."""
    angle_id: str = ""
    title: str = ""  # e.g. "自由与惩罚", "五百年的独白"
    based_on_event: str = ""  # which life event this angle draws from
    emotional_core: str = ""  # 核心情绪
    narrative_pov: str = "first"  # first / third person
    target_feeling: str = ""  # 听完后听众应该有什么感受
    hook_sentence: str = ""  # 一句话钩子
    contrast_angle: str = ""  # 反差感描述
    visual_motif: str = ""  # 视觉母题


class SongBrief(BaseModel):
    """Selected song direction from Agent 2: Angle Planner."""
    selected_angle: SongAngle = Field(default_factory=SongAngle)
    candidate_angles: list[SongAngle] = Field(default_factory=list)
    emotional_arc: str = ""  # e.g. "压抑→爆发→释然"
    suggested_genre: str = ""  # 建议曲风
    suggested_tempo: str = ""  # 建议节奏：慢/中/快
    creative_direction: str = ""  # 创意方向详细描述


class LyricsSection(BaseModel):
    """A section of lyrics."""
    section_type: str = ""  # intro/verse1/pre-chorus/chorus/verse2/bridge/outro
    lines: list[str] = Field(default_factory=list)
    emotion: str = ""
    imagery_used: list[str] = Field(default_factory=list)


class Lyrics(BaseModel):
    """Complete lyrics from Agent 3: Lyrics Generator."""
    version: int = 1
    title: str = ""
    character_name: str = ""
    angle: str = ""
    sections: list[LyricsSection] = Field(default_factory=list)
    full_text: str = ""  # 完整歌词文本
    rhyme_scheme: str = ""  # 韵脚方案
    imagery_vocabulary: list[str] = Field(default_factory=list)  # 意象词汇表
    language_style: str = ""  # 语言风格：古风/白话/口语/诗意
    character_voice_score: float = Field(default=0.0)  # 角色贴合度自评


class VoiceDesign(BaseModel):
    """Voice character design from Agent 4: Voice Designer."""
    gender: str = ""  # male/female/neutral
    age_range: str = ""  # 少年/青年/中年/沧桑
    timbre: str = ""  # 声线特质
    singing_style: str = ""  # 唱法
    vocal_range: str = ""  # 音域
    emotional_expression: str = ""  # 情感表达特点
    voice_description: str = ""  # 完整音色描述（避免名人名）
    copyright_safety_notes: str = ""  # 版权安全说明
    presets: list[dict] = Field(default_factory=list)  # 多套音色预设


class SongStyle(BaseModel):
    """Music style parameters for song production."""
    genre: str = ""  # 曲风
    sub_genre: str = ""  # 子风格
    bpm: int = 0  # 节奏
    key: str = ""  # 调性
    instruments: list[str] = Field(default_factory=list)  # 主要乐器
    mood_dynamics: str = ""  # 情绪动态描述
    reference_style: str = ""  # 风格参考（不指名具体歌曲，用风格描述）


class SongProduction(BaseModel):
    """Song production output from Agent 5."""
    lyrics: Lyrics = Field(default_factory=Lyrics)
    voice_design: VoiceDesign = Field(default_factory=VoiceDesign)
    style: SongStyle = Field(default_factory=SongStyle)
    suno_prompt: str = ""  # 给 Suno/Udio 的完整提示词
    generated_variants: list[str] = Field(default_factory=list)  # 音频文件路径列表
    selected_variant: str = ""  # 最终选定版本
    audio_path: str = ""  # 最终音频文件路径
    metadata: dict = Field(default_factory=dict)
