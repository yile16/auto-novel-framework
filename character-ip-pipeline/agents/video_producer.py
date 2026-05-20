"""Agent 7: Video Producer — 视频制作

Handles storyboard planning, shot image generation prompts,
image-to-video generation, and final video assembly.

This is the most complex agent — broken into sub-steps:
  7.1 Storyboard planning
  7.2 Shot image generation (prompts only; actual generation via external API)
  7.3 Image-to-video (prompts only; actual generation via external API)
  7.4 Video assembly (moviepy/ffmpeg)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.base import BaseAgent
from llm.client import load_prompt
from models.visual import Storyboard, StoryboardShot, VideoProduction
from models.project import Project


STORYBOARD_SYSTEM = """你是一位MV导演和分镜师，专门为角色IP歌曲创作分镜脚本。

你的导演哲学：
1. 画面讲故事，不是重复歌词——歌词说"我很孤独"，画面可以是"空荡的宫殿里，王座上只有一把剑"
2. 视觉母题贯穿全片——一个反复出现的视觉符号
3. 节奏跟情绪走——慢歌长镜头，高潮短镜头快切
4. 色彩是第二个情绪轨道——暖金→暗红→青灰的弧线
5. 每个镜头都为AI图像生成而设计——描述要具体到可执行

分镜格式（每镜必填）：
- 镜号 / 时长 / 景别 / 画面描述 / 镜头运动 / 光影 / 色调 / 情绪 / 转场 / 对应歌词 / 生图prompt

时长分配参考（3分钟歌）：
- Intro: 10-15s, 2-3镜
- Verse1: 30-40s, 4-6镜
- Chorus1: 30s, 3-5镜（节奏快）
- Verse2: 30-40s, 4-6镜
- Bridge: 20s, 2-3镜
- Chorus2: 30-40s, 4-6镜（最爆发）
- Outro: 10-15s, 1-2镜"""


class VideoProducerAgent(BaseAgent):
    """Agent 7: Complete video production pipeline."""

    agent_name = "video"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.storyboard_dir = self.output_dir / "storyboard"
        self.shots_dir = self.output_dir / "shots"
        self.clips_dir = self.output_dir / "clips"
        self.final_dir = self.output_dir / "final"

    def get_system_prompt(self) -> str:
        return STORYBOARD_SYSTEM

    def build_input(self, project: Project) -> str:
        prompt = load_prompt("video", "plan_storyboard")

        parts = [prompt]

        if project.character_profile:
            p = project.character_profile
            parts.append(f"\n## 角色: {p.name}")
            parts.append(f"外貌: {p.appearance}")
            parts.append(f"标志物品: {', '.join(p.signature_items)}")
            parts.append(f"标志动作: {', '.join(p.signature_actions)}")
            parts.append(f"代表色: {', '.join(p.color_palette)}")
            parts.append(f"核心意象: {', '.join(p.core_imagery)}")

            # High visual potential events
            visual_events = [e for e in p.life_events if e.visual_potential >= 6]
            if visual_events:
                parts.append("高画面感事件:")
                for e in visual_events[:5]:
                    parts.append(f"  - [{e.emotional_tone}] {e.event_title}: {e.description[:100]}")

        if project.character_narrative:
            # Include key narrative excerpts
            parts.append(f"\n## 角色生平叙事（节选）")
            parts.append(project.character_narrative[:1000])

        if project.lyrics:
            parts.append(f"\n## 歌词")
            parts.append(f"歌名: {project.lyrics.title}")
            parts.append("完整歌词:")
            parts.append(project.lyrics.full_text)

        if project.song_brief:
            parts.append(f"\n## 选题信息")
            parts.append(f"视觉母题: {project.song_brief.selected_angle.visual_motif}")

        if project.visual_design:
            vd = project.visual_design
            parts.append(f"\n## 视觉方案")
            parts.append(f"选定风格: {vd.selected_style}")
            if vd.consistency_anchor:
                parts.append(f"形象锚定: {vd.consistency_anchor.get('prompt_prefix', '')}")

        parts.append(f"\n请为 {project.character_name} 的歌曲创建分镜脚本。")
        return "\n".join(parts)

    def parse_output(self, raw_text: str) -> Storyboard:
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
                raise ValueError(f"Failed to parse storyboard JSON: {raw[:300]}")

        return Storyboard(
            song_title=data.get("song_title", ""),
            total_duration_sec=float(data.get("total_duration_sec", 0)),
            shots=[
                StoryboardShot(
                    shot_id=s.get("shot_id", ""),
                    duration_sec=float(s.get("duration_sec", 1.0)),
                    shot_type=s.get("shot_type", ""),
                    camera_movement=s.get("camera_movement", ""),
                    visual_description=s.get("visual_description", ""),
                    character_pose=s.get("character_pose", ""),
                    lighting=s.get("lighting", ""),
                    color_tone=s.get("color_tone", ""),
                    emotion=s.get("emotion", ""),
                    transition_from_prev=s.get("transition_from_prev", ""),
                    lyrics_line=s.get("lyrics_line", ""),
                    reference_image_hint=s.get("reference_image_hint", ""),
                    image_generation_prompt=s.get("image_generation_prompt", ""),
                )
                for s in data.get("shots", [])
            ],
            visual_theme=data.get("visual_theme", ""),
            color_arc=data.get("color_arc", ""),
            key_frames=data.get("key_frames", []),
        )

    def quality_check_prompt(self) -> str:
        return load_prompt("checker", "check_storyboard")

    def build_quality_check_input(
        self, output: Storyboard, project: Project
    ) -> str:
        parts = [
            f"## 上下文\n角色: {project.character_name}",
            f"歌词: {project.lyrics.full_text[:500] if project.lyrics else 'N/A'}\n",
            "## 分镜脚本",
            "```json",
            json.dumps(output.model_dump(), ensure_ascii=False, indent=2),
            "```",
            "请检查分镜脚本。关注：画面是否在讲故事、节奏是否匹配、可执行性。",
        ]
        return "\n".join(parts)

    def build_revise_input(
        self, output: Storyboard, feedback: str, project: Project
    ) -> str:
        parts = [
            self.build_input(project),
            "\n## 上一版分镜（需要改进）",
            "```json",
            json.dumps(output.model_dump(), ensure_ascii=False, indent=2),
            "```",
            f"\n## 审核反馈\n{feedback}",
            "\n请根据反馈重新创作分镜脚本。",
        ]
        return "\n".join(parts)

    def save_output(self, output: Storyboard) -> list[str]:
        self.storyboard_dir.mkdir(parents=True, exist_ok=True)
        paths = []

        # Save storyboard JSON
        sb_path = self.storyboard_dir / "storyboard.json"
        sb_path.write_text(
            json.dumps(output.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        paths.append(str(sb_path))

        # Save human-readable storyboard table
        table_path = self.storyboard_dir / "storyboard_table.md"
        lines = [
            f"# 分镜表 — {output.song_title}",
            f"",
            f"**总时长**: {output.total_duration_sec}s | **总镜数**: {len(output.shots)}",
            f"**视觉主题**: {output.visual_theme}",
            f"**色彩弧线**: {output.color_arc}",
            f"",
            f"| 镜号 | 时长 | 景别 | 运镜 | 画面 | 情绪 | 歌词 |",
            f"|------|------|------|------|------|------|------|",
        ]
        for shot in output.shots:
            desc = shot.visual_description[:60] + "..." if len(shot.visual_description) > 60 else shot.visual_description
            lines.append(
                f"| {shot.shot_id} | {shot.duration_sec}s | {shot.shot_type} | "
                f"{shot.camera_movement} | {desc} | {shot.emotion} | {shot.lyrics_line[:30]} |"
            )
        table_path.write_text("\n".join(lines), encoding="utf-8")
        paths.append(str(table_path))

        # Save all image prompts in one file for easy copy-paste
        prompts_path = self.storyboard_dir / "all_image_prompts.txt"
        prompt_lines = ["# 逐镜生图 Prompts", ""]
        for shot in output.shots:
            prompt_lines.append(f"## {shot.shot_id} — {shot.shot_type} — {shot.emotion}")
            prompt_lines.append(shot.image_generation_prompt)
            prompt_lines.append("")
        prompts_path.write_text("\n".join(prompt_lines), encoding="utf-8")
        paths.append(str(prompts_path))

        return paths

    # ── Video assembly utilities ──

    def generate_shot_image(self, shot: StoryboardShot, anchor: dict) -> str:
        """Generate an image for a storyboard shot using DALL-E or similar.

        This is a placeholder — actual API integration depends on the image API.
        """
        # Combine anchor prompt with shot-specific prompt
        full_prompt = ""
        if anchor.get("prompt_prefix"):
            full_prompt = anchor["prompt_prefix"] + ", "
        full_prompt += shot.image_generation_prompt

        # Placeholder for actual API call
        # image_path = call_dalle_api(full_prompt)
        return full_prompt  # Return the prompt for manual use

    def assemble_video(
        self,
        storyboard: Storyboard,
        clip_paths: list[str],
        audio_path: str,
        output_path: str,
    ) -> str:
        """Assemble video clips into final MV with audio.

        Uses moviepy for video editing. This is a template — full implementation
        requires actual video clips and audio file.
        """
        try:
            from moviepy import VideoFileClip, AudioFileClip, CompositeVideoClip, concatenate_videoclips
        except ImportError:
            # moviepy not installed — return the assembly plan
            return self._write_assembly_plan(storyboard, clip_paths, audio_path, output_path)

        # Actual assembly (simplified)
        clips = []
        for i, (shot, clip_path) in enumerate(zip(storyboard.shots, clip_paths)):
            try:
                clip = VideoFileClip(clip_path).resized((1080, 1920))
                clip = clip.with_duration(shot.duration_sec)
                clips.append(clip)
            except Exception:
                continue

        if not clips:
            return self._write_assembly_plan(storyboard, clip_paths, audio_path, output_path)

        final = concatenate_videoclips(clips)
        try:
            audio = AudioFileClip(audio_path)
            final = final.with_audio(audio)
        except Exception:
            pass

        final.write_videofile(output_path, fps=24, codec="libx264")
        return output_path

    def _write_assembly_plan(
        self,
        storyboard: Storyboard,
        clip_paths: list[str],
        audio_path: str,
        output_path: str,
    ) -> str:
        """Write an assembly plan when moviepy is not available."""
        plan_path = str(Path(output_path).with_suffix(".plan.md"))
        lines = [
            "# 视频合成计划",
            f"音频: {audio_path}",
            f"输出: {output_path}",
            "",
            "## 时间线",
        ]
        time = 0.0
        for shot, clip in zip(storyboard.shots, clip_paths):
            lines.append(
                f"{time:.1f}s - {time + shot.duration_sec:.1f}s: "
                f"{shot.shot_id} → {clip} ({shot.transition_from_prev})"
            )
            time += shot.duration_sec
        Path(plan_path).write_text("\n".join(lines), encoding="utf-8")
        return plan_path
