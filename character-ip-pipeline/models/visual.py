"""Models for visual/video agents: character visual design, storyboard, video."""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class VisualStyle(BaseModel):
    """A visual style option for the character."""
    style_name: str = ""  # 写实/水墨/赛博/暗黑/国潮
    face_description: str = ""  # 面部特征
    hair_style: str = ""
    costume: str = ""
    color_scheme: list[str] = Field(default_factory=list)
    signature_props: list[str] = Field(default_factory=list)
    overall_vibe: str = ""
    image_prompt: str = ""  # 可直接用于生图的 prompt


class VisualDesign(BaseModel):
    """Character visual design from Agent 6."""
    character_name: str = ""
    style_options: list[VisualStyle] = Field(default_factory=list)
    selected_style: str = ""
    reference_images: list[str] = Field(default_factory=list)  # 参考图路径
    consistency_anchor: dict = Field(default_factory=dict)  # 形象一致性锚点 {prompt_prefix, seed, negative_prompt}
    character_sheet_prompt: str = ""  # 角色设定图 prompt
    expression_variants: list[str] = Field(default_factory=list)  # 不同表情的 prompt


class StoryboardShot(BaseModel):
    """A single shot in the storyboard."""
    shot_id: str = ""
    duration_sec: float = 0.0  # 时长（秒）
    shot_type: str = ""  # 远景/全景/中景/近景/特写
    camera_movement: str = ""  # 静态/慢推/摇镜/拉远/跟随
    visual_description: str = ""  # 画面描述（中文）
    character_pose: str = ""  # 角色姿态
    lighting: str = ""  # 光影描述
    color_tone: str = ""  # 色调
    emotion: str = ""  # 情绪关键词
    transition_from_prev: str = ""  # 转场方式
    lyrics_line: str = ""  # 对应歌词行
    reference_image_hint: str = ""  # 参考图搜索关键词
    image_generation_prompt: str = ""  # 用于生图的 prompt


class Storyboard(BaseModel):
    """Complete storyboard from Agent 7.1."""
    song_title: str = ""
    total_duration_sec: float = 0.0
    shots: list[StoryboardShot] = Field(default_factory=list)
    visual_theme: str = ""  # 整体视觉主题
    color_arc: str = ""  # 色调变化弧线
    key_frames: list[int] = Field(default_factory=list)  # 关键帧 shot_id 列表


class VideoProduction(BaseModel):
    """Video production output from Agent 7."""
    storyboard: Storyboard = Field(default_factory=Storyboard)
    shot_images: list[str] = Field(default_factory=list)  # 各镜画面文件路径
    video_clips: list[str] = Field(default_factory=list)  # 各镜视频片段路径
    final_video_path: str = ""  # 最终 MV 路径
    subtitle_track: str = ""  # 字幕文件路径
    edit_timeline: dict = Field(default_factory=dict)  # 剪辑时间线
