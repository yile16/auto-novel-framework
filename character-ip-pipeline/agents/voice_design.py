"""Agent 4: Voice Designer — 音色设计

Designs character voice personality with strict copyright safety.
All descriptions use acoustic parameters, never real singer names.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.base import BaseAgent
from llm.client import load_prompt
from models.song import VoiceDesign, SongBrief
from models.project import Project


VOICE_DESIGN_SYSTEM = """你是一个声学工程师 + 音乐制作人，专门为AI角色歌曲设计声音人格。

版权红线（MUST遵守）：
- 绝对禁止提及任何真人歌手姓名
- 绝对禁止 "像XXX的声音" "XXX风格唱腔"
- 只能用声学参数描述：音域、共鸣位置、声线厚度、明亮度、气息感、咬字方式
- 如果角色故事中有歌唱描写的，优先参考原著中的声音描述

音色设计维度：
- 性别/年龄感 → 物理基础
- 声线厚度 → 纤细/薄/适中/厚实/浑厚
- 明亮度 → 暗淡/柔和/清亮/明亮/穿透性强
- 气息感 → 气息重/气声/正常/干净利落
- 共鸣位置 → 头腔/胸腔/鼻腔/喉音
- 咬字方式 → 字正腔圆/慵懒/急促/从容
- 唱法方向 → 流行/民谣/摇滚/戏腔/说唱/民族/美声
- 情感表达 → 克制内敛/爆发力强/娓娓道来/撕裂感/空灵感"""


class VoiceDesignAgent(BaseAgent):
    """Agent 4: Voice character design with copyright safety."""

    agent_name = "voice"

    def get_system_prompt(self) -> str:
        return VOICE_DESIGN_SYSTEM

    def build_input(self, project: Project) -> str:
        prompt = load_prompt("voice", "design_voice")

        parts = [prompt]

        if project.character_profile:
            p = project.character_profile
            parts.append(f"\n## 角色: {p.name}")
            parts.append(f"性别: 根据角色故事判断")
            parts.append(f"年龄阶段: 根据角色主要故事阶段判断")
            parts.append(f"性格特质: {', '.join(p.personality_traits)}")
            parts.append(f"成长弧光: {p.character_arc}")
            parts.append(f"说话风格: {p.speech_style}")
            parts.append(f"内心声音: {p.inner_voice}")
            parts.append(f"经典语录: {'; '.join(p.classic_quotes[:3])}")

        if project.song_brief:
            sb = project.song_brief
            parts.append(f"\n## 歌曲信息")
            parts.append(f"选题: {sb.selected_angle.title}")
            parts.append(f"核心情感: {sb.selected_angle.emotional_core}")
            parts.append(f"情绪弧线: {sb.emotional_arc}")
            parts.append(f"建议曲风: {sb.suggested_genre}")

        if project.lyrics:
            parts.append(f"\n## 歌词风格")
            parts.append(f"语言风格: {project.lyrics.language_style}")
            # Include lyrics sections with emotions
            parts.append("歌词情绪分布:")
            for s in project.lyrics.sections:
                parts.append(f"  [{s.section_type}] {s.emotion}")

        parts.append(f"\n请为 {project.character_name} 设计音色方案。严格遵守版权红线。")
        return "\n".join(parts)

    def parse_output(self, raw_text: str) -> VoiceDesign:
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
                raise ValueError(f"Failed to parse voice design JSON: {raw[:300]}")
        return VoiceDesign(
            gender=data.get("gender", ""),
            age_range=data.get("age_range", ""),
            timbre=data.get("timbre", ""),
            singing_style=data.get("singing_style", ""),
            vocal_range=data.get("vocal_range", ""),
            emotional_expression=data.get("emotional_expression", ""),
            voice_description=data.get("voice_description", ""),
            copyright_safety_notes=data.get("copyright_safety_notes", ""),
            presets=data.get("presets", []),
        )

    def quality_check_prompt(self) -> str:
        return load_prompt("checker", "check_voice")

    def build_quality_check_input(
        self, output: VoiceDesign, project: Project
    ) -> str:
        parts = [
            f"## 上下文\n角色: {project.character_name}\n",
            "## 音色设计方案",
            "```json",
            json.dumps(output.model_dump(), ensure_ascii=False, indent=2),
            "```",
            "请检查音色方案。重点：1)是否有任何真人歌手姓名 2)是否贴合角色 3)presets是否可执行",
        ]
        return "\n".join(parts)

    def build_revise_input(
        self, output: VoiceDesign, feedback: str, project: Project
    ) -> str:
        parts = [
            self.build_input(project),
            "\n## 上一版音色方案（需要改进）",
            "```json",
            json.dumps(output.model_dump(), ensure_ascii=False, indent=2),
            "```",
            f"\n## 审核反馈\n{feedback}",
            "\n请根据反馈重新设计音色方案。特别关注版权安全。",
        ]
        return "\n".join(parts)

    def save_output(self, output: VoiceDesign) -> list[str]:
        paths = []
        vd_path = self.output_dir / "voice_design.json"
        vd_path.write_text(
            json.dumps(output.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        paths.append(str(vd_path))

        presets_path = self.output_dir / "voice_presets.json"
        presets_path.write_text(
            json.dumps(output.presets, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        paths.append(str(presets_path))
        return paths
