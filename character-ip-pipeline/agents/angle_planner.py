"""Agent 2: Angle Planner — 选题策划

Generates song angle candidates from character profile,
evaluates viral potential, and selects the best angle.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.base import BaseAgent
from llm.client import load_prompt
from models.character import CharacterProfile
from models.song import SongAngle, SongBrief
from models.project import Project


ANGLE_PLANNER_SYSTEM = """你是一个爆款内容策划专家，专门为"角色IP歌曲"策划选题角度的顶尖策划人。
你读过上千个角色的故事，你策划了上百首爆款角色歌曲。你最关键的能力是：
从角色的故事中找到一个角度，让几百年/几千年前的角色唱出当代人的心。

你的选题方法论：
1. 反差重塑：打破大众对角色的固有印象，挖掘"不为人知的一面"
2. 当代映射：古老的故事映射当代人的困境和情感
3. 情感共振：角色的情感经历与普通人的通感
4. 哲学追问：角色的选择引发深层思考
5. 热血共鸣：角色面对困境的态度引发共鸣"""


class AnglePlannerAgent(BaseAgent):
    """Agent 2: Song angle/topic planning and selection."""

    agent_name = "angle"

    def get_system_prompt(self) -> str:
        return ANGLE_PLANNER_SYSTEM

    def build_input(self, project: Project) -> str:
        prompt = load_prompt("angle", "generate_angles")

        parts = [prompt]

        # Character context
        if project.character_profile:
            profile = project.character_profile
            parts.append(f"\n## 角色: {profile.name}")
            parts.append(f"身份: {profile.identity}")
            parts.append(f"性格特质: {', '.join(profile.personality_traits)}")
            parts.append(f"性格矛盾: {', '.join(profile.personality_contradictions)}")
            parts.append(f"成长弧光: {profile.character_arc}")

            parts.append("\n## 关键事件")
            for e in profile.life_events:
                if e.song_potential >= 5:
                    parts.append(
                        f"- [{e.emotional_tone}] {e.event_title}: {e.description} "
                        f"(歌曲潜力: {e.song_potential}/10)"
                    )

            parts.append("\n## 核心意象")
            parts.append(f"代表色: {', '.join(profile.color_palette)}")
            parts.append(f"标志物品: {', '.join(profile.signature_items)}")
            parts.append(f"标志动作: {', '.join(profile.signature_actions)}")
            parts.append(f"经典语录: {'; '.join(profile.classic_quotes[:5])}")

        if project.key_moments:
            parts.append("\n## 已标注的高潜力时刻")
            for m in project.key_moments[:5]:
                parts.append(
                    f"- **{m.title}** [{m.emotion}] (热度分: {m.viral_score}/10)"
                    f"\n  角度提示: {', '.join(m.angle_hints)}"
                )

        parts.append(f"\n请为角色 {project.character_name} 生成歌曲选题方案。")
        return "\n".join(parts)

    def parse_output(self, raw_text: str) -> SongBrief:
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
                raise ValueError(f"Failed to parse angle planner JSON: {raw[:300]}")

        def parse_angle(d: dict) -> SongAngle:
            return SongAngle(
                angle_id=d.get("angle_id", ""),
                title=d.get("title", ""),
                based_on_event=d.get("based_on_event", ""),
                emotional_core=d.get("emotional_core", ""),
                narrative_pov=d.get("narrative_pov", "first"),
                target_feeling=d.get("target_feeling", ""),
                hook_sentence=d.get("hook_sentence", ""),
                contrast_angle=d.get("contrast_angle", ""),
                visual_motif=d.get("visual_motif", ""),
            )

        return SongBrief(
            selected_angle=parse_angle(data.get("selected_angle", {})),
            candidate_angles=[
                parse_angle(a) for a in data.get("candidate_angles", [])
            ],
            emotional_arc=data.get("emotional_arc", ""),
            suggested_genre=data.get("suggested_genre", ""),
            suggested_tempo=data.get("suggested_tempo", ""),
            creative_direction=data.get("creative_direction", ""),
        )

    def quality_check_prompt(self) -> str:
        return load_prompt("checker", "check_angle")

    def build_quality_check_input(
        self, output: SongBrief, project: Project
    ) -> str:
        parts = [
            f"## 上下文\n角色: {project.character_name}\n",
            "## 选题方案",
            "```json",
            json.dumps(output.model_dump(), ensure_ascii=False, indent=2),
            "```",
            "请对该选题方案进行质量评分。重点关注 hook_sentence 是否有爆款钩子感。",
        ]
        return "\n".join(parts)

    def build_revise_input(
        self, output: SongBrief, feedback: str, project: Project
    ) -> str:
        parts = [
            self.build_input(project),
            "\n## 上一版选题方案（需要改进）",
            "```json",
            json.dumps(output.model_dump(), ensure_ascii=False, indent=2),
            "```",
            f"\n## 审核反馈\n{feedback}",
            "\n请根据反馈重新生成选题方案。",
        ]
        return "\n".join(parts)

    def save_output(self, output: SongBrief) -> list[str]:
        paths = []
        brief_path = self.output_dir / "song_brief.json"
        brief_path.write_text(
            json.dumps(output.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        paths.append(str(brief_path))

        angles_path = self.output_dir / "angle_candidates.json"
        angles_path.write_text(
            json.dumps(
                [a.model_dump() for a in output.candidate_angles],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        paths.append(str(angles_path))
        return paths
