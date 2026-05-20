"""Agent 1: Character Research — 角色深度研究

Searches for character information, structures it into a profile,
and writes a narrative biography.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.base import BaseAgent
from llm.client import LLMClient, load_prompt
from models.character import CharacterProfile, KeyMoment, LifeEvent, Relationship
from models.project import Project


CHARACTER_PROFILE_SYSTEM = """你是一个角色研究专家。你深入研究角色的故事、性格和情感，
从碎片化信息中重建角色的完整画像。你特别擅长：
1. 发现角色不为人知的一面
2. 挖掘情感矛盾和戏剧冲突
3. 提取可用于内容创作的意象和符号
4. 用叙事的方式讲述角色的故事"""


class CharacterResearchAgent(BaseAgent):
    """Agent 1: Deep character research and profile construction.

    Integrates web search (DuckDuckGo, free) to gather real character data.
    """

    agent_name = "research"

    def get_system_prompt(self) -> str:
        return CHARACTER_PROFILE_SYSTEM

    def _search_web(self, character_name: str) -> list[dict]:
        """Search the web for character information using DuckDuckGo (free, no API key)."""
        try:
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS

            results = []
            queries = [
                f"{character_name} 角色 人物分析",
                f"{character_name} 原著 故事 性格",
                f"{character_name} 经典语录 名场面",
            ]
            with DDGS() as ddgs:
                for query in queries[:2]:  # Limit to 2 queries to stay fast
                    try:
                        for r in ddgs.text(query, max_results=5, region="cn-zh"):
                            body = (r.get("body") or "").strip()
                            if body and len(body) > 30:
                                results.append({
                                    "title": r.get("title", ""),
                                    "content": body,
                                    "url": r.get("href", ""),
                                })
                    except Exception:
                        pass
            return results[:10]
        except ImportError:
            return []
        except Exception:
            return []

    def build_input(self, project: Project) -> str:
        """Build the research prompt for this character."""
        prompt = load_prompt("research", "structure_profile")

        parts = [prompt]
        parts.append(f"\n\n## 角色名称\n{project.character_name}")

        # Determine source context
        source = project.character_name
        prefill = getattr(project, '_prefill_profile', None)
        if prefill and isinstance(prefill, dict):
            source = prefill.get('background', '') or prefill.get('source', '') or project.character_name
        parts.append(f"\n## 来源\n{source}")

        # If we have pre-filled data from novel decomposition, include it
        if prefill and isinstance(prefill, dict):
            parts.append("\n## 来自小说自动拆解的角色数据（这是角色的权威信息，必须以此为准）")
            parts.append("以下数据由 AI 从小说中自动提取，这是该角色的唯一权威定义：")
            parts.append("```json")
            parts.append(json.dumps(prefill, ensure_ascii=False, indent=2))
            parts.append("```")
            parts.append("重要：该角色是小说中的虚构人物，不是真实历史人物。你必须严格基于以上预填充数据来构建角色档案。")
            parts.append("预填充数据中的 personality、appearance、background 是角色的核心设定，不可偏离。")

        # Web search results (only for non-revision)
        if not project.character_narrative:
            search_results = self._search_web(project.character_name)
            if search_results:
                parts.append("\n## 网络搜索结果（仅供参考背景知识）")
                parts.append("注意：网络搜索结果可能指向同名但不同的人物。预填充数据（来自小说拆解）才是该角色的权威信息。")
                for r in search_results[:8]:
                    parts.append(f"\n### {r['title']}")
                    parts.append(f"内容: {r['content'][:300]}")
                    parts.append(f"来源: {r['url']}")
                parts.append("\n如果网络搜索结果与预填充数据描述的不是同一个人物，请以预填充数据为准。")

        if project.character_narrative:
            # This is revision
            parts.append("\n## 之前的研究结果（需要改进）")
            if project.character_profile:
                parts.append("```json")
                parts.append(json.dumps(project.character_profile.model_dump(), ensure_ascii=False, indent=2))
                parts.append("```")
        else:
            parts.append(
                f"\n请根据以上所有信息，为 {project.character_name} 生成一份完整的角色档案。"
                f"如果有预填充数据，必须以预填充数据为核心，在此基础上进行合理扩展和深度挖掘。"
            )

        return "\n".join(parts)

    def parse_output(self, raw_text: str) -> CharacterProfile:
        """Parse LLM JSON output into a CharacterProfile."""
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
            # Try to extract JSON from surrounding text
            import re
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                raise ValueError(f"Failed to parse character profile JSON: {raw[:500]}")

        # Build CharacterProfile with lenient coercion
        profile = CharacterProfile(
            name=data.get("name", ""),
            aliases=data.get("aliases", []),
            origin=data.get("origin", ""),
            era=data.get("era", ""),
            identity=data.get("identity", ""),
            appearance=data.get("appearance", ""),
            appearance_variants=data.get("appearance_variants", {}),
            personality_traits=data.get("personality_traits", []),
            personality_contradictions=data.get("personality_contradictions", []),
            character_arc=data.get("character_arc", ""),
            life_events=[
                LifeEvent(
                    time_label=e.get("time_label", ""),
                    event_title=e.get("event_title", ""),
                    description=e.get("description", ""),
                    emotional_tone=e.get("emotional_tone", ""),
                    visual_potential=int(e.get("visual_potential", 5)),
                    song_potential=int(e.get("song_potential", 5)),
                )
                for e in data.get("life_events", [])
            ],
            highlight_moments=data.get("highlight_moments", []),
            lowlight_moments=data.get("lowlight_moments", []),
            relationships=[
                Relationship(
                    name=r.get("name", ""),
                    relation_type=r.get("relation_type", ""),
                    description=r.get("description", ""),
                    emotional_dynamic=r.get("emotional_dynamic", ""),
                )
                for r in data.get("relationships", [])
            ],
            classic_quotes=data.get("classic_quotes", []),
            speech_style=data.get("speech_style", ""),
            inner_voice=data.get("inner_voice", ""),
            signature_items=data.get("signature_items", []),
            signature_actions=data.get("signature_actions", []),
            core_imagery=data.get("core_imagery", []),
            color_palette=data.get("color_palette", []),
            different_interpretations=data.get("different_interpretations", []),
            controversies=data.get("controversies", []),
            research_sources=data.get("research_sources", []),
            completeness_score=float(data.get("completeness_score", 0.5)),
        )
        return profile

    def quality_check_prompt(self) -> str:
        return load_prompt("checker", "check_research")

    def build_quality_check_input(self, output: CharacterProfile, project: Project) -> str:
        parts = [
            f"## 上下文\n角色名称: {project.character_name}\n",
            "## 角色档案",
            "```json",
            json.dumps(output.model_dump(), ensure_ascii=False, indent=2),
            "```",
            "请对该角色档案进行质量评分。",
        ]
        return "\n".join(parts)

    def build_revise_input(
        self, output: CharacterProfile, feedback: str, project: Project
    ) -> str:
        parts = [
            load_prompt("research", "structure_profile"),
            f"\n## 角色名称\n{project.character_name}",
            "\n## 上一版角色档案（需要改进）",
            "```json",
            json.dumps(output.model_dump(), ensure_ascii=False, indent=2),
            "```",
            f"\n## 审核反馈（请根据以下反馈修改）\n{feedback}",
            "\n请根据反馈重新生成角色档案。",
        ]
        return "\n".join(parts)

    def save_output(self, output: CharacterProfile) -> list[str]:
        paths = []
        # Save profile JSON
        profile_path = self.output_dir / "character_profile.json"
        profile_path.write_text(
            json.dumps(output.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        paths.append(str(profile_path))
        return paths

    # ── Additional: Generate Narrative ──

    def generate_narrative(self, profile: CharacterProfile) -> str:
        """Generate a narrative biography from the profile."""
        system_prompt = "你是一位擅长讲故事的传记作家。"
        user_message = (
            load_prompt("research", "write_narrative")
            + "\n\n## 角色档案\n```json\n"
            + json.dumps(profile.model_dump(), ensure_ascii=False, indent=2)
            + "\n```\n请基于以上档案，撰写角色生平叙事。"
        )
        narrative = self.llm.chat_with_retry(system_prompt, user_message, max_tokens=4096)
        narrative_path = self.output_dir / "character_narrative.md"
        narrative_path.write_text(narrative, encoding="utf-8")
        return narrative

    def extract_key_moments(self, profile: CharacterProfile) -> list[KeyMoment]:
        """Extract key moments for content creation."""
        moments = []
        for event in profile.life_events:
            if event.song_potential >= 6:
                angle_hints = []
                emo = event.emotional_tone
                if emo in ("悲壮", "孤独"):
                    angle_hints.extend(["不被人理解的内心世界", "表面强大内心的脆弱"])
                if emo in ("热血", "愤怒"):
                    angle_hints.extend(["反抗命运的呐喊", "不屈服的精神"])
                if emo in ("释然", "感动"):
                    angle_hints.extend(["回头看这一生的感悟", "与宿命和解"])

                moments.append(
                    KeyMoment(
                        title=event.event_title,
                        event=event.description,
                        emotion=event.emotional_tone,
                        angle_hints=angle_hints,
                        visual_hints=[f"画面: {event.description}"],
                        viral_score=event.song_potential,
                    )
                )
        # Sort by viral potential
        moments.sort(key=lambda m: m.viral_score, reverse=True)
        return moments[:10]
