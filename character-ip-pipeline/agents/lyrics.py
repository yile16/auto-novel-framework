"""Agent 3: Lyrics Generator — 歌词生成

Generates character-authentic lyrics from the song brief and character profile.
Implements multi-section structured output with imagery consistency checks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.base import BaseAgent
from llm.client import load_prompt
from models.song import Lyrics, LyricsSection, SongBrief
from models.project import Project


LYRICS_SYSTEM = """你是一个天才作词人，专门为角色IP创作歌词。你不写通用的抒情歌词，
你写的每一句歌词都必须像那个角色本人在说话。

你遵循以下创作铁律：
1. 用角色的眼睛看世界，用角色的嘴巴说话
2. 意象必须来自角色的世界，不出现不属于他的物品
3. 情感不说出来，而是通过意象和动作来承载
4. 副歌必须是金句——即使只看副歌也能被打动
5. 韵脚要漂亮但不生硬
6. 告别"星星月亮风花"这些烂大街的意象

你为孙悟空写"俺老孙的筋斗云，翻不过这一劫"，为关羽写"青龙偃月斩不断，这世间的恩怨"，
为林黛玉写"葬花的人，最后谁来葬我"。你绝不写"我很痛苦但我很坚强"这种流水线歌词。"""


class LyricsGeneratorAgent(BaseAgent):
    """Agent 3: Character-authentic lyrics generation."""

    agent_name = "lyrics"

    def get_system_prompt(self) -> str:
        return LYRICS_SYSTEM

    def build_input(self, project: Project) -> str:
        prompt = load_prompt("lyrics", "generate_lyrics")

        parts = [prompt]

        # Character context
        if project.character_profile:
            p = project.character_profile
            parts.append(f"\n## 角色: {p.name}")
            parts.append(f"身份: {p.identity}")
            parts.append(f"性格: {', '.join(p.personality_traits)}")
            parts.append(f"说话风格: {p.speech_style}")
            parts.append(f"内心独白风格: {p.inner_voice}")
            parts.append(f"核心意象: {', '.join(p.core_imagery)}")
            parts.append(f"标志物品: {', '.join(p.signature_items)}")
            parts.append(f"经典语录: {'; '.join(p.classic_quotes[:5])}")

        # Song brief context
        if project.song_brief:
            sb = project.song_brief
            parts.append(f"\n## 歌曲选题")
            parts.append(f"选题角度: {sb.selected_angle.title}")
            parts.append(f"核心情感: {sb.selected_angle.emotional_core}")
            parts.append(f"叙事视角: {sb.selected_angle.narrative_pov}")
            parts.append(f"目标感受: {sb.selected_angle.target_feeling}")
            parts.append(f"一句话钩子: {sb.selected_angle.hook_sentence}")
            parts.append(f"反差角度: {sb.selected_angle.contrast_angle}")
            parts.append(f"视觉母题: {sb.selected_angle.visual_motif}")
            parts.append(f"情绪弧线: {sb.emotional_arc}")
            parts.append(f"建议曲风: {sb.suggested_genre}")
            parts.append(f"创意方向: {sb.creative_direction}")

        # If there's a narrative, include relevant excerpt
        if project.character_narrative:
            # Take first 1500 chars of narrative as context
            excerpt = project.character_narrative[:1500]
            parts.append(f"\n## 角色生平叙事（节选）\n{excerpt}")

        parts.append(
            f"\n请为角色 {project.character_name} 创作歌词。"
            f"选择 {project.song_brief.selected_angle.title if project.song_brief else '合适的角度'}。"
        )
        return "\n".join(parts)

    def parse_output(self, raw_text: str) -> Lyrics:
        import re
        raw = raw_text.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw = "\n".join(lines)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                raise ValueError(f"Failed to parse lyrics JSON: {raw[:300]}")

        return Lyrics(
            version=data.get("version", 1),
            title=data.get("title", ""),
            character_name=data.get("character_name", ""),
            angle=data.get("angle", ""),
            sections=[
                LyricsSection(
                    section_type=s.get("section_type", ""),
                    lines=s.get("lines", []),
                    emotion=s.get("emotion", ""),
                    imagery_used=s.get("imagery_used", []),
                )
                for s in data.get("sections", [])
            ],
            full_text=data.get("full_text", ""),
            rhyme_scheme=data.get("rhyme_scheme", ""),
            imagery_vocabulary=data.get("imagery_vocabulary", []),
            language_style=data.get("language_style", ""),
            character_voice_score=float(data.get("character_voice_score", 0.5)),
        )

    def quality_check_prompt(self) -> str:
        return load_prompt("checker", "check_lyrics")

    def build_quality_check_input(
        self, output: Lyrics, project: Project
    ) -> str:
        parts = [
            f"## 上下文\n角色: {project.character_name}",
            f"选题: {project.song_brief.selected_angle.title if project.song_brief else 'N/A'}",
            f"角色说话风格: {project.character_profile.speech_style if project.character_profile else 'N/A'}",
            "\n## 歌词",
            "```json",
            json.dumps(output.model_dump(), ensure_ascii=False, indent=2),
            "```",
            "请严格评审歌词质量。重点检查：1)是否像角色本人在说话 2)意象是否来自角色世界 3)副歌是否有金句感",
        ]
        return "\n".join(parts)

    def build_revise_input(
        self, output: Lyrics, feedback: str, project: Project
    ) -> str:
        parts = [
            self.build_input(project),
            "\n## 上一版歌词（需要改进）",
            output.full_text,
            "\n## 审核反馈",
            feedback,
            "\n请根据反馈重新创作歌词。特别注意角色贴合度和意象选择。",
        ]
        return "\n".join(parts)

    def save_output(self, output: Lyrics) -> list[str]:
        paths = []

        # Save structured JSON
        lyrics_json_path = self.output_dir / "lyrics.json"
        lyrics_json_path.write_text(
            json.dumps(output.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        paths.append(str(lyrics_json_path))

        # Save formatted markdown
        lyrics_md_path = self.output_dir / "lyrics_final.md"
        md_lines = [
            f"# {output.title}",
            f"",
            f"**角色**: {output.character_name}",
            f"**选题**: {output.angle}",
            f"**语言风格**: {output.language_style}",
            f"**韵脚方案**: {output.rhyme_scheme}",
            f"**角色贴合度自评**: {output.character_voice_score}",
            f"",
            f"## 意象词汇表",
            f"{', '.join(output.imagery_vocabulary)}",
            f"",
            f"## 歌词",
            f"",
        ]
        for section in output.sections:
            md_lines.append(f"### [{section.section_type}] — {section.emotion}")
            for line in section.lines:
                md_lines.append(line)
            md_lines.append("")

        lyrics_md_path.write_text("\n".join(md_lines), encoding="utf-8")
        paths.append(str(lyrics_md_path))

        return paths
