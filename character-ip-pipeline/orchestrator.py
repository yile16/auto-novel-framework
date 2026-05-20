"""Orchestrator — 总调度器，协调所有 Agent 的执行流程和质量检核。

Pipeline stages:
  Agent 1 (research) ─┬─→ Agent 2 (angle) → Agent 3 (lyrics) → Agent 4 (voice) → Agent 5 (song)
                       │                                                              │
                       └─→ Agent 6 (visual) ──────────────────────────────────────────┘
                                                                                       │
                                                  Agent 7 (video) ←───────────────────┘
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from config import PipelineConfig, ProjectConfig
from llm.client import LLMClient
from checker.quality_checker import QualityChecker
from agents.research import CharacterResearchAgent
from agents.angle_planner import AnglePlannerAgent
from agents.lyrics import LyricsGeneratorAgent
from agents.voice_design import VoiceDesignAgent
from agents.song_producer import SongProducerAgent
from agents.visual_design import VisualDesignAgent
from agents.video_producer import VideoProducerAgent
from models.project import Project, AgentResult, AgentStatus
from utils.file_manager import ProjectFileManager

logger = logging.getLogger(__name__)


class Orchestrator:
    """Master orchestrator for the Character IP Pipeline."""

    def __init__(self, config: PipelineConfig = None):
        self.config = config or PipelineConfig()
        self.llm = LLMClient(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            base_url=self.config.base_url,
            api_key=self.config.api_key,
        )
        self.checker = QualityChecker(self.llm)

        # Callbacks for UI updates
        self._on_stage_start: Optional[Callable] = None
        self._on_stage_complete: Optional[Callable] = None
        self._on_check: Optional[Callable] = None
        self._on_error: Optional[Callable] = None

    # ── Callback registration ──

    def on_stage_start(self, fn: Callable):
        self._on_stage_start = fn

    def on_stage_complete(self, fn: Callable):
        self._on_stage_complete = fn

    def on_check(self, fn: Callable):
        self._on_check = fn

    def on_error(self, fn: Callable):
        self._on_error = fn

    # ── Main pipeline execution ──

    def run(
        self,
        character_name: str,
        source: str = "",
        style: str = "auto",
        stages: list[str] | None = None,
        prefill_profile: dict | None = None,
    ) -> Project:
        """Run the full or partial pipeline for a character.

        Args:
            character_name: Name of the character (e.g. "孙悟空")
            source: Source material (e.g. "西游记原著")
            style: Visual style preference
            stages: If provided, only run these stages (e.g. ["research", "angle", "lyrics"])
            prefill_profile: Optional dict with pre-filled character data from novel decomposition

        Returns:
            Project with all outputs and agent results.
        """
        if stages is None:
            stages = ["research", "angle", "lyrics", "voice", "song", "visual", "video"]

        project = Project(
            project_id=f"{character_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            character_name=character_name,
        )
        project._prefill_profile = prefill_profile

        file_manager = ProjectFileManager(self.config.output_dir, character_name)
        file_manager.setup()

        logger.info(f"🎬 启动项目: {character_name}")
        logger.info(f"📂 输出目录: {file_manager.project_dir}")

        # ── Stage: Research (Agent 1) ──
        if "research" in stages:
            self._notify_start("research", "角色深度研究")
            try:
                research_agent = CharacterResearchAgent(
                    self.llm,
                    file_manager.get_stage_dir("research"),
                    self.config.quality_threshold,
                    self.config.max_retries,
                )
                profile, result = research_agent.run(project)
                project.character_profile = profile
                project.agent_results["research"] = result

                # Generate narrative
                self._notify_start("research", "生成角色生平叙事")
                narrative = research_agent.generate_narrative(profile)
                project.character_narrative = narrative

                # Extract key moments
                key_moments = research_agent.extract_key_moments(profile)
                project.key_moments = key_moments
                # Save key moments
                km_path = file_manager.get_stage_dir("research") / "key_moments.json"
                km_path.write_text(
                    json.dumps(
                        [m.model_dump() for m in key_moments],
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )

                self._notify_complete("research", result)
                logger.info(f"  ✅ 研究完成 (得分: {result.quality_score:.2f})")
            except Exception as e:
                logger.error(f"  ❌ 研究失败: {e}")
                project.agent_results["research"] = AgentResult(
                    agent_name="research",
                    status=AgentStatus.FAILED,
                    error_message=str(e),
                )
                if self._on_error:
                    self._on_error("research", str(e))

        # ── Stage: Angle (Agent 2) ──
        if "angle" in stages and project.character_profile:
            self._notify_start("angle", "选题策划")
            try:
                angle_agent = AnglePlannerAgent(
                    self.llm,
                    file_manager.get_stage_dir("angle"),
                    self.config.quality_threshold,
                    self.config.max_retries,
                )
                song_brief, result = angle_agent.run(project)
                project.song_brief = song_brief
                project.agent_results["angle"] = result
                self._notify_complete("angle", result)
                logger.info(f"  ✅ 选题策划完成 (得分: {result.quality_score:.2f})")
                logger.info(f"     选定: {song_brief.selected_angle.title}")
            except Exception as e:
                logger.error(f"  ❌ 选题策划失败: {e}")
                project.agent_results["angle"] = AgentResult(
                    agent_name="angle", status=AgentStatus.FAILED, error_message=str(e)
                )

        # ── Stage: Lyrics (Agent 3) ──
        if "lyrics" in stages and project.song_brief:
            self._notify_start("lyrics", "歌词生成")
            try:
                lyrics_agent = LyricsGeneratorAgent(
                    self.llm,
                    file_manager.get_stage_dir("lyrics"),
                    self.config.quality_threshold,
                    self.config.max_retries,
                )
                lyrics, result = lyrics_agent.run(project)
                project.lyrics = lyrics
                project.agent_results["lyrics"] = result
                self._notify_complete("lyrics", result)
                logger.info(f"  ✅ 歌词生成完成 (得分: {result.quality_score:.2f})")
                logger.info(f"     歌名: {lyrics.title}")
            except Exception as e:
                logger.error(f"  ❌ 歌词生成失败: {e}")
                project.agent_results["lyrics"] = AgentResult(
                    agent_name="lyrics", status=AgentStatus.FAILED, error_message=str(e)
                )

        # ── Stage: Voice (Agent 4) ──
        if "voice" in stages and project.lyrics:
            self._notify_start("voice", "音色设计")
            try:
                voice_agent = VoiceDesignAgent(
                    self.llm,
                    file_manager.get_stage_dir("voice"),
                    self.config.quality_threshold,
                    self.config.max_retries,
                )
                voice_design, result = voice_agent.run(project)
                project.voice_design = voice_design
                project.agent_results["voice"] = result
                self._notify_complete("voice", result)
                logger.info(f"  ✅ 音色设计完成 (得分: {result.quality_score:.2f})")
            except Exception as e:
                logger.error(f"  ❌ 音色设计失败: {e}")
                project.agent_results["voice"] = AgentResult(
                    agent_name="voice", status=AgentStatus.FAILED, error_message=str(e)
                )

        # ── Stage: Song (Agent 5) ──
        if "song" in stages and project.voice_design:
            self._notify_start("song", "歌曲制作")
            try:
                song_agent = SongProducerAgent(
                    self.llm,
                    file_manager.get_stage_dir("song"),
                    self.config.quality_threshold,
                    self.config.max_retries,
                )
                song_production, result = song_agent.run(project)
                project.song_production = song_production
                project.agent_results["song"] = result
                self._notify_complete("song", result)
                logger.info(f"  ✅ 歌曲制作完成 (得分: {result.quality_score:.2f})")
                logger.info(f"     曲风: {song_production.style.genre}")
            except Exception as e:
                logger.error(f"  ❌ 歌曲制作失败: {e}")
                project.agent_results["song"] = AgentResult(
                    agent_name="song", status=AgentStatus.FAILED, error_message=str(e)
                )

        # ── Stage: Visual (Agent 6) ──
        if "visual" in stages and project.character_profile:
            self._notify_start("visual", "形象设计")
            try:
                visual_agent = VisualDesignAgent(
                    self.llm,
                    file_manager.get_stage_dir("visual"),
                    self.config.quality_threshold,
                    self.config.max_retries,
                )
                visual_design, result = visual_agent.run(project)
                project.visual_design = visual_design
                project.agent_results["visual"] = result
                self._notify_complete("visual", result)
                logger.info(f"  ✅ 形象设计完成 (得分: {result.quality_score:.2f})")
                logger.info(f"     风格: {visual_design.selected_style}")
            except Exception as e:
                logger.error(f"  ❌ 形象设计失败: {e}")
                project.agent_results["visual"] = AgentResult(
                    agent_name="visual", status=AgentStatus.FAILED, error_message=str(e)
                )

        # ── Stage: Video (Agent 7) ──
        if "video" in stages and project.lyrics:
            self._notify_start("video", "视频制作")
            try:
                video_agent = VideoProducerAgent(
                    self.llm,
                    file_manager.get_stage_dir("video"),
                    self.config.quality_threshold,
                    self.config.max_retries,
                )
                storyboard, result = video_agent.run(project)
                project.storyboard = storyboard
                project.agent_results["video"] = result
                self._notify_complete("video", result)
                logger.info(f"  ✅ 分镜脚本完成 (得分: {result.quality_score:.2f})")
                if storyboard:
                    logger.info(f"     总镜数: {len(storyboard.shots)}")
            except Exception as e:
                logger.error(f"  ❌ 视频制作失败: {e}")
                project.agent_results["video"] = AgentResult(
                    agent_name="video", status=AgentStatus.FAILED, error_message=str(e)
                )

        # Save final project state
        file_manager.save_project_state({
            "project_id": project.project_id,
            "character_name": project.character_name,
            "stages_completed": [
                name for name, r in project.agent_results.items()
                if r.status == AgentStatus.DONE
            ],
            "agent_results": {
                name: r.model_dump() for name, r in project.agent_results.items()
            },
        })

        logger.info(f"🏁 项目完成: {character_name}")
        self._print_summary(project)
        return project

    # ── Stage runner (for UI async execution) ──

    def run_stage(self, stage: str, project: Project, file_manager: ProjectFileManager) -> Project:
        """Run a single stage. Used by the web UI for step-by-step execution."""
        stages = [stage]
        # Reuse the stage logic but only for this one stage
        return self._run_stages(stages, project, file_manager)

    def _run_stages(self, stages: list[str], project: Project, fm: ProjectFileManager) -> Project:
        """Internal: run specific stages."""
        # This mirrors run() but skips stages not in the list
        # For simplicity, delegate to run() with filtered stages
        return self.run(project.character_name, stages=stages)

    # ── Notification helpers ──

    def _notify_start(self, stage: str, label: str):
        if self._on_stage_start:
            self._on_stage_start(stage, label)

    def _notify_complete(self, stage: str, result: AgentResult):
        if self._on_stage_complete:
            self._on_stage_complete(stage, result)

    def _print_summary(self, project: Project):
        """Print a summary of the project results."""
        print("\n" + "=" * 60)
        print(f"📊 项目总结: {project.character_name}")
        print("=" * 60)
        for name, result in project.agent_results.items():
            icon = "✅" if result.status == AgentStatus.DONE else "❌"
            print(f"  {icon} {name}: {result.quality_score:.2f} ({result.retry_count} retries)")
        print("=" * 60)

        # Print output stats
        if project.character_profile:
            print(f"  角色事件: {len(project.character_profile.life_events)} 个")
            print(f"  关系网: {len(project.character_profile.relationships)} 人")
        if project.song_brief:
            print(f"  候选角度: {len(project.song_brief.candidate_angles)} 个")
        if project.lyrics:
            print(f"  歌词段落: {len(project.lyrics.sections)} 段")
        if project.storyboard:
            print(f"  分镜数: {len(project.storyboard.shots)} 镜")
