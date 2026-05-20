"""Programmatic merger — merges raw chapter extractions into final StoryDecomposition.

No LLM calls. Preserves all 10 dimensions of extracted data with field-name normalization.
Replaces the LLM-based ArcMerger + BookFinalizer for large novels.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from core.models.story import StoryDecomposition
from core.models.character import (
    Character, CharacterArc, CharacterState, Identity, StaticTraits,
    AbilityGain, CombatPowerProgression,
)
from core.models.plot import (
    Plot, ChapterEvent, StoryBeat, ForeshadowingItem,
    CombatPowerState, AssetChange,
)
from core.models.setting import WorldSetting, Location, CheatSystem, CheatStage, Faction, PowerSystem
from core.models.style import Style
from core.models.relationship import Relationships, CharacterRelation, RelationEvolution

logger = logging.getLogger(__name__)


def _shorter_in_parens(longer: str, shorter: str) -> bool:
    """Check if `shorter` appears inside parentheses in `longer`.
    E.g. "年轻人（百里东君？）" with shorter="百里东君" → True.
    """
    import re
    parens = re.findall(r"[（(]([^）)]*)[）)]", longer)
    for p in parens:
        if shorter in p or p in shorter:
            return True
    return False


class ProgrammaticMerger:
    """Merges raw chapter extractions programmatically — no LLM, no data loss."""

    def merge(self, raw_extractions: list[dict], title: str = "", author: str = "") -> StoryDecomposition:
        """
        Merge all raw extractions into a complete StoryDecomposition.

        Args:
            raw_extractions: List of raw chapter extraction dicts (from raw_extractions.json)
            title: Novel title
            author: Novel author

        Returns:
            Complete StoryDecomposition model
        """
        total_chapters = len(raw_extractions)

        characters = self._merge_characters(raw_extractions)
        beats = self._merge_beats(raw_extractions)
        events = self._merge_events(raw_extractions)
        locations = self._merge_locations(raw_extractions)
        foreshadowing = self._merge_foreshadowing(raw_extractions)
        combat_power = self._merge_combat_power(raw_extractions)
        assets = self._merge_assets(raw_extractions)
        cheat_system = self._merge_cheat_system(raw_extractions)
        relationships = self._merge_relationships(raw_extractions)
        settings = self._merge_setting_revelations(raw_extractions)

        # Calculate emotional curve for rhythm analysis
        emotional_curve = self._calculate_emotional_curve(beats)

        plot = Plot(
            beats=beats,
            chapter_events=events,
            foreshadowing_tracking=foreshadowing,
            combat_power_timeline=combat_power,
            asset_timeline=assets,
        )

        world = WorldSetting(
            locations=locations,
            cheat_system=cheat_system,
        )

        style = Style()

        result = StoryDecomposition(
            title=title or "未命名",
            author=author or "未知",
            total_chapters=total_chapters,
            characters=characters,
            plot=plot,
            world_setting=world,
            relationships=relationships,
            style=style,
        )

        # Attach emotional curve for rhythm output
        result._emotional_curve = emotional_curve

        logger.info(
            "Merge complete: %d chars, %d beats, %d events, %d locations, "
            "%d foreshadows, %d combat, %d assets, %d relations, %d settings",
            len(characters), len(beats), len(events), len(locations),
            len(foreshadowing), len(combat_power), len(assets),
            len(relationships.character_relations), len(settings),
        )
        return result

    # === Beats ===

    def _merge_beats(self, raw_list: list[dict]) -> list[StoryBeat]:
        all_beats = []
        for ext in raw_list:
            ch_num = ext.get("chapter", 0)
            # new prompt outputs "beats", old prompt outputs "events"
            # serialized JSON may store beats under "events" key (extractor compat)
            raw_beats = ext.get("beats", ext.get("events", []))
            for i, b in enumerate(raw_beats):
                d = b if isinstance(b, dict) else (b.model_dump() if hasattr(b, "model_dump") else b.__dict__)
                try:
                    all_beats.append(StoryBeat(
                        chapter=ch_num,
                        beat_index=i,
                        beat_type=d.get("beat_type", ""),
                        emotional_arc=d.get("emotional_arc", ""),
                        narrative_function=d.get("narrative_function", ""),
                        intensity=int(d.get("intensity", 1) or 1),
                        location=d.get("location", ""),
                        characters_present=d.get("characters_present", []),
                        summary=d.get("summary", ""),
                        cause=d.get("cause", ""),
                        consequence=d.get("consequence", ""),
                        key_moments=d.get("key_moments", []),
                        info_released=d.get("info_released", ""),
                        dialogue_signposts=d.get("dialogue_signposts", []),
                    ))
                except Exception:
                    pass
        all_beats.sort(key=lambda b: (b.chapter, b.beat_index))
        return all_beats

    # === Characters ===

    def _merge_characters(self, raw_list: list[dict]) -> list[Character]:
        char_map = {}
        for ext in raw_list:
            ch_num = ext.get("chapter", 0)
            for c in ext.get("characters", []):
                name = c.get("name", "") or "unknown"
                intro_ch = c.get("introduction_chapter", 0) or 0
                if name not in char_map:
                    char_map[name] = dict(
                        name=name, role=c.get("role", ""),
                        aliases=set(),
                        first_chapter=intro_ch if intro_ch else ch_num,
                        personality="", appearance="", background="",
                        states=[], ability_gains=[], combat_power=[],
                    )
                e = char_map[name]
                # Update first_chapter if earlier chapter found
                effective_ch = intro_ch if intro_ch else ch_num
                if effective_ch and effective_ch < e["first_chapter"]:
                    e["first_chapter"] = effective_ch
                for a in (c.get("aliases") or []):
                    e["aliases"].add(a)
                st = c.get("static_traits", {}) or {}
                if isinstance(st, dict):
                    if st.get("personality", "") and len(st.get("personality", "")) > len(e["personality"]):
                        e["personality"] = st["personality"]
                    if st.get("appearance", "") and len(st.get("appearance", "")) > len(e["appearance"]):
                        e["appearance"] = st["appearance"]
                ident = c.get("identity", {}) or {}
                if isinstance(ident, dict):
                    bg = ident.get("background", "")
                    if bg and len(bg) > len(e["background"]):
                        e["background"] = bg
                new_traits = c.get("new_traits", {}) or {}
                if isinstance(new_traits, dict):
                    p = new_traits.get("personality", "")
                    a = new_traits.get("appearance", "")
                    if p and len(p) > len(e["personality"]):
                        e["personality"] = p
                    if a and len(a) > len(e["appearance"]):
                        e["appearance"] = a
                elif isinstance(new_traits, str) and new_traits:
                    if len(new_traits) > len(e["personality"]):
                        e["personality"] = new_traits
                # chapter state — handle both state_timeline (array) and chapter_state (single obj)
                states_data = c.get("state_timeline") or c.get("chapter_state")
                if states_data is None:
                    states_data = []
                elif isinstance(states_data, dict):
                    states_data = [states_data]
                elif isinstance(states_data, str):
                    states_data = [{"emotional": states_data}]
                for st_entry in states_data:
                    if not isinstance(st_entry, dict):
                        continue
                    emotional = st_entry.get("emotional", "")
                    goal = st_entry.get("goal", "")
                    location = st_entry.get("location", "")
                    key_actions = st_entry.get("key_actions", [])
                    st_ch = st_entry.get("chapter", ch_num)
                    if not isinstance(key_actions, list):
                        key_actions = [str(key_actions)] if key_actions else []
                    if emotional or goal or location:
                        try:
                            e["states"].append(CharacterState(
                                chapter=st_ch, emotional=str(emotional or ""),
                                goal=str(goal or ""), location=str(location or ""),
                                key_actions=key_actions or [],
                            ))
                        except Exception:
                            pass
                # abilities — handle abilities_timeline (array) and ability_changes (array)
                ab_list = c.get("abilities_timeline") or c.get("ability_changes") or []
                for ab in ab_list:
                    if isinstance(ab, dict):
                        try:
                            abl_names = ab.get("abilities") or ab.get("ability") or []
                            if isinstance(abl_names, str):
                                abl_names = [abl_names]
                            e["ability_gains"].append(AbilityGain(
                                chapter=ch_num,
                                abilities=abl_names,
                                context=ab.get("context", ""),
                            ))
                        except Exception:
                            pass

        # Normalize: merge duplicate names (LLM naming inconsistencies)
        char_map = self._normalize_character_names(char_map)

        characters = []
        for data in char_map.values():
            data["states"].sort(key=lambda s: s.chapter)
            try:
                characters.append(Character(
                    name=data["name"], role=data["role"],
                    aliases=sorted(data["aliases"]),
                    introduction_chapter=data["first_chapter"],
                    static_traits=StaticTraits(
                        personality=data["personality"],
                        appearance=data["appearance"],
                    ),
                    identity=Identity(background=data["background"]),
                    state_timeline=data["states"],
                    abilities_timeline=data["ability_gains"],
                    arc=CharacterArc(),
                ))
            except Exception as e:
                logger.warning(f"Could not create character {data['name']}: {e}")
        return characters

    def _normalize_character_names(self, char_map: dict) -> dict:
        """Merge duplicate character entries caused by LLM naming inconsistencies."""
        import re

        # Sort by state count descending — merge less-frequent into more-frequent
        sorted_names = sorted(char_map, key=lambda n: len(char_map[n]["states"]), reverse=True)
        merged = set()
        result = {}

        # Generic terms that should NOT be used for substring matching
        GENERIC_NAMES = {
            "年轻人", "男子", "女子", "老人", "小孩", "童子", "小童", "少年",
            "老者", "大汉", "妇人", "公子", "小姐", "姑娘", "书生", "剑客",
            "刀客", "枪客", "道人", "和尚", "太监", "公公", "侍女", "侍从",
            "黑衣人", "白衣人", "青衣人", "紫衣人", "红衣人", "灰衣人",
            "车夫", "屠夫", "卖油郎", "店小二", "乞丐", "商人", "士兵",
            "为首", "众弟子", "众人", "来人", "声音", "弟子", "门人",
            "剑仙", "神秘人", "白衣男子", "青衣男子", "黑衣男子",
            "白衣女子", "青衣女子", "红衣女子", "紫衣女子", "黑衣女子",
            "老侯爷", "侯爷", "世子", "王妃", "公主", "皇帝", "将军",
            "首领", "头领", "帮主", "掌门", "宗主", "门主", "教主",
            "师父", "师娘", "师叔", "师伯", "师兄", "师姐", "师弟", "师妹",
        }

        # Words that indicate a DIFFERENT character when appended (don't substring-merge)
        RELATIONSHIP_SUFFIXES = [
            "师父", "师父", "弟子", "徒弟", "侍童", "侍女", "手下", "护卫", "随从",
            "父亲", "母亲", "父亲", "兄长", "弟弟", "姐姐", "妹妹", "儿子", "女儿",
            "主人", "仆人", "门人", "门客", "宗主", "帮主", "掌门", "长老", "使者",
            "将军", "元帅", "先生", "大人", "公公", "太监", "侍卫", "护卫",
        ]

        for name in sorted_names:
            if name in merged:
                continue

            # Extract real name from parenthetical: "叶小凡（叶鼎之）" → "叶鼎之"
            paren_match = re.search(r"[（(]([^）)]+)[）)]", name)
            real_name = paren_match.group(1).strip() if paren_match else ""

            # Extract base name (before parenthesis)
            base_name = name[:paren_match.start()].strip() if paren_match else name

            # Check if this name should be merged into an existing one
            merged_into = None
            for existing in result:
                existing_data = result[existing]

                # Pattern 1: name has parenthetical containing existing name
                # Skip if base_name (part before parens) is generic
                if real_name and real_name == existing and base_name not in GENERIC_NAMES:
                    merged_into = existing
                    break

                # Pattern 2: existing has parenthetical containing this name
                exist_paren = re.search(r"[（(]([^）)]+)[）)]", existing)
                exist_base = existing[:exist_paren.start()].strip() if exist_paren else existing
                if exist_paren and exist_paren.group(1).strip() == name and exist_base not in GENERIC_NAMES:
                    merged_into = existing
                    break

                # Pattern 3: name is a title-prefixed version (e.g. "执伞鬼苏暮雨" → "苏暮雨")
                # Skip if either name is generic to avoid over-merging
                if name in GENERIC_NAMES or existing in GENERIC_NAMES:
                    pass
                elif len(name) >= 3 and len(existing) >= 2:
                    shorter = name if len(name) < len(existing) else existing
                    longer = existing if len(name) < len(existing) else name
                    # Don't merge if the shorter side is a generic name
                    if shorter in GENERIC_NAMES:
                        pass
                    elif len(shorter) >= 2 and shorter in longer:
                        extra = longer.replace(shorter, "")
                        # Don't merge if shorter is inside parentheses in longer
                        # (e.g. "年轻人（百里东君？）" — 百里东君 is just a comment)
                        if _shorter_in_parens(longer, shorter):
                            pass
                        elif any(suf in extra for suf in RELATIONSHIP_SUFFIXES):
                            pass
                        else:
                            merged_into = existing
                            break

                # Pattern 4: name with question mark, extract real name
                if ("？" in base_name or "?" in base_name) and real_name:
                    if real_name == existing and base_name not in GENERIC_NAMES:
                        merged_into = existing
                        break

            # Pattern 5: existing character has this name as an alias
            if not merged_into and name not in GENERIC_NAMES:
                for existing in result:
                    existing_aliases = result[existing]["aliases"]
                    if name in existing_aliases or base_name in existing_aliases:
                        merged_into = existing
                        break

            if merged_into:
                # Merge data into the more-established character
                target = result[merged_into]
                src = char_map[name]
                target["states"].extend(src["states"])
                target["ability_gains"].extend(src["ability_gains"])
                target["combat_power"].extend(src["combat_power"])
                target["aliases"].update(src["aliases"])
                target["aliases"].add(name)
                if src["first_chapter"] < target["first_chapter"]:
                    target["first_chapter"] = src["first_chapter"]
                # Keep better role (主角 > 反派 > 配角 > 龙套)
                role_rank = {"主角": 0, "反派": 1, "配角": 2, "龙套": 3}
                if role_rank.get(src.get("role", ""), 99) < role_rank.get(target.get("role", ""), 99):
                    target["role"] = src["role"]
                for field in ("personality", "appearance", "background"):
                    if len(src.get(field, "") or "") > len(target.get(field, "") or ""):
                        target[field] = src[field]
                # If name is a parenthetical form, add the non-parenthetical part as alias
                if paren_match:
                    target["aliases"].add(base_name)
                merged.add(name)
            else:
                result[name] = char_map[name]

        # Second pass: merge characters where one's alias is another's name
        # (e.g. "南宫春水" has alias "李先生" → merge into "李先生" which has more states)
        return self._merge_by_alias_cross_reference(result)

    def _merge_by_alias_cross_reference(self, char_map: dict) -> dict:
        """Second pass: merge if character A's alias == character B's name."""
        GENERIC_NAMES = {
            "年轻人", "男子", "女子", "老人", "小孩", "童子", "小童", "少年",
            "老者", "大汉", "妇人", "公子", "小姐", "姑娘", "书生", "剑客",
            "刀客", "枪客", "道人", "和尚", "太监", "公公", "侍女", "侍从",
            "黑衣人", "白衣人", "青衣人", "紫衣人", "红衣人", "灰衣人",
            "车夫", "屠夫", "卖油郎", "店小二", "乞丐", "商人", "士兵",
            "剑仙", "神秘人", "老侯爷", "侯爷", "世子", "王妃", "公主",
            "皇帝", "将军", "首领", "头领", "帮主", "掌门", "宗主", "门主",
            "师父", "师娘", "师叔", "师伯", "师兄", "师姐", "师弟", "师妹",
        }
        sorted_names = sorted(char_map, key=lambda n: len(char_map[n]["states"]), reverse=True)
        merged = set()
        result = {}

        for name in sorted_names:
            if name in merged or name in GENERIC_NAMES:
                if name not in result:
                    result[name] = char_map[name]
                continue
            merged_into = None
            data = char_map[name]
            for existing in result:
                if existing in GENERIC_NAMES:
                    continue
                existing_data = result[existing]
                # Check if this name is in existing's aliases
                if name in existing_data["aliases"]:
                    merged_into = existing
                    break
                # Check if any of this character's aliases match existing's name
                if existing in data["aliases"]:
                    merged_into = existing
                    break

            if merged_into:
                target = result[merged_into]
                target["states"].extend(data["states"])
                target["ability_gains"].extend(data["ability_gains"])
                target["combat_power"].extend(data["combat_power"])
                target["aliases"].update(data["aliases"])
                target["aliases"].add(name)
                if data["first_chapter"] < target["first_chapter"]:
                    target["first_chapter"] = data["first_chapter"]
                role_rank = {"主角": 0, "反派": 1, "配角": 2, "龙套": 3}
                if role_rank.get(data.get("role", ""), 99) < role_rank.get(target.get("role", ""), 99):
                    target["role"] = data["role"]
                for field in ("personality", "appearance", "background"):
                    if len(data.get(field, "") or "") > len(target.get(field, "") or ""):
                        target[field] = data[field]
                merged.add(name)
            else:
                result[name] = data

        for data in result.values():
            data["states"].sort(key=lambda s: s.chapter)

        return result

    # === Events ===

    def _merge_events(self, raw_list: list[dict]) -> list[ChapterEvent]:
        all_events = []
        for ext in raw_list:
            ch_num = ext.get("chapter", 0)
            raw_events = ext.get("events", [])
            if not raw_events:
                continue
            # If first item has beat_type, this is new-format beats, skip old-style event creation
            first = raw_events[0]
            if isinstance(first, dict) and "beat_type" in first:
                # Convert beats to ChapterEvent for backward compatibility
                for b in raw_events:
                    d = b if isinstance(b, dict) else {}
                    try:
                        all_events.append(ChapterEvent(
                            chapter=ch_num,
                            location=d.get("location", ""),
                            characters=d.get("characters_present", d.get("characters", [])),
                            summary=d.get("summary", ""),
                            tone=d.get("emotional_arc", ""),
                            cause=d.get("cause", ""),
                            consequence=d.get("consequence", ""),
                            key_moments=d.get("key_moments", []),
                        ))
                    except Exception:
                        pass
                continue
            for ev in raw_events:
                d = ev if isinstance(ev, dict) else (ev.model_dump() if hasattr(ev, "model_dump") else ev.__dict__)
                try:
                    all_events.append(ChapterEvent(
                        chapter=ch_num,
                        location=d.get("location", ""),
                        characters=d.get("characters_involved", d.get("characters", [])),
                        summary=d.get("summary", ""),
                        tone=d.get("tone", ""),
                        cause=d.get("cause", ""),
                        consequence=d.get("consequence", ""),
                        key_moments=d.get("key_moments", []),
                    ))
                except Exception:
                    pass
        return all_events

    # === Locations ===

    def _merge_locations(self, raw_list: list[dict]) -> list[Location]:
        loc_map = {}
        for ext in raw_list:
            ch_num = ext.get("chapter", 0)
            for loc in (ext.get("locations") or []):
                if isinstance(loc, dict):
                    name = loc.get("name", "")
                else:
                    name = getattr(loc, "name", "")
                if not name:
                    continue
                if name not in loc_map:
                    loc_map[name] = dict(
                        name=name,
                        type=(loc.get("type", "") or "") if isinstance(loc, dict) else (getattr(loc, "type", "") or ""),
                        description=(loc.get("description", "") or "") if isinstance(loc, dict) else (getattr(loc, "description", "") or ""),
                        atmosphere=(loc.get("atmosphere", "") or "") if isinstance(loc, dict) else (getattr(loc, "atmosphere", "") or ""),
                        parent=(loc.get("parent", "") or "") if isinstance(loc, dict) else (getattr(loc, "parent", "") or ""),
                        first_chapter=ch_num,
                        appearances=[ch_num],
                    )
                else:
                    loc_map[name]["appearances"].append(ch_num)
                    if isinstance(loc, dict):
                        desc = loc.get("description", "")
                        if desc and len(desc) > len(loc_map[name].get("description", "")):
                            loc_map[name]["description"] = desc
        try:
            return [Location(**d) for d in loc_map.values()]
        except Exception as e:
            logger.warning(f"Location merge error: {e}")
            return []

    # === Foreshadowing ===

    def _merge_foreshadowing(self, raw_list: list[dict]) -> list[ForeshadowingItem]:
        # Deduplicate by id
        fs_map = {}
        for ext in raw_list:
            ch_num = ext.get("chapter", 0)
            for f in (ext.get("foreshadowing") or []):
                d = f if isinstance(f, dict) else (f.model_dump() if hasattr(f, "model_dump") else f.__dict__)
                fid = d.get("id", "")
                if not fid:
                    continue
                if fid not in fs_map:
                    fs_map[fid] = ForeshadowingItem(
                        id=str(fid) if fid else "",
                        description=d.get("description") or "",
                        planted_chapter=ch_num or 0,
                        involved_characters=d.get("involved_characters") or [],
                        estimated_purpose=d.get("estimated_purpose") or "",
                        resolved_chapter=(d.get("resolved_chapter") or 0),
                        resolution=d.get("resolution") or "",
                    )
                else:
                    # Update with resolution info if available
                    existing = fs_map[fid]
                    if d.get("resolved_chapter"):
                        existing.resolved_chapter = d["resolved_chapter"]
                    if d.get("resolution"):
                        existing.resolution = d["resolution"]
        return sorted(fs_map.values(), key=lambda x: x.planted_chapter)

    # === Combat Power ===

    def _merge_combat_power(self, raw_list: list[dict]) -> list[CombatPowerState]:
        result = []
        for ext in raw_list:
            ch_num = ext.get("chapter", 0)
            for cp in (ext.get("combat_power_changes") or []):
                d = cp if isinstance(cp, dict) else (cp.model_dump() if hasattr(cp, "model_dump") else cp.__dict__)
                try:
                    result.append(CombatPowerState(
                        chapter=ch_num,
                        level=d.get("level_after", d.get("level", "")),
                        sub_level=d.get("sub_level", ""),
                        change_description=d.get("change_description", d.get("change", "")),
                    ))
                except Exception:
                    pass
        return sorted(result, key=lambda x: x.chapter)

    # === Assets ===

    def _merge_assets(self, raw_list: list[dict]) -> list[AssetChange]:
        result = []
        for ext in raw_list:
            ch_num = ext.get("chapter", 0)
            for a in (ext.get("asset_changes") or []):
                d = a if isinstance(a, dict) else (a.model_dump() if hasattr(a, "model_dump") else a.__dict__)
                try:
                    qty = d.get("quantity", "")
                    result.append(AssetChange(
                        chapter=ch_num,
                        operation=d.get("operation", ""),
                        item_name=d.get("item_name", ""),
                        quantity=str(qty) if qty else "",
                        source_or_target=d.get("source_or_target", ""),
                    ))
                except Exception:
                    pass
        return sorted(result, key=lambda x: x.chapter)

    # === Cheat System ===

    def _merge_cheat_system(self, raw_list: list[dict]) -> CheatSystem:
        stages = []
        for ext in raw_list:
            ch_num = ext.get("chapter", 0)
            for cs in (ext.get("cheat_system_changes") or []):
                d = cs if isinstance(cs, dict) else (cs.model_dump() if hasattr(cs, "model_dump") else cs.__dict__)
                try:
                    stages.append(CheatStage(
                        chapter=ch_num,
                        stage_name=d.get("system_name", d.get("stage_name", "")),
                        description=d.get("description", ""),
                        new_features=d.get("new_abilities", d.get("new_features", [])),
                        limitations=d.get("limitations", ""),
                    ))
                except Exception:
                    pass
        return CheatSystem(name="", evolution_stages=stages)

    # === Relationships ===

    def _merge_relationships(self, raw_list: list[dict]) -> Relationships:
        rel_map = defaultdict(list)
        for ext in raw_list:
            ch_num = ext.get("chapter", 0)
            for rc in (ext.get("relationship_changes") or []):
                d = rc if isinstance(rc, dict) else (rc.model_dump() if hasattr(rc, "model_dump") else rc.__dict__)
                a = d.get("from", "") or d.get("character_a", "")
                b = d.get("to", "") or d.get("character_b", "")
                status = d.get("new_status", "") or d.get("status", "")
                if a and b:
                    rel_map[(a, b)].append(dict(chapter=ch_num, status=status))

        relations = []
        for (a, b), changes in rel_map.items():
            evolutions = []
            for ch in sorted(changes, key=lambda x: x["chapter"]):
                try:
                    evolutions.append(RelationEvolution(
                        chapter=ch["chapter"], status=ch["status"],
                    ))
                except Exception:
                    pass
            if evolutions:
                try:
                    relations.append(CharacterRelation(
                        from_char=a, to=b,
                        type=evolutions[-1].status if evolutions else "",
                        start_chapter=evolutions[0].chapter if evolutions else 0,
                        evolution=evolutions,
                    ))
                except Exception:
                    pass
        return Relationships(character_relations=relations)

    # === Setting Revelations ===

    def _merge_setting_revelations(self, raw_list: list[dict]) -> list[dict]:
        result = []
        for ext in raw_list:
            ch_num = ext.get("chapter", 0)
            for sr in (ext.get("setting_revelations") or []):
                d = sr if isinstance(sr, dict) else sr
                d["_chapter"] = ch_num
                result.append(d)
        return result

    # === Emotional Curve ===

    def _calculate_emotional_curve(self, beats: list[StoryBeat]) -> list[dict]:
        """Calculate per-chapter emotional intensity and dominant tone."""
        ch_emotions = defaultdict(list)
        for b in beats:
            ch_emotions[b.chapter].append(b.intensity)

        curve = []
        for ch in sorted(ch_emotions):
            intensities = ch_emotions[ch]
            curve.append({
                "chapter": ch,
                "beat_count": len(intensities),
                "avg_intensity": round(sum(intensities) / len(intensities), 1),
                "max_intensity": max(intensities),
                "min_intensity": min(intensities),
            })
        return curve
