"""Convert decomposition JSON to structured Markdown for readability and search."""

from __future__ import annotations

import json
from pathlib import Path


def _s(v, default=""):
    return str(v) if v else default


def _l(v):
    return v if isinstance(v, list) else []


def _i(v, d=0):
    try:
        return int(v)
    except Exception:
        return d


def decomposition_to_markdown(json_path: str | Path, output_path: str | Path | None = None):
    """
    Convert a decomposition JSON file to a well-structured Markdown file.

    Args:
        json_path: Path to decomposition.json
        output_path: Output path for .md file (auto-derived if None)
    """
    json_path = Path(json_path)
    if output_path is None:
        output_path = json_path.with_suffix(".md")
    else:
        output_path = Path(output_path)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    md: list[str] = []

    def w(s=""):
        md.append(s)

    def h1(s):
        w(f"# {s}")
        w()

    def h2(s):
        w(f"## {s}")
        w()

    def h3(s):
        w(f"### {s}")
        w()

    def table(headers, rows):
        w("| " + " | ".join(headers) + " |")
        w("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in rows:
            w("| " + " | ".join(str(c).replace("|", "\\|").replace("\n", " ") for c in row) + " |")
        w()

    # ====== HEADER ======
    h1(f"《{data.get('title', '未命名')}》拆解文档")
    w(f"**作者**: {data.get('author', '未知')}  ")
    w(f"**总章节数**: {data.get('total_chapters', 0)}  ")
    w()
    w("---")
    w()

    # ====== OVERVIEW ======
    chars = _l(data.get("characters", []))
    events = _l(data.get("plot", {}).get("chapter_events", []))
    locations = _l(data.get("world_setting", {}).get("locations", []))
    relations = _l(data.get("relationships", {}).get("character_relations", []))
    settings = _l(data.get("world_setting", {}).get("power_system", {}).get("rule_discovery_timeline", []))
    foreshadowing = _l(data.get("plot", {}).get("foreshadowing_tracking", []))
    combat_timeline = _l(data.get("plot", {}).get("combat_power_timeline", []))
    asset_timeline = _l(data.get("plot", {}).get("asset_timeline", []))
    cheat_stages = _l(data.get("world_setting", {}).get("cheat_system", {}).get("evolution_stages", []))

    h2("拆解概览")
    table(
        ["维度", "数量"],
        [
            ["角色", len(chars)],
            ["章节事件", len(events)],
            ["地点", len(locations)],
            ["关系演化", len(relations)],
            ["设定揭示", len(settings)],
            ["伏笔追踪", len(foreshadowing)],
            ["战力变化", len(combat_timeline)],
            ["资产变动", len(asset_timeline)],
            ["金手指演化", len(cheat_stages)],
        ],
    )

    # ====== 1. CHARACTERS ======
    h1("一、角色谱")

    chars_sorted = sorted(chars, key=lambda c: len(_l(c.get("state_timeline", []))), reverse=True)

    h2("角色索引")
    char_rows = []
    for c in chars_sorted[:80]:
        st_count = len(_l(c.get("state_timeline", [])))
        ab_count = len(_l(c.get("abilities_timeline", [])))
        pers = _s(c.get("static_traits", {}).get("personality", ""))[:60]
        intro = c.get("introduction_chapter", "?")
        char_rows.append([c["name"], c.get("role", ""), str(intro), f"{st_count}章", f"{ab_count}次", pers])
    table(["角色名", "定位", "登场章节", "状态追踪", "能力成长", "性格特征"], char_rows)

    h2("主要角色详情")
    for c in chars_sorted[:30]:
        h3(f"{c['name']} ({c.get('role', '?')})")
        st = c.get("static_traits", {}) or {}
        identity = c.get("identity", {}) or {}
        w(f"- **性格**: {_s(st.get('personality', '未知'))}")
        w(f"- **外貌**: {_s(st.get('appearance', '未知'))}")
        if identity.get("background"):
            w(f"- **背景**: {identity['background']}")
        w(f"- **登场章节**: 第 {c.get('introduction_chapter', '?')} 章")
        aliases = _l(c.get("aliases", []))
        w(f"- **别名**: {', '.join(aliases) if aliases else '无'}")

        ab_tl = _l(c.get("abilities_timeline", []))
        if ab_tl:
            w(f"- **能力成长线** ({len(ab_tl)} 次):")
            for ab in ab_tl[:15]:
                abs_list = ab.get("abilities", [])
                abs_str = "、".join(str(a) for a in abs_list) if isinstance(abs_list, list) else str(abs_list)
                w(f"  - 第 {ab.get('chapter', '?')} 章: {abs_str}")
            if len(ab_tl) > 15:
                w(f"  - ... 共 {len(ab_tl)} 次")

        cp_tl = _l(c.get("combat_power_timeline", []))
        if cp_tl:
            w(f"- **战力进阶线** ({len(cp_tl)} 次变化):")
            for cp in cp_tl[:20]:
                w(f"  - 第 {cp.get('chapter', '?')} 章: {cp.get('level', '?')} {cp.get('sub_level', '')} ({cp.get('change', '')})")
            if len(cp_tl) > 20:
                w(f"  - ... 共 {len(cp_tl)} 次战力变化")

        state_tl = _l(c.get("state_timeline", []))
        if state_tl:
            w(f"- **状态追踪** (共 {len(state_tl)} 章):")
            w()
            w("| 章节 | 情绪 | 目标 | 位置 | 关键行为 |")
            w("| --- | --- | --- | --- | --- |")
            for s in state_tl[:10]:
                actions = "、".join(_l(s.get("key_actions", []))[:3])
                if len(_l(s.get("key_actions", []))) > 3:
                    actions += "..."
                w(f"| {s.get('chapter','?')} | {_s(s.get('emotional',''))[:25]} | {_s(s.get('goal',''))[:35]} | {_s(s.get('location',''))[:20]} | {actions[:80]} |")
            if len(state_tl) > 10:
                w(f"| ... | ... | ... | ... | 共 {len(state_tl)} 章状态记录 |")

        arc = c.get("arc", {}) or {}
        if arc.get("growth_trajectory") or arc.get("core_conflict"):
            w(f"- **角色弧光**: {_s(arc.get('growth_trajectory', ''))}")
            w(f"- **核心矛盾**: {_s(arc.get('core_conflict', ''))}")
        w()
        w("---")
        w()

    # ====== 2. PLOT ======
    h1("二、情节谱")

    h2("章节事件（前30章预览）")
    table(
        ["章节", "地点", "参与角色", "事件摘要", "情绪"],
        [
            [
                ev.get("chapter", ""),
                _s(ev.get("location", ""))[:15],
                ", ".join(_l(ev.get("characters", []))[:3]),
                _s(ev.get("summary", ""))[:80],
                _s(ev.get("tone", "")),
            ]
            for ev in events[:30]
        ],
    )

    h2("全部章节事件")
    for ev in events:
        ch = ev.get("chapter", "?")
        chars_str = "、".join(_l(ev.get("characters", []))[:5])
        w(f"### 第 {ch} 章: {_s(ev.get('title', ''))}")
        w(f"- **地点**: {_s(ev.get('location', ''))}")
        w(f"- **参与角色**: {chars_str}")
        w(f"- **摘要**: {_s(ev.get('summary', ''))}")
        w(f"- **因果链**: {_s(ev.get('causal_chain', ''))}")
        w(f"- **原因**: {_s(ev.get('cause', ''))}")
        w(f"- **后果**: {_s(ev.get('consequence', ''))}")
        w(f"- **情绪基调**: {_s(ev.get('tone', ''))}")
        moments = _l(ev.get("key_moments", []))
        if moments:
            w("- **关键瞬间**:")
            for m in moments[:5]:
                w(f"  - {m}")
        w()

    # ====== FORESHADOWING ======
    if foreshadowing:
        h2("伏笔追踪总表")
        unresolved = [f for f in foreshadowing if not f.get("resolved_chapter") or f.get("resolved_chapter") == 0]
        resolved = [f for f in foreshadowing if f.get("resolved_chapter") and f.get("resolved_chapter") != 0]
        w(f"- 未回收: **{len(unresolved)}** 条 | 已回收: **{len(resolved)}** 条")
        w()
        table(
            ["编号", "描述", "埋坑章节", "涉及人物", "回收章节", "回收方式", "圆满度"],
            [
                [
                    f.get("id", ""),
                    _s(f.get("description", ""))[:60],
                    str(f.get("planted_chapter", "?")),
                    ", ".join(_l(f.get("involved_characters", []))[:3]),
                    str(f.get("resolved_chapter", "未回收")),
                    _s(f.get("resolution", ""))[:50],
                    _s(f.get("resolution_quality", "")),
                ]
                for f in foreshadowing[:100]
            ],
        )

    # ====== COMBAT POWER ======
    if combat_timeline:
        h2("主角战力追踪总表")
        table(
            ["章节", "等级", "小境界", "变化描述"],
            [
                [str(cp.get("chapter", "?")), cp.get("level", ""), cp.get("sub_level", ""),
                 _s(cp.get("change_description", ""))[:70]]
                for cp in combat_timeline[:100]
            ],
        )

    # ====== ASSETS ======
    if asset_timeline:
        h2("核心资产变动总表")
        table(
            ["章节", "操作", "物品/资源", "数量", "来源/去向"],
            [
                [str(a.get("chapter", "?")), a.get("operation", ""),
                 a.get("item_name", ""), a.get("quantity", ""),
                 _s(a.get("source_or_target", ""))[:50]]
                for a in asset_timeline[:100]
            ],
        )

    # ====== 3. WORLD SETTING ======
    h1("三、世界观设定")

    # Cheat system evolution
    if cheat_stages:
        h2("金手指/外挂系统演化")
        cheat_name = _s(data.get("world_setting", {}).get("cheat_system", {}).get("name", ""))
        w(f"**系统名称**: {cheat_name or '未命名'}")
        w()
        table(
            ["阶段", "章节", "形态描述", "新增功能", "限制/缺陷"],
            [
                [
                    cs.get("stage", ""),
                    str(cs.get("chapter", "?")),
                    _s(cs.get("form_description", ""))[:60],
                    "、".join(_l(cs.get("new_functions", []))[:3]),
                    _s(cs.get("limitations", ""))[:50],
                ]
                for cs in cheat_stages[:30]
            ],
        )

    # Factions
    h2("势力/组织")
    factions = _l(data.get("world_setting", {}).get("factions", []))
    if factions:
        table(
            ["势力名", "类型", "描述", "核心成员"],
            [
                [f.get("name", ""), f.get("type", ""),
                 _s(f.get("description", ""))[:60],
                 "、".join(_l(f.get("key_members", []))[:5])]
                for f in factions[:50]
            ],
        )
    else:
        w("*暂无势力数据*")
        w()

    h2("地点（地图）")
    loc_rows = []
    for loc in locations:
        apps = _l(loc.get("appearances", []))
        loc_rows.append([
            loc.get("name", ""),
            _s(loc.get("type", "")),
            _s(loc.get("description", ""))[:80],
            _s(loc.get("atmosphere", "")),
            f"第{loc.get('first_chapter','?')}章",
            f"{len(apps)}次",
        ])
    loc_rows.sort(key=lambda r: int(r[5].replace("次", "")), reverse=True)
    table(["地点名", "类型", "描述", "氛围", "首现", "出现次数"], loc_rows[:50])
    w(f"*共 {len(loc_rows)} 个地点*")
    w()

    h2("设定揭示")
    w("| 章节 | 类别 | 内容 | 揭示方式 |")
    w("| --- | --- | --- | --- |")
    for sr in settings[:100]:
        w(f"| {sr.get('chapter','?')} | {_s(sr.get('category',''))} | {_s(sr.get('content', sr.get('rule','')))[:80]} | {_s(sr.get('revealed_through',''))[:25]} |")
    w()
    w(f"*共 {len(settings)} 条设定揭示*")
    w()

    # ====== 4. RELATIONSHIPS ======
    h1("四、关系网")

    rels_sorted = sorted(relations, key=lambda r: len(_l(r.get("evolution", []))), reverse=True)

    h2("角色关系")
    table(
        ["角色A", "角色B", "关系类型", "初建章节", "演化次数"],
        [
            [r.get("from", ""), r.get("to", ""), _s(r.get("type", "")),
             str(r.get("start_chapter", "")), str(len(_l(r.get("evolution", []))))]
            for r in rels_sorted[:50]
        ],
    )
    w(f"*共 {len(relations)} 对角色关系*")
    w()

    h2("主要关系演化详情")
    for r in rels_sorted[:20]:
        evo = _l(r.get("evolution", []))
        if not evo:
            continue
        w(f"### {r.get('from', '')} ↔ {r.get('to', '')}")
        w(f"- **关系类型**: {_s(r.get('type', ''))}")
        w(f"- **时间跨度**: 第 {r.get('start_chapter', '?')} 章 ~ 第 {r.get('end_chapter', '终')} 章")
        w("- **演化过程**:")
        for e in evo[:15]:
            w(f"  - 第 {e.get('chapter', '?')} 章: {_s(e.get('status', ''))}")
        if len(evo) > 15:
            w(f"  - ... 共 {len(evo)} 次关系变化")
        w()

    # ====== 5. STYLE ======
    h1("五、叙事风格")
    style = data.get("style", {}) or {}
    w(f"- **叙事视角**: {_s(style.get('narrative_pov', '未分析'))}")
    w(f"- **平均章节长度**: {_s(style.get('average_chapter_length', '未分析'))}")
    w(f"- **高潮间距**: {_s(style.get('climax_spacing', '未分析'))}")
    w(f"- **对话风格**: {_s(style.get('dialogue_style', '未分析'))}")
    w(f"- **描写密度**: {_s(style.get('description_density', '未分析'))}")
    patterns = _l(style.get("pacing_patterns", []))
    if patterns:
        w(f"- **节奏模式**: {', '.join(patterns)}")
    hooks = _l(style.get("hook_patterns", []))
    if hooks:
        w(f"- **钩子模式**: {', '.join(hooks)}")

    # Write
    md_text = "\n".join(md)
    output_path.write_text(md_text, encoding="utf-8")
    return output_path
