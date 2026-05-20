"""Agent 5: Song Producer — 歌曲制作

Designs music style and generates Suno/Udio prompt.
Handles music API integration and audio post-processing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.base import BaseAgent
from llm.client import load_prompt
from models.song import SongStyle, SongProduction, Lyrics, VoiceDesign
from models.project import Project


SONG_PRODUCER_SYSTEM = """你是一个专业的AI音乐制作人，专门为Suno AI等工具编写高质量的音乐生成提示词。

你的核心能力：
1. 根据角色气质选择最合适的曲风
2. 设计"主角乐器"——代表这个角色的核心乐器
3. 编写结构化、高质量的Suno提示词
4. 考虑BPM、调性、情绪动态的匹配

风格选择直觉（根据角色气质）：
- 反抗型角色 → 国风摇滚、史诗金属（力量、撕裂、不羁）
- 忠义型角色 → 大气国风、交响战歌（壮阔、仪式感、悲壮）
- 智慧型角色 → 古风电子、氛围音乐（空灵、深思、知性）
- 悲剧型角色 → 古风民谣、戏腔流行（脆弱、唯美、破碎）
- 热血型角色 → 交响摇滚、史诗金属（振奋、昂扬、大气）
- 内省型角色 → 极简钢琴、氛围电子（空旷、哲思、留白）

Suno提示词结构：
[风格标签] [genre, mood, instruments, vocal style]
[Intro]
...
[Verse 1]
...
[Pre-Chorus]
...
[Chorus - Powerful, belting]
...
[Verse 2]
...
[Bridge]
...
[Chorus]
...
[Outro]
..."""


class SongProducerAgent(BaseAgent):
    """Agent 5: Music production and Suno prompt generation."""

    agent_name = "song"

    def get_system_prompt(self) -> str:
        return SONG_PRODUCER_SYSTEM

    def build_input(self, project: Project) -> str:
        prompt = load_prompt("song", "design_style")

        parts = [prompt]

        if project.character_profile:
            p = project.character_profile
            parts.append(f"\n## 角色: {p.name}")
            parts.append(f"身份: {p.identity}")
            parts.append(f"性格: {', '.join(p.personality_traits)}")
            parts.append(f"核心意象: {', '.join(p.core_imagery)}")
            parts.append(f"代表色: {', '.join(p.color_palette)}")

        if project.song_brief:
            sb = project.song_brief
            parts.append(f"\n## 选题")
            parts.append(f"角度: {sb.selected_angle.title}")
            parts.append(f"核心情感: {sb.selected_angle.emotional_core}")
            parts.append(f"情绪弧线: {sb.emotional_arc}")
            parts.append(f"建议曲风: {sb.suggested_genre}")
            parts.append(f"建议节奏: {sb.suggested_tempo}")

        if project.lyrics:
            parts.append(f"\n## 歌词")
            parts.append(f"歌名: {project.lyrics.title}")
            parts.append(f"语言风格: {project.lyrics.language_style}")
            parts.append(f"韵脚方案: {project.lyrics.rhyme_scheme}")
            parts.append("\n完整歌词:")
            parts.append(project.lyrics.full_text)

        if project.voice_design:
            vd = project.voice_design
            parts.append(f"\n## 音色设计")
            parts.append(f"性别: {vd.gender}")
            parts.append(f"年龄: {vd.age_range}")
            parts.append(f"声线: {vd.timbre}")
            parts.append(f"唱法: {vd.singing_style}")
            parts.append(f"音色描述: {vd.voice_description}")
            # Include presets
            if vd.presets:
                parts.append("音色预设:")
                for preset in vd.presets:
                    parts.append(f"  - {preset.get('name', '')}: {preset.get('description', '')}")

        parts.append(f"\n请为 {project.character_name} 的歌曲设计音乐风格并生成Suno提示词。")
        return "\n".join(parts)

    def parse_output(self, raw_text: str) -> SongProduction:
        raw = raw_text.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw = "\n".join(lines)

        import re
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                raise ValueError(f"Failed to parse song production JSON: {raw[:300]}")
        style_data = data.get("style", {})

        return SongProduction(
            style=SongStyle(
                genre=style_data.get("genre", ""),
                sub_genre=style_data.get("sub_genre", ""),
                bpm=int(style_data.get("bpm", 0)),
                key=style_data.get("key", ""),
                instruments=style_data.get("instruments", []),
                mood_dynamics=style_data.get("mood_dynamics", ""),
                reference_style=style_data.get("reference_style", ""),
            ),
            suno_prompt=data.get("suno_prompt", ""),
            metadata=data,
        )

    def quality_check_prompt(self) -> str:
        return load_prompt("checker", "check_song")

    def build_quality_check_input(
        self, output: SongProduction, project: Project
    ) -> str:
        parts = [
            f"## 上下文\n角色: {project.character_name}\n",
            "## 歌曲制作方案",
            "```json",
            json.dumps(output.model_dump(), ensure_ascii=False, indent=2),
            "```",
            "请检查音乐制作方案。关注：风格是否贴合角色、Suno提示词结构是否正确。",
        ]
        return "\n".join(parts)

    def build_revise_input(
        self, output: SongProduction, feedback: str, project: Project
    ) -> str:
        parts = [
            self.build_input(project),
            "\n## 上一版歌曲制作方案（需要改进）",
            "```json",
            json.dumps(output.model_dump(), ensure_ascii=False, indent=2),
            "```",
            f"\n## 审核反馈\n{feedback}",
            "\n请根据反馈重新生成音乐制作方案。",
        ]
        return "\n".join(parts)

    def save_output(self, output: SongProduction) -> list[str]:
        paths = []
        # Save full production
        prod_path = self.output_dir / "song_production.json"
        prod_path.write_text(
            json.dumps(output.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        paths.append(str(prod_path))

        # Save Suno prompt separately
        prompt_path = self.output_dir / "suno_prompt.txt"
        prompt_path.write_text(output.suno_prompt, encoding="utf-8")
        paths.append(str(prompt_path))

        # Save metadata
        meta_path = self.output_dir / "song_metadata.json"
        meta_path.write_text(
            json.dumps(output.metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        paths.append(str(meta_path))
        return paths

    def generate_audio(
        self, output: SongProduction, output_dir: Path
    ) -> list[str]:
        """Generate audio using Suno/Udio API.

        This is a placeholder — actual API integration depends on
        Suno/Udio API availability. For now, saves the prompt for manual use.
        """
        import subprocess
        import sys

        audio_paths = []

        # Try to use suno-bark if available, otherwise just save the prompt
        try:
            # Placeholder for future Suno API integration
            pass
        except Exception:
            pass

        return audio_paths
