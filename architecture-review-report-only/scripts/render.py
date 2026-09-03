#!/usr/bin/env python3
"""render.py — regenerate codemap.html + codemap.md from modules.json.

modules.json is the single source of truth. The HTML and MD are pure projections
of it and must never be hand-edited. Run scan.py --write before rendering so LoC /
content hashes are current.

Usage:
  python render.py --state modules.json \
      --template assets/template.html \
      --out-html codemap.html --out-md codemap.md

Stdlib only.
"""
import argparse, json, os


DIMENSION_DEFS = [
    {"id": "responsibility", "lens": "split", "order": 1,
     "label": "Module responsibilities", "labelZh": "模块职责",
     "question": "Does each module own one coherent responsibility?",
     "questionZh": "每个模块是不是只管自己的事？"},
    {"id": "boundary", "lens": "split", "order": 2,
     "label": "Module boundaries", "labelZh": "模块边界",
     "question": "Do UI, combat, persistence, and data stay inside their boundaries?",
     "questionZh": "UI、战斗、存档、数据有没有互相乱伸手？"},
    {"id": "contract", "lens": "connect", "order": 3,
     "label": "Contracts and interfaces", "labelZh": "Contract / 接口",
     "question": "Do modules communicate through stable interfaces, events, and data structures?",
     "questionZh": "模块是不是通过固定接口、事件和数据结构沟通？"},
    {"id": "dependency", "lens": "connect", "order": 4,
     "label": "Dependency direction", "labelZh": "依赖方向",
     "question": "Are there cycles, reversed layers, or wide change blast radii?",
     "questionZh": "有没有循环依赖、底层反向依赖上层、改一处牵一大片？"},
    {"id": "data_logic", "lens": "change", "order": 5,
     "label": "Data and logic separation", "labelZh": "数据与逻辑分离",
     "question": "Can content be added as data without editing many code paths?",
     "questionZh": "新增武器、怪物、商品，是加数据就行吗？"},
    {"id": "composition_state", "lens": "change", "order": 6,
     "label": "State and composition", "labelZh": "状态与组合",
     "question": "Are complex behaviors composed with state machines and components?",
     "questionZh": "复杂行为有没有状态机和组件，而不是无限 if/else 与继承？"},
    {"id": "evolution", "lens": "change", "order": 7,
     "label": "Long-term evolution", "labelZh": "长期演进",
     "question": "Can old saves and data upgrade through stable IDs and migrations?",
     "questionZh": "旧存档、旧数据和稳定 ID 能不能升级？"},
    {"id": "safeguards", "lens": "protect", "order": 8,
     "label": "Engineering safeguards", "labelZh": "工程保障",
     "question": "Can regressions be detected, traced, and recovered quickly?",
     "questionZh": "改坏后能不能及时发现、追踪并恢复？"},
]

LENS_DEFS = [
    {"id": "split", "label": "Split", "labelZh": "分", "order": 1,
     "question": "Who owns each responsibility, and where are the boundaries?",
     "questionZh": "每个模块管什么，哪些事情不归它管？",
     "dimensionIds": ["responsibility", "boundary"]},
    {"id": "connect", "label": "Connect", "labelZh": "连", "order": 2,
     "question": "How do modules communicate, and who depends on whom?",
     "questionZh": "模块怎么沟通，谁依赖谁？",
     "dimensionIds": ["contract", "dependency"]},
    {"id": "change", "label": "Change", "labelZh": "变", "order": 3,
     "question": "Can the system add content, combine behavior, and upgrade old data safely?",
     "questionZh": "加内容、改行为、升旧数据，会不会牵一大片？",
     "dimensionIds": ["data_logic", "composition_state", "evolution"]},
    {"id": "protect", "label": "Protect", "labelZh": "保", "order": 4,
     "question": "Can a bad change be found, traced, and recovered?",
     "questionZh": "改坏了能否发现、追踪并恢复？",
     "dimensionIds": ["safeguards"]},
]

VALID_STATUSES = {"good", "warning", "risk", "unknown"}
STATUS_RANK = {"good": 0, "unknown": 1, "warning": 2, "risk": 3}


def normalize_architecture(state):
    """Return a validated four-lens/eight-dimension projection.

    Old state files remain renderable: absent structured audit data becomes explicit
    `unknown`, never an invented pass. When structured data is present, warning/risk
    results must carry evidence and every referenced module id must exist.
    """
    modules = {m.get("id") for m in state.get("modules", []) if m.get("id")}
    raw_dims = state.get("architectureDimensions") or []
    if not isinstance(raw_dims, list):
        raise ValueError("architectureDimensions must be an array")
    by_dim = {}
    allowed_dims = {d["id"] for d in DIMENSION_DEFS}
    for item in raw_dims:
        if not isinstance(item, dict) or item.get("id") not in allowed_dims:
            raise ValueError("architectureDimensions contains an unknown or malformed id")
        if item["id"] in by_dim:
            raise ValueError(f"duplicate architecture dimension: {item['id']}")
        by_dim[item["id"]] = item

    dims = []
    for definition in DIMENSION_DEFS:
        src = by_dim.get(definition["id"], {})
        status = src.get("status", "unknown")
        if status not in VALID_STATUSES:
            raise ValueError(f"invalid architecture status for {definition['id']}: {status}")
        score = src.get("score")
        if score is not None and (isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 100):
            raise ValueError(f"invalid architecture score for {definition['id']}")
        evidence = src.get("evidence") or []
        if not isinstance(evidence, list):
            raise ValueError(f"evidence must be an array for {definition['id']}")
        normalized_evidence = []
        for ev in evidence:
            if isinstance(ev, str):
                ev = {"type": "note", "description": ev}
            if not isinstance(ev, dict) or not ev.get("description"):
                raise ValueError(f"malformed evidence for {definition['id']}")
            normalized_evidence.append({k: ev.get(k) for k in (
                "id", "type", "description", "file", "symbol", "line", "moduleId") if ev.get(k) is not None})
        if status in {"warning", "risk"} and not normalized_evidence:
            raise ValueError(f"{status} architecture dimension requires evidence: {definition['id']}")
        related = src.get("relatedModules") or []
        if not isinstance(related, list) or any(mid not in modules for mid in related):
            raise ValueError(f"architecture dimension references an unknown module: {definition['id']}")
        dim = dict(definition)
        dim.update({
            "status": status,
            "score": score,
            "summary": src.get("summary") or ("Evidence has not been structured yet." if state.get("meta", {}).get("lang") != "zh" else "尚未完成结构化审计。"),
            "evidence": normalized_evidence,
            "relatedModules": related,
            "recommendation": src.get("recommendation") or "",
            "sourceRevision": src.get("sourceRevision") or state.get("meta", {}).get("rev"),
            "verifiedAt": src.get("verifiedAt"),
            "inheritedFrom": src.get("inheritedFrom"),
        })
        dims.append(dim)

    raw_lenses = state.get("architectureLenses") or []
    if not isinstance(raw_lenses, list):
        raise ValueError("architectureLenses must be an array")
    by_lens = {}
    allowed_lenses = {x["id"] for x in LENS_DEFS}
    for item in raw_lenses:
        if not isinstance(item, dict) or item.get("id") not in allowed_lenses:
            raise ValueError("architectureLenses contains an unknown or malformed id")
        if item["id"] in by_lens:
            raise ValueError(f"duplicate architecture lens: {item['id']}")
        by_lens[item["id"]] = item

    dim_by_id = {d["id"]: d for d in dims}
    lenses = []
    for definition in LENS_DEFS:
        src = by_lens.get(definition["id"], {})
        owned = [dim_by_id[i] for i in definition["dimensionIds"]]
        status = max((d["status"] for d in owned), key=lambda x: STATUS_RANK[x])
        scores = [d["score"] for d in owned]
        score = round(sum(scores) / len(scores)) if scores and all(s is not None for s in scores) else None
        issues = [
            {"dimensionId": d["id"], "label": d["label"], "labelZh": d["labelZh"],
             "status": d["status"], "summary": d["summary"],
             "recommendation": d["recommendation"], "relatedModules": d["relatedModules"]}
            for d in sorted(owned, key=lambda d: (-STATUS_RANK[d["status"]], d["order"]))
            if d["status"] in {"risk", "warning", "unknown"}
        ][:3]
        lens = dict(definition)
        lens.update({
            "status": status,
            "score": score,
            "summary": src.get("summary") or next((d["summary"] for d in owned if d["status"] == status), owned[0]["summary"]),
            "issues": issues,
        })
        lenses.append(lens)

    version = state.get("auditVersion") or {
        "version": None,
        "mode": "working",
        "baseline": None,
        "trigger": "structured-view",
        "scope": [],
        "createdAt": None,
    }
    delta = state.get("auditDelta")
    if delta is not None and not isinstance(delta, dict):
        raise ValueError("auditDelta must be an object or null")
    return lenses, dims, version, delta


def health_color(s):
    if s is None: return "#6b7280"
    if s < 50:  return "#e0524b"
    if s < 65:  return "#e0804a"
    if s < 75:  return "#d9a441"
    if s < 85:  return "#8f969d"
    return "#5d6b63"


def band_order(state):
    return [b["id"] for b in state.get("bands", []) if not b.get("wire")]


def load_standard(state_path, explicit=None):
    """Effective audit standard: explicit path → project override next to the state
    file (`<state dir>/standard.json`) → the skill's default `reference/standard.json`."""
    project = os.path.join(os.path.dirname(os.path.abspath(state_path)), "standard.json")
    candidate = explicit or (project if os.path.isfile(project) else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "reference", "standard.json"))
    try:
        with open(candidate, encoding="utf-8") as handle:
            return json.load(handle)
    except (ValueError, OSError) as exc:
        raise ValueError("cannot load effective standard {}: {}".format(candidate, exc)) from exc


def render_html(state, template, standard=None):
    lenses, dimensions, version, delta = normalize_architecture(state)
    data = {
        "meta": state.get("meta", {}),
        "bands": state.get("bands", []),
        "spine": state.get("spine", []),
        "reportThemes": state.get("reportThemes", []),
        "architectureLenses": lenses,
        "architectureDimensions": dimensions,
        "auditVersion": version,
        "auditDelta": delta,
        "standard": standard,
        "modules": [
            {k: m.get(k) for k in (
                "id", "label", "band", "path", "desc", "coupling", "deps",
                "loc", "score", "grade", "tags", "findings")}
            for m in state.get("modules", [])
        ],
    }
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return template.replace("__ARCH_DATA__", blob)


def render_md(state):
    meta = state.get("meta", {})
    lenses, dimensions, version, delta = normalize_architecture(state)
    mods = [m for m in state.get("modules", []) if m.get("score") is not None]
    bands = {b["id"]: b for b in state.get("bands", [])}
    out = []
    proj = meta.get("project", "Project")
    out.append("<!--")
    out.append(f"  This file:        {meta.get('mdPath', 'codemap.md')}   (written report)")
    out.append(f"  Interactive map:  {meta.get('htmlPath', 'codemap.html')}")
    out.append("-->\n")
    out.append(f"# {proj} — Functional Module Quality Audit\n")
    out.append(f"> **模块图:** [`{meta.get('htmlPath','codemap.html')}`]"
               f"({os.path.basename(meta.get('htmlPath','codemap.html'))}) — "
               "每个模块的分数、问题、代码行数和依赖关系；本文件是文字报告。\n")
    gen = meta.get("generatedAt", "")
    loc_line = meta.get("locLine") or (
        f"{meta.get('tracked_loc','?')} 代码行，涉及 {meta.get('tracked_files','?')} 个文件")
    out.append(f"**Generated:** {gen} · **Modules:** {len(mods)} · **Size:** {loc_line}\n")

    lang_zh = meta.get("lang") == "zh"
    out.append("## 分 · 连 · 变 · 保\n" if lang_zh else "## Split · Connect · Change · Protect\n")
    out.append("| 入口 | 状态 | 分数 | 结论 |" if lang_zh else "| Lens | Status | Score | Summary |")
    out.append("|---|:--:|--:|---|")
    for lens in lenses:
        label = lens["labelZh"] if lang_zh else lens["label"]
        score = lens["score"] if lens["score"] is not None else "—"
        out.append(f"| {label} | {lens['status']} | {score} | {lens['summary']} |")
    out.append("")
    for lens in lenses:
        label = lens["labelZh"] if lang_zh else lens["label"]
        out.append(f"### {label}\n")
        for dim in [d for d in dimensions if d["lens"] == lens["id"]]:
            dlabel = dim["labelZh"] if lang_zh else dim["label"]
            out.append(f"- **{dlabel} · {dim['status']}** — {dim['summary']}")
            for ev in dim["evidence"][:3]:
                where = ev.get("file") or ev.get("moduleId") or ev.get("type", "evidence")
                out.append(f"  - `{where}` — {ev['description']}")
        out.append("")
    ver = version.get("version") or ("未留版" if lang_zh else "not retained")
    out.append(f"**{'审计版本' if lang_zh else 'Audit version'}:** {ver}\n")

    # per-layer averages
    out.append("## Health by layer\n")
    out.append("| Layer | Modules | Avg score |")
    out.append("|---|--:|--:|")
    for b in state.get("bands", []):
        if b.get("wire"):
            continue
        grp = [m for m in mods if m["band"] == b["id"]]
        if not grp:
            continue
        avg = round(sum(m["score"] for m in grp) / len(grp))
        out.append(f"| {b.get('t', b['id'])} | {len(grp)} | {avg} |")
    out.append("")

    # per-module LoC + score, grouped by band, sorted by loc desc
    out.append("## 各模块代码行数与分数\n")
    out.append("_代码行数按模块代表文件或目录统计；目录模块可能重叠，不能直接相加。_\n")
    for b in state.get("bands", []):
        if b.get("wire"):
            continue
        grp = sorted([m for m in mods if m["band"] == b["id"]],
                     key=lambda m: -(m.get("loc") or 0))
        if not grp:
            continue
        out.append(f"### {b.get('t', b['id'])}\n")
        out.append("| 模块 | 代码行数 | 分数 | 标签 |")
        out.append("|---|--:|:--|:--|")
        for m in grp:
            tags = ", ".join(t for t in (m.get("tags") or []) if t != "clean") or "—"
            loc = f"{m.get('loc',0):,}"
            out.append(f"| {m['label']} | {loc} | {m['score']} {m['grade']} | {tags} |")
        out.append("")

    # worst offenders
    out.append("## Worst offenders\n")
    worst = sorted(mods, key=lambda m: m["score"])[:10]
    for m in worst:
        fnd = m.get("findings") or []
        top = next((f for f in fnd if f["sev"] == "HIGH"), fnd[0] if fnd else None)
        ev = f" — {top['loc']}: {top['text']}" if top else ""
        out.append(f"- **{m['label']} ({m['score']}/{m['grade']})**{ev}")
    out.append("")

    # all findings, by severity
    out.append("## All findings\n")
    for sev in ("HIGH", "MED", "LOW"):
        rows = [(m, f) for m in mods for f in (m.get("findings") or []) if f["sev"] == sev]
        if not rows:
            continue
        out.append(f"### {sev} ({len(rows)})\n")
        for m, f in rows:
            out.append(f"- **{m['label']}** · `{f['loc']}` — {f['text']}")
        out.append("")

    # cross-cutting themes
    themes = state.get("reportThemes", [])
    if themes:
        out.append("## Cross-cutting themes\n")
        for h, body in themes:
            out.append(f"- **{h}.** {body}")
        out.append("")

    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--template")
    ap.add_argument("--out-html")
    ap.add_argument("--out-md")
    ap.add_argument("--standard", help="path to a custom standard.json (else project override → skill default)")
    args = ap.parse_args()

    state = json.load(open(args.state, encoding="utf-8"))
    standard = load_standard(args.state, args.standard)
    if not args.out_html and not args.out_md:
        ap.error("at least one of --out-html or --out-md is required")
    if args.out_html:
        if not args.template:
            ap.error("--template is required with --out-html")
        template = open(args.template, encoding="utf-8").read()
        os.makedirs(os.path.dirname(os.path.abspath(args.out_html)), exist_ok=True)
        open(args.out_html, "w", encoding="utf-8").write(render_html(state, template, standard))
    if args.out_md:
        os.makedirs(os.path.dirname(os.path.abspath(args.out_md)), exist_ok=True)
        open(args.out_md, "w", encoding="utf-8").write(render_md(state))
    n = len(state.get("modules", []))
    scored = sum(1 for m in state.get("modules", []) if m.get("score") is not None)
    outputs = [path for path in (args.out_html, args.out_md) if path]
    print(f"rendered {n} modules ({scored} scored) -> {' + '.join(outputs)}")


if __name__ == "__main__":
    main()
