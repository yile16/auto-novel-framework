"""Markdown writer v3 — produces comprehensive author's setting bible.

Output files:
  outline.md      — chapter-by-chapter synopsis (story at a glance)
  characters.md   — full character profiles with equipment, skills, changes
  world.md        — complete setting bible (geography, factions, power, techniques, items)
  relationships.md — relationship evolution with initial/middle/final states
  beats.md        — narrative beats (atomic storytelling units)
  rhythm.md       — emotional curve & pacing calendar
  index.md        — overview with stats and navigation
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from core.models.story import StoryDecomposition
from core.models.character import Character
from core.models.setting import Location, Faction, PowerSystem, PowerStage, CheatStage, SpecialItem


def _md(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _pick_longest(*texts: str) -> str:
    return max((t or "" for t in texts), key=len)


def write_all(decomp: StoryDecomposition, output_dir: Path, raw_extractions: list[dict] | None = None) -> list[Path]:
    """Write all markdown files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Pre-process: build lookup tables from raw data
    ctx = _build_context(decomp, raw_extractions or [])

    paths = [
        write_outline(decomp, output_dir, ctx),
        write_characters(decomp, output_dir, ctx),
        write_world(decomp, output_dir, ctx),
        write_relationships(decomp, output_dir),
        write_beats(decomp, output_dir),
        write_rhythm(decomp, output_dir),
        write_index(decomp, output_dir, ctx),
    ]
    return [p for p in paths if p]


# ============================================================
# Context builder — synthesizes info across chapters
# ============================================================

def _build_context(decomp: StoryDecomposition, raw_list: list[dict]) -> dict:
    """Build cross-reference tables from raw extractions."""
    # Character → equipment from asset_changes
    char_equipment = defaultdict(list)
    char_skills = defaultdict(list)
    char_combat = defaultdict(list)

    # Factions from setting_revelations
    factions_map = {}
    # Power system from setting_revelations
    power_rules = []
    # World history
    history_entries = []
    # All items
    all_items = []
    # All techniques
    all_techniques = []
    # Setting revelations by category
    settings_by_cat = defaultdict(list)

    for ext in raw_list:
        ch = ext.get("chapter", 0)

        # Equipment/items per character (from asset_changes)
        for ac in ext.get("asset_changes", []):
            item_name = (ac.get("item_name") or "").strip()
            if not item_name:
                continue
            all_items.append({
                "chapter": ch,
                "name": item_name,
                "operation": ac.get("operation", ""),
                "source_or_target": ac.get("source_or_target", ""),
            })

        # Skills/abilities per character (from ability_gains)
        for ag in ext.get("ability_gains", []):
            char_name = ag.get("character", "")
            for ab in ag.get("abilities", []):
                char_skills[char_name].append({
                    "chapter": ch,
                    "ability": ab,
                    "context": ag.get("context", ""),
                })
                all_techniques.append({
                    "chapter": ch,
                    "name": ab,
                    "character": char_name,
                    "context": ag.get("context", ""),
                })

        # Combat power changes
        for cp in ext.get("combat_power_changes", []):
            char_combat[cp.get("character", "")].append({
                "chapter": ch,
                "level_before": cp.get("level_before", ""),
                "level_after": cp.get("level_after", ""),
                "change_description": cp.get("change_description", ""),
            })

        # Setting revelations
        for sr in ext.get("setting_revelations", []):
            cat = sr.get("category", "其他")
            content = sr.get("content", "")
            settings_by_cat[cat].append({
                "chapter": ch,
                "content": content,
                "revealed_through": sr.get("revealed_through", ""),
            })

            # Extract factions
            if cat in ("势力关系", "社会制度"):
                _extract_faction_info(content, ch, factions_map)

            # Extract power system
            if cat == "修炼体系":
                power_rules.append({"chapter": ch, "content": content})

            # History
            if cat == "历史背景":
                history_entries.append({"chapter": ch, "content": content})

    # Build factions list
    factions = list(factions_map.values())

    # Build power system
    power_system = PowerSystem()
    if power_rules:
        power_system = PowerSystem(
            name="修炼体系",
            stages=[PowerStage(name=f"第{r['chapter']}章揭示", levels="", description=r["content"][:200]) for r in power_rules[:20]],
            special_rules=[],
        )

    # Build special items
    special_items = []
    seen_items = set()
    for item in all_items:
        name = item["name"]
        if name not in seen_items and len(name) > 1:
            seen_items.add(name)
            special_items.append(SpecialItem(
                name=name,
                first_chapter=item["chapter"],
            ))

    return {
        "char_equipment": dict(char_equipment),
        "char_skills": dict(char_skills),
        "char_combat": dict(char_combat),
        "factions": factions,
        "power_system": power_system,
        "power_rules": power_rules,
        "history_entries": history_entries,
        "all_items": all_items,
        "all_techniques": all_techniques,
        "special_items": special_items,
        "settings_by_cat": dict(settings_by_cat),
        "raw_extractions_count": len(raw_list),
    }


def _extract_faction_info(content: str, ch: int, factions_map: dict):
    """Try to extract faction names from setting revelation content."""
    # Simple heuristic: look for known patterns
    triggers = ["组织", "宗门", "帮", "教", "派", "府", "阁", "楼", "谷", "城", "国", "族", "盟", "会", "司", "堂", "门", "殿", "宫", "坊", "院", "江湖"]
    for t in triggers:
        if t in content:
            # Extract the full name (word before and including trigger)
            idx = content.index(t)
            start = max(0, idx - 4)
            end = min(len(content), idx + len(t) + 2)
            name = content[start:end].strip("，。、；：""''！？…—")
            if len(name) >= 2:
                key = name
                if key not in factions_map:
                    factions_map[key] = Faction(
                        name=name,
                        type="",
                        description=content[:200],
                        key_members=[],
                    )
                else:
                    # Append more info
                    f = factions_map[key]
                    if len(content) > len(f.description or ""):
                        f.description = content[:200]


# ============================================================
# outline.md — Chapter synopsis at a glance
# ============================================================

def write_outline(decomp: StoryDecomposition, output_dir: Path, ctx: dict) -> Path:
    beats = decomp.plot.beats
    chars = {c.name: c for c in decomp.characters}

    # Group beats by chapter
    ch_beats = defaultdict(list)
    for b in beats:
        ch_beats[b.chapter].append(b)

    lines = [
        "# 故事章纲 — 全书概要",
        "",
        f"共 **{len(ch_beats)}** 章，**{len(beats)}** 个叙事节拍",
        "",
        "> 每章几句话概述：人物、地点、做了什么、发生了什么。一眼看到头。",
        "",
        "---",
        "",
    ]

    for ch in sorted(ch_beats):
        b_list = ch_beats[ch]
        # Gather chapter-level info
        characters_set = set()
        locations_set = set()
        for b in b_list:
            for c in b.characters_present:
                characters_set.add(c)
            if b.location:
                locations_set.add(b.location)

        # Build 2-3 sentence summary
        summaries = [b.summary for b in b_list if b.summary]
        full_summary = "；".join(summaries[:5])  # first 5 beat summaries
        if len(full_summary) > 300:
            full_summary = full_summary[:297] + "..."

        # Intensity
        avg_intensity = sum(b.intensity for b in b_list) / len(b_list)
        bar = "🔥" if avg_intensity >= 4 else "⚡" if avg_intensity >= 3 else "📖"

        # Key beats
        key_type = ", ".join(sorted(set(b.beat_type for b in b_list if b.beat_type)))

        lines.extend([
            f"## 第{ch}章 {bar}",
            "",
            f"| 维度 | 内容 |",
            f"| --- | --- |",
            f"| **节拍数** | {len(b_list)} |",
            f"| **情绪强度** | {avg_intensity:.1f}/5 |",
            f"| **节拍类型** | {key_type or '-'} |",
            f"| **人物** | {', '.join(sorted(characters_set)[:8]) or '-'} |",
            f"| **地点** | {', '.join(sorted(locations_set)[:5]) or '-'} |",
            f"| **概要** | {_md(full_summary)} |",
            "",
        ])

    path = output_dir / "outline.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ============================================================
# characters.md — Full character profiles
# ============================================================

def write_characters(decomp: StoryDecomposition, output_dir: Path, ctx: dict) -> Path:
    chars = decomp.characters
    skills_map = ctx["char_skills"]
    combat_map = ctx["char_combat"]
    assets = decomp.plot.asset_timeline

    # Sort: by importance (state_timeline length), then role
    role_prio = {"主角": 0, "反派": 1, "配角": 2, "龙套": 3}
    chars_sorted = sorted(chars, key=lambda c: (
        role_prio.get(c.role, 99),
        -len(c.state_timeline),
    ))

    main_chars = [c for c in chars_sorted if c.role in ("主角", "反派", "配角") and len(c.state_timeline) >= 3]
    extras = [c for c in chars_sorted if c not in main_chars]

    lines = [
        "# 人物设定集",
        "",
        f"共 **{len(chars)}** 个角色（主要角色 {len(main_chars)} 人，龙套 {len(extras)} 人）",
        "",
        "---",
        "",
        "## 角色总表",
        "",
        "| # | 角色 | 定位 | 登场 | 出场章数 | 状态追踪 | 能力 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]

    for i, c in enumerate(chars_sorted, 1):
        intro_ch = c.introduction_chapter or (c.state_timeline[0].chapter if c.state_timeline else 0)
        abilities_count = len(c.abilities_timeline) + len(skills_map.get(c.name, []))
        lines.append(
            f"| {i} | **{_md(c.name)}** | {c.role} | "
            f"第{intro_ch}章 | {len(c.state_timeline)}章 | "
            f"{len(c.state_timeline)}次 | {abilities_count}项 |"
        )

    # === Main character profiles ===
    lines.extend([
        "",
        "---",
        "",
        "## 主要角色列传",
        "",
    ])

    for c in main_chars:
        _write_character_profile(c, lines, skills_map, combat_map, assets)

    # === Extras summary ===
    if extras:
        lines.extend([
            "---",
            "",
            "## 龙套角色一览",
            "",
            "| 角色 | 定位 | 登场章 | 出场次数 |",
            "| --- | --- | --- | --- |",
        ])
        for c in extras:
            intro = c.introduction_chapter or (c.state_timeline[0].chapter if c.state_timeline else 0)
            lines.append(f"| {_md(c.name)} | {c.role} | 第{intro}章 | {len(c.state_timeline)}章 |")

    path = output_dir / "characters.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _write_character_profile(c: Character, lines: list, skills_map: dict, combat_map: dict, assets: list):
    """Write a detailed profile for one character."""
    # Collect all info
    personality = c.static_traits.personality if c.static_traits else ""
    appearance = c.static_traits.appearance if c.static_traits else ""
    background = c.identity.background if c.identity else ""

    # Skills
    c_skills = skills_map.get(c.name, [])
    c_combat = combat_map.get(c.name, [])

    # Equipment from asset timeline (approximate - match character name)
    c_equipment = [a for a in assets if c.name in (a.source_or_target or "")]

    intro_ch = c.introduction_chapter or (c.state_timeline[0].chapter if c.state_timeline else 0)
    aliases_str = "、".join(c.aliases) if c.aliases else "无"

    # Header
    role_emoji = {"主角": "🌟", "反派": "💀", "配角": "👤", "龙套": "👥"}.get(c.role, "")
    lines.extend([
        f"### {role_emoji} {c.name}",
        "",
        f"| 属性 | 内容 |",
        f"| --- | --- |",
        f"| **定位** | {c.role or '-'} |",
        f"| **别名** | {aliases_str} |",
        f"| **登场** | 第{intro_ch}章 |",
        f"| **出场** | {len(c.state_timeline)}章 |",
    ])

    if personality:
        lines.append(f"| **性格** | {_md(personality)} |")
    if appearance:
        lines.append(f"| **外貌** | {_md(appearance)} |")
    if background:
        lines.append(f"| **背景** | {_md(background)} |")

    # Character arc
    arc = c.arc
    if arc:
        if arc.growth_trajectory:
            lines.append(f"| **成长轨迹** | {_md(arc.growth_trajectory)} |")
        if arc.core_conflict:
            lines.append(f"| **核心矛盾** | {_md(arc.core_conflict)} |")

    lines.append("")

    # Abilities/Skills timeline
    if c.abilities_timeline or c_skills:
        lines.append("#### 技能/功法")
        lines.append("")
        lines.append("| 章节 | 技能 | 场景 |")
        lines.append("| --- | --- | --- |")
        for ab in c.abilities_timeline:
            ab_names = "、".join(ab.abilities) if ab.abilities else "-"
            lines.append(f"| {ab.chapter} | {_md(ab_names)} | {_md(ab.context) if ab.context else '-'} |")
        for sk in c_skills:
            if not any(a.chapter == sk["chapter"] and sk["ability"] in "、".join(a.abilities) for a in c.abilities_timeline):
                lines.append(f"| {sk['chapter']} | {_md(sk['ability'])} | {_md(sk.get('context','')) or '-'} |")
        lines.append("")

    # Combat power progression
    if c_combat or c.combat_power_timeline:
        lines.append("#### 实力进阶")
        lines.append("")
        lines.append("| 章节 | 变化 |")
        lines.append("| --- | --- |")
        for cp in c_combat:
            fallback = cp.get('level_before','?') + " → " + cp.get('level_after','?')
            lines.append(f"| {cp['chapter']} | {_md(cp['change_description']) or _md(fallback)} |")
        for cp in c.combat_power_timeline:
            lines.append(f"| {cp.chapter} | {_md(cp.change)} |")
        lines.append("")

    # Equipment/Items
    if c_equipment:
        lines.append("#### 装备/物品")
        lines.append("")
        lines.append("| 章节 | 操作 | 物品 |")
        lines.append("| --- | --- | --- |")
        for a in c_equipment:
            lines.append(f"| {a.chapter} | {a.operation} | {_md(a.item_name)} |")
        lines.append("")

    # State timeline (key changes only — every 5 chapters)
    if c.state_timeline:
        lines.append("#### 状态追踪（抽要）")
        lines.append("")
        lines.append("| 章节 | 情绪 | 目标 | 位置 |")
        lines.append("| --- | --- | --- | --- |")
        states = c.state_timeline
        # Show first 5, then every 5th, then last 3
        show_indices = set()
        show_indices.update(range(min(5, len(states))))
        show_indices.update(range(0, len(states), max(1, len(states)//15)))
        show_indices.update(range(max(0, len(states)-3), len(states)))
        for i in sorted(show_indices):
            if i < len(states):
                s = states[i]
                lines.append(
                    f"| {s.chapter} | {_md(s.emotional) if s.emotional else '-'} | "
                    f"{_md(s.goal) if s.goal else '-'} | {_md(s.location) if s.location else '-'} |"
                )
        lines.append("")


# ============================================================
# world.md — Complete setting bible
# ============================================================

def write_world(decomp: StoryDecomposition, output_dir: Path, ctx: dict) -> Path:
    locations = decomp.world_setting.locations
    cheat = decomp.world_setting.cheat_system
    factions = ctx["factions"]
    power_rules = ctx["power_rules"]
    history_entries = ctx["history_entries"]
    all_techniques = ctx["all_techniques"]
    all_items = ctx["all_items"]
    settings_by_cat = ctx["settings_by_cat"]
    special_items = ctx["special_items"]

    lines = [
        "# 世界观设定集",
        "",
        "---",
        "",
    ]

    # === 1. World Overview ===
    lines.extend([
        "## 一、世界概述",
        "",
        f"**书名**: {decomp.title}  ",
        f"**作者**: {decomp.author}  ",
        f"**总章节**: {decomp.total_chapters}  ",
        "",
    ])

    # History entries
    if history_entries:
        lines.append("### 历史背景")
        lines.append("")
        for h in history_entries[:30]:
            lines.append(f"- 第{h['chapter']}章: {_md(h['content'][:200])}")
        lines.append("")

    # === 2. Geography ===
    lines.extend([
        "## 二、地理志",
        "",
        f"共 **{len(locations)}** 个地点",
        "",
    ])

    # Build location hierarchy
    locs_sorted = sorted(locations, key=lambda l: -(len(getattr(l, "appearances", []) or [])))
    parent_map = defaultdict(list)
    for loc in locs_sorted:
        parent = getattr(loc, "parent", "") or ""
        if parent:
            parent_map[parent].append(loc.name)
        else:
            parent_map[""].append(loc.name)

    # Location table
    lines.append("### 地点总表")
    lines.append("")
    lines.append("| 地点 | 类型 | 氛围 | 上级 | 首次出现 | 出现次数 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for loc in locs_sorted:
        apps = getattr(loc, "appearances", []) or []
        lines.append(
            f"| {_md(loc.name)} | {loc.type or '-'} | {_md(loc.atmosphere) if loc.atmosphere else '-'} | "
            f"{loc.parent or '-'} | 第{loc.first_chapter}章 | {len(apps)}次 |"
        )
    lines.append("")

    # Location hierarchy tree
    lines.append("### 地点层级")
    lines.append("")
    _write_location_tree(locs_sorted, lines)
    lines.append("")

    # === 3. Factions ===
    lines.extend([
        "## 三、势力录",
        "",
        f"共识别 **{len(factions)}** 个势力/组织",
        "",
    ])

    if factions:
        lines.append("| 势力 | 描述 | 首次提及 |")
        lines.append("| --- | --- | --- |")
        for f in factions:
            timeline_first = f.timeline[0].chapter if f.timeline else "?"
            lines.append(f"| **{_md(f.name)}** | {_md(f.description or '')[:150]} | 第{timeline_first}章 |")
        lines.append("")

    # === 4. Power System ===
    lines.extend([
        "## 四、修炼体系",
        "",
    ])

    if power_rules:
        lines.append(f"共 **{len(power_rules)}** 条修炼规则揭示")
        lines.append("")
        lines.append("| 章节 | 规则 |")
        lines.append("| --- | --- |")
        for pr in power_rules[:50]:
            lines.append(f"| {pr['chapter']} | {_md(pr['content'][:200])} |")
        lines.append("")
    else:
        lines.append("（本作未涉及明确的修炼等级体系，以武学招式为主）")
        lines.append("")

    # === 5. Techniques ===
    lines.extend([
        "## 五、功法武技录",
        "",
        f"共 **{len(all_techniques)}** 项功法/技能",
        "",
    ])

    if all_techniques:
        # Deduplicate
        seen_tech = set()
        lines.append("| # | 功法/技能 | 习得者 | 章节 | 场景 |")
        lines.append("| --- | --- | --- | --- | --- |")
        for i, t in enumerate(all_techniques, 1):
            key = t["name"][:30]
            if key not in seen_tech:
                seen_tech.add(key)
                lines.append(
                    f"| {i} | **{_md(t['name'])}** | {t['character'] or '-'} | "
                    f"第{t['chapter']}章 | {_md(t.get('context','') or '')[:80]} |"
                )
        lines.append("")

    # === 6. Items/Equipment ===
    lines.extend([
        "## 六、神兵宝器录",
        "",
        f"共 **{len(all_items)}** 条物品/装备变动",
        "",
    ])

    if all_items:
        # Group by item name
        item_groups = defaultdict(list)
        for item in all_items:
            item_groups[item["name"]].append(item)

        lines.append("| 物品 | 首次出现 | 变动次数 | 操作记录 |")
        lines.append("| --- | --- | --- | --- |")
        for name, entries in sorted(item_groups.items(), key=lambda x: -len(x[1])):
            if len(name) < 2:
                continue
            first_ch = min(e["chapter"] for e in entries)
            ops = "、".join(f"第{e['chapter']}章{e['operation']}" for e in entries[:5])
            if len(entries) > 5:
                ops += f"... 共{len(entries)}次"
            lines.append(f"| {_md(name)} | 第{first_ch}章 | {len(entries)} | {_md(ops)} |")
        lines.append("")

    # === 7. Cheat System ===
    if cheat and cheat.evolution_stages:
        lines.extend([
            "## 七、金手指/外挂系统",
            "",
            f"**系统名**: {cheat.name or '未命名'}",
            "",
            "| 章节 | 阶段 | 新功能 | 限制 |",
            "| --- | --- | --- | --- |",
        ])
        for stage in cheat.evolution_stages:
            lines.append(
                f"| {stage.chapter} | {_md(stage.stage_name)} | "
                f"{'<br>'.join(stage.new_features) if stage.new_features else '-'} | "
                f"{_md(stage.limitations) if stage.limitations else '-'} |"
            )
        lines.append("")

    # === 8. Setting Revelations by Category ===
    lines.extend([
        "## 八、设定揭秘（按类别）",
        "",
    ])

    for cat in ["修炼体系", "社会制度", "历史背景", "势力关系", "物品设定", "地理设定", "人物背景", "种族设定"]:
        entries = settings_by_cat.get(cat, [])
        if not entries:
            continue
        lines.append(f"### {cat}（{len(entries)}条）")
        lines.append("")
        for e in entries[:30]:  # first 30 per category
            lines.append(f"- 第{e['chapter']}章: {_md(e['content'][:200])}")
        if len(entries) > 30:
            lines.append(f"- ... 共{len(entries)}条")
        lines.append("")

    path = output_dir / "world.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _write_location_tree(locations: list[Location], lines: list):
    """Write location hierarchy as nested markdown lists."""
    parent_map = defaultdict(list)
    for loc in locations:
        parent = getattr(loc, "parent", "") or ""
        parent_map[parent].append(loc)

    def write_children(parent: str, depth: int):
        children = sorted(parent_map.get(parent, []), key=lambda l: l.name)
        for child in children:
            indent = "  " * depth
            apps = getattr(child, "appearances", []) or []
            lines.append(f"{indent}- **{child.name}** ({child.type or '地点'}) — 出现{len(apps)}次")
            write_children(child.name, depth + 1)

    write_children("", 0)


# ============================================================
# relationships.md — with initial/middle/final states
# ============================================================

def write_relationships(decomp: StoryDecomposition, output_dir: Path) -> Path:
    relations = decomp.relationships.character_relations
    rels_sorted = sorted(relations, key=lambda r: -len(r.evolution))

    lines = [
        "# 关系网络",
        "",
        f"共 **{len(relations)}** 对角色关系",
        "",
        "---",
        "",
        "## 关系总表",
        "",
        "| 角色A | 角色B | 初始关系 | 最终关系 | 初建章 | 演化次数 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]

    for r in rels_sorted:
        initial = r.evolution[0].status if r.evolution else "-"
        final = r.evolution[-1].status if r.evolution else "-"
        lines.append(
            f"| {_md(r.from_char)} | {_md(r.to)} | {_md(initial)} | "
            f"{_md(final)} | 第{r.start_chapter}章 | {len(r.evolution)} |"
        )

    # Top 30 detailed evolution
    lines.extend([
        "",
        "---",
        "",
        "## 主要关系演化（前30）",
        "",
    ])

    for r in rels_sorted[:30]:
        evolutions = r.evolution
        initial = evolutions[0].status if evolutions else "?"
        middle = evolutions[len(evolutions)//2].status if len(evolutions) >= 3 else "-"
        final = evolutions[-1].status if evolutions else "?"

        lines.extend([
            f"### {r.from_char} ↔ {r.to}",
            "",
            f"| 属性 | 内容 |",
            f"| --- | --- |",
            f"| **初始** | {_md(initial)}（第{evolutions[0].chapter if evolutions else '?'}章） |",
            f"| **中途** | {_md(middle)} |",
            f"| **最终** | {_md(final)}（第{evolutions[-1].chapter if evolutions else '?'}章） |",
            f"| **跨越** | 第{r.start_chapter}章 ~ 第{evolutions[-1].chapter if evolutions else '?'}章（{evolutions[-1].chapter - r.start_chapter if evolutions else 0}章） |",
            "",
            "**演化过程**:",
            "",
        ])

        # Show key turning points only (status changes)
        prev_status = ""
        for ev in evolutions:
            if ev.status != prev_status:
                lines.append(f"- 第{ev.chapter}章: **{prev_status}** → **{ev.status}**")
                prev_status = ev.status
            else:
                lines.append(f"- 第{ev.chapter}章: {ev.status}")
        lines.append("")

    path = output_dir / "relationships.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ============================================================
# beats.md — Atomic narrative beats
# ============================================================

def write_beats(decomp: StoryDecomposition, output_dir: Path) -> Path:
    beats = decomp.plot.beats
    lines = [
        "# 叙事节拍 — 全书原子叙事单元",
        "",
        f"共 **{len(beats)}** 个节拍",
        "",
        "> 节拍 = 一个因果动作 + 一个情绪转折。LLM 拿到每个节拍卡片即可展开为完整叙事段落。",
        "",
        "---",
        "",
    ]

    current_ch = 0
    for b in beats:
        if b.chapter != current_ch:
            current_ch = b.chapter
            lines.append(f"## 第 {current_ch} 章")
            lines.append("")

        type_icon = {"铺垫": "📋", "冲突": "⚔️", "反转": "🔄", "释放": "💥", "过渡": "➡️"}.get(b.beat_type, "")
        func_icon = {
            "推进主线": "主线", "塑造人物": "人物", "揭示设定": "设定",
            "制造悬念": "悬念", "调节节奏": "节奏",
        }.get(b.narrative_function, b.narrative_function)

        lines.extend([
            f"### {b.chapter}.{b.beat_index + 1} {type_icon}",
            "",
            f"| 维度 | 内容 |",
            f"| --- | --- |",
            f"| **类型** | {_md(b.beat_type)} |",
            f"| **情绪弧** | {_md(b.emotional_arc)} |",
            f"| **功能** | {_md(func_icon)} |",
            f"| **强度** | {'★' * b.intensity}{'☆' * (5 - b.intensity)} ({b.intensity}/5) |",
            f"| **地点** | {_md(b.location)} |",
            f"| **人物** | {', '.join(b.characters_present) if b.characters_present else '-'} |",
            f"| **摘要** | {_md(b.summary)} |",
            f"| **触发因** | {_md(b.cause)} |",
            f"| **后果** | {_md(b.consequence)} |",
        ])

        if b.key_moments:
            moments = "<br>".join(f"• {_md(m)}" for m in b.key_moments)
            lines.append(f"| **关键瞬间** | {moments} |")

        if b.info_released:
            lines.append(f"| **信息释放** | {_md(b.info_released)} |")

        if b.dialogue_signposts:
            signs = "<br>".join(f"• {_md(d)}" for d in b.dialogue_signposts)
            lines.append(f"| **对话路标** | {signs} |")

        lines.append("")

    path = output_dir / "beats.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ============================================================
# rhythm.md — Emotional curve & pacing
# ============================================================

def write_rhythm(decomp: StoryDecomposition, output_dir: Path) -> Path:
    beats = decomp.plot.beats
    ch_emotions = _chapter_emotions(beats)
    climaxes = [ce for ce in ch_emotions if ce["max_intensity"] >= 4]

    hooks = []
    for ch in sorted(set(b.chapter for b in beats)):
        ch_beats = [b for b in beats if b.chapter == ch]
        if ch_beats:
            last = ch_beats[-1]
            hooks.append({
                "chapter": ch,
                "end_emotion": last.emotional_arc.split("→")[-1].strip() if "→" in last.emotional_arc else "",
                "end_type": last.beat_type,
                "last_summary": last.summary[:80],
            })

    lines = [
        "# 节奏日历 — 情绪曲线与爽点分布",
        "",
        "---",
        "",
        "## 逐章情绪曲线",
        "",
        "| 章节 | 节拍数 | 平均强度 | 最高 | 最低 | 曲线 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]

    for ce in ch_emotions:
        bar = "█" * int(ce["avg_intensity"]) + "░" * (5 - int(ce["avg_intensity"]))
        lines.append(
            f"| {ce['chapter']} | {ce['beat_count']} | "
            f"{ce['avg_intensity']} | {ce['max_intensity']} | {ce['min_intensity']} | "
            f"{bar} |"
        )

    # Climax analysis
    if climaxes:
        climax_chs = [c['chapter'] for c in climaxes]
        gaps = [climax_chs[i+1] - climax_chs[i] for i in range(len(climax_chs)-1)]
        avg_gap = sum(gaps) / len(gaps) if gaps else 0

        lines.extend([
            "",
            "## 高潮节点（强度≥4）",
            "",
            f"共 **{len(climaxes)}** 个高潮章节",
            "",
            "| 章节 | 节拍数 | 最高强度 |",
            "| --- | --- | --- |",
        ])
        for cl in climaxes[:30]:
            lines.append(f"| {cl['chapter']} | {cl['beat_count']} | {'★' * cl['max_intensity']} |")

        lines.extend([
            "",
            "## 节奏分析",
            "",
            f"- 高潮总数: **{len(climaxes)}**",
            f"- 平均高潮间距: **{avg_gap:.1f}章**",
            f"- 最短间距: **{min(gaps) if gaps else 0}章**",
            f"- 最长间距: **{max(gaps) if gaps else 0}章**",
        ])

    # Chapter ending hooks
    lines.extend([
        "",
        "## 章末钩子",
        "",
        "| 章节 | 结束情绪 | 末拍类型 | 结尾线索 |",
        "| --- | --- | --- | --- |",
    ])
    for h in hooks[:50]:
        lines.append(
            f"| {h['chapter']} | {h['end_emotion'] or '-'} | "
            f"{h['end_type'] or '-'} | {_md(h['last_summary'])} |"
        )

    path = output_dir / "rhythm.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ============================================================
# index.md — Overview & navigation
# ============================================================

def write_index(decomp: StoryDecomposition, output_dir: Path, ctx: dict) -> Path:
    beats = decomp.plot.beats
    total_ch = decomp.total_chapters
    ch_3plus = sum(1 for ch in set(b.chapter for b in beats) if sum(1 for b in beats if b.chapter==ch) >= 3)
    avg_intensity = round(sum(b.intensity for b in beats) / len(beats), 1) if beats else 0
    beat_avg = round(len(beats) / total_ch, 1) if total_ch else 0

    lines = [
        f"# 《{decomp.title}》设定全集",
        "",
        f"**作者**: {decomp.author}  ",
        f"**总章节**: {total_ch}  ",
        f"**总节拍**: {len(beats)}  ",
        "",
        "---",
        "",
        "## 维度统计",
        "",
        "| 维度 | 数量 |",
        "| --- | --- |",
        f"| 叙事节拍 | {len(beats)} |",
        f"| 角色 | {len(decomp.characters)} |",
        f"| 地点 | {len(decomp.world_setting.locations)} |",
        f"| 势力 | {len(ctx['factions'])} |",
        f"| 功法/技能 | {len(ctx['all_techniques'])} |",
        f"| 物品/装备 | {len(ctx['all_items'])} |",
        f"| 角色关系 | {len(decomp.relationships.character_relations)} |",
        f"| 伏笔 | {len(decomp.plot.foreshadowing_tracking)} |",
        f"| 战力变化 | {len(decomp.plot.combat_power_timeline)} |",
        f"| 资产变动 | {len(decomp.plot.asset_timeline)} |",
        "",
        "## 质量指标",
        "",
        f"- 平均每章节拍: **{beat_avg:.1f}**",
        f"- 每章≥3拍: **{ch_3plus}/{total_ch}**" + (f" ({ch_3plus/total_ch:.0%})" if total_ch else ""),
        f"- 平均情绪强度: **{avg_intensity}/5**",
        "",
        "## 设定集导航",
        "",
        "| 文件 | 内容 |",
        "| --- | --- |",
        "| [outline.md](outline.md) | **故事章纲** — 每章几句话概述，一眼看到头 |",
        "| [characters.md](characters.md) | **人物设定集** — 角色列传、性格、技能、装备、实力进阶 |",
        "| [world.md](world.md) | **世界观设定集** — 地理、势力、修炼体系、功法武技、神兵宝器 |",
        "| [relationships.md](relationships.md) | **关系网络** — 初始→中途→最终关系演化 |",
        "| [beats.md](beats.md) | **叙事节拍** — 全书原子单元，LLM可展开为正文 |",
        "| [rhythm.md](rhythm.md) | **节奏日历** — 情绪曲线、爽点分布、高潮分析 |",
        "",
    ]

    path = output_dir / "index.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ============================================================
# Helpers
# ============================================================

def _chapter_emotions(beats):
    ch_data = defaultdict(list)
    for b in beats:
        ch_data[b.chapter].append(b.intensity)
    result = []
    for ch in sorted(ch_data):
        intensities = ch_data[ch]
        result.append({
            "chapter": ch,
            "beat_count": len(intensities),
            "avg_intensity": round(sum(intensities) / len(intensities), 1),
            "max_intensity": max(intensities),
            "min_intensity": min(intensities),
        })
    return result
