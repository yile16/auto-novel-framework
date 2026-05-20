"""Agent 6: Visual Designer — 角色形象设计

Designs character visual appearance for consistent image generation.
Creates style options, reference prompts, and consistency anchors.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.base import BaseAgent
from llm.client import load_prompt
from models.visual import VisualStyle, VisualDesign
from models.project import Project


VISUAL_DESIGN_SYSTEM = """你是一位角色视觉设计师，专门为AI图像生成创建角色视觉方案。

你的设计哲学：
1. 每个角色都有"视觉锚点"——让人一眼认出的核心视觉元素
2. 形象必须能通过文字描述让AI画出来——颜色、形状、材质、比例
3. 多套方案之间要有真正的风格差异，不是换汤不换药
4. 形象一致性是最大的技术挑战——consistency_anchor必须精心设计

视觉锚点识别方法：
- 头饰/发型 → 形状、颜色、材质
- 面部特征 → 眉形、眼型、肤色、特殊标记（如孙悟空的火眼金睛）
- 服饰 → 款式（朝代/风格）、主色、材质、标志性细节
- 道具 → 尺寸、形状、颜色、材质、手持方式
- 配色 → 主色+辅色+点缀色，形成色彩记忆"""
# Removed extra "s seen — not needed here
# removing this line


class VisualDesignAgent(BaseAgent):
    """Agent 6: Character visual design and image prompt generation."""

    agent_name = "visual"

    def get_system_prompt(self) -> str:
        return VISUAL_DESIGN_SYSTEM

    def build_input(self, project: Project) -> str:
        prompt = load_prompt("visual", "design_visual")

        parts = [prompt]

        if project.character_profile:
            p = project.character_profile
            parts.append(f"\n## 角色: {p.name}")
            parts.append(f"身份: {p.identity}")
            parts.append(f"外貌: {p.appearance}")

            if p.appearance_variants:
                parts.append("外貌各版本描述:")
                for ver, desc in p.appearance_variants.items():
                    parts.append(f"  - {ver}: {desc}")

            parts.append(f"标志物品: {', '.join(p.signature_items)}")
            parts.append(f"标志动作: {', '.join(p.signature_actions)}")
            parts.append(f"代表色: {', '.join(p.color_palette)}")
            parts.append(f"核心意象: {', '.join(p.core_imagery)}")

            # Include key life events with visual potential
            visual_events = [e for e in p.life_events if e.visual_potential >= 7]
            if visual_events:
                parts.append("\n高画面感事件（可用于MV形象设计）:")
                for e in visual_events[:5]:
                    parts.append(f"  - {e.event_title}: {e.description[:80]}")

        if project.song_brief:
            parts.append(f"\n## 歌曲信息")
            parts.append(f"选题: {project.song_brief.selected_angle.title}")
            parts.append(f"视觉母题: {project.song_brief.selected_angle.visual_motif}")

        parts.append(f"\n请为 {project.character_name} 设计视觉形象方案。")
        return "\n".join(parts)

    def parse_output(self, raw_text: str) -> VisualDesign:
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
                raise ValueError(f"Failed to parse visual design JSON: {raw[:300]}")

        return VisualDesign(
            character_name=data.get("character_name", ""),
            style_options=[
                VisualStyle(
                    style_name=s.get("style_name", ""),
                    face_description=s.get("face_description", ""),
                    hair_style=s.get("hair_style", ""),
                    costume=s.get("costume", ""),
                    color_scheme=s.get("color_scheme", []),
                    signature_props=s.get("signature_props", []),
                    overall_vibe=s.get("overall_vibe", ""),
                    image_prompt=s.get("image_prompt", ""),
                )
                for s in data.get("style_options", [])
            ],
            selected_style=data.get("selected_style", ""),
            consistency_anchor=data.get("consistency_anchor", {}),
            character_sheet_prompt=data.get("character_sheet_prompt", ""),
            expression_variants=data.get("expression_variants", []),
        )

    def quality_check_prompt(self) -> str:
        return load_prompt("checker", "check_visual")

    def build_quality_check_input(
        self, output: VisualDesign, project: Project
    ) -> str:
        parts = [
            f"## 上下文\n角色: {project.character_name}\n",
            "## 视觉设计方案",
            "```json",
            json.dumps(output.model_dump(), ensure_ascii=False, indent=2),
            "```",
            "请检查视觉设计。关注：视觉锚点是否明确、AI可生成性、形象一致性方案。",
        ]
        return "\n".join(parts)

    def build_revise_input(
        self, output: VisualDesign, feedback: str, project: Project
    ) -> str:
        parts = [
            self.build_input(project),
            "\n## 上一版视觉方案（需要改进）",
            "```json",
            json.dumps(output.model_dump(), ensure_ascii=False, indent=2),
            "```",
            f"\n## 审核反馈\n{feedback}",
            "\n请根据反馈重新设计视觉方案。特别关注形象一致性的改进。",
        ]
        return "\n".join(parts)

    def save_output(self, output: VisualDesign) -> list[str]:
        paths = []
        vd_path = self.output_dir / "visual_design.json"
        vd_path.write_text(
            json.dumps(output.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        paths.append(str(vd_path))

        # Save anchor separately
        anchor_path = self.output_dir / "prompt_anchor.json"
        anchor_path.write_text(
            json.dumps(output.consistency_anchor, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        paths.append(str(anchor_path))

        # Save reference image search hints
        ref_path = self.output_dir / "reference_image_hints.txt"
        ref_lines = ["# 参考图搜索关键词", ""]
        for style in output.style_options:
            ref_lines.append(f"## {style.style_name}")
            ref_lines.append(f"主prompt: {style.image_prompt}")
            ref_lines.append(f"关键词: {', '.join(style.color_scheme + style.signature_props)}")
            ref_lines.append("")
        ref_path.write_text("\n".join(ref_lines), encoding="utf-8")
        paths.append(str(ref_path))
        return paths
