#!/usr/bin/env python3
"""Generate the read-only Chinese architecture audit dashboard and module map."""

import argparse
import html
import importlib.util
import json
import os
from pathlib import Path
import webbrowser

SEVERITY_LABELS = {"HIGH": "高风险", "MED": "中风险", "LOW": "低风险"}
TAG_LABELS = {
    "god-component": "上帝组件", "bloat": "臃肿", "stub": "占位桩",
    "fake-output": "伪造输出", "dual-format": "双格式", "duplication": "重复",
    "silent-except": "静默吞错", "fallback": "回退兜底", "legacy": "遗留",
    "glue": "胶水", "any-escape": "类型逃逸", "over-fit": "过度特化",
    "placeholder": "占位", "monkeypatch": "猴补丁",
}


def read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def module_files(module, root):
    root_path = Path(root).resolve()
    found = set()
    patterns = module.get("paths") or []
    if isinstance(patterns, str):
        patterns = [patterns]
    for pattern in patterns:
        try:
            candidates = root_path.glob(str(pattern))
        except (ValueError, OSError):
            candidates = ()
        for candidate in candidates:
            if candidate.is_file():
                found.add(candidate.resolve())
    path = module.get("path")
    if path:
        candidate = (root_path / str(path)).resolve()
        if candidate.is_file():
            found.add(candidate)
    return found


def finding_text_zh(finding):
    explicit = finding.get("textZh")
    if explicit:
        return str(explicit)
    text = str(finding.get("text") or "").strip()
    return text if text else "该模块存在待确认的审计问题。"


def issue_rows(state, root):
    rows = []
    rank = {"HIGH": 0, "MED": 1, "LOW": 2}
    for module in state.get("modules", []):
        score = module.get("score")
        for finding in module.get("findings") or []:
            sev = finding.get("sev", "LOW")
            rows.append({
                "severity": sev,
                "severityLabel": SEVERITY_LABELS.get(sev, "待确认"),
                "label": module.get("label") or module.get("id") or "未命名模块",
                "summary": finding_text_zh(finding),
                "location": finding.get("loc") or module.get("path") or "",
                "score": score if isinstance(score, (int, float)) else 0,
                "moduleId": module.get("id"),
            })
    rows.sort(key=lambda item: (rank.get(item["severity"], 3), item["score"], item["label"]))
    return rows


def possible_rows(state, confirmed):
    """Surface bounded follow-on risks without inventing findings."""
    known = {(row.get("moduleId"), row.get("summary")) for row in confirmed}
    rows = []
    for module in state.get("modules", []):
        tags = [TAG_LABELS.get(tag, tag) for tag in module.get("tags") or [] if tag != "clean"]
        if not tags:
            continue
        summary = "；".join(tags) + " 等结构性问题可能扩大后续改动范围。"
        candidate = {
            "severityLabel": "可能风险",
            "label": module.get("label") or module.get("id") or "未命名模块",
            "summary": summary,
            "location": module.get("path") or "",
            "moduleId": module.get("id"),
        }
        if (candidate["moduleId"], candidate["summary"]) not in known:
            rows.append(candidate)
    return rows[:3]


def dashboard_data(state, root):
    modules = state.get("modules") or []
    scores = [m.get("score") for m in modules if isinstance(m.get("score"), (int, float))]
    confirmed = issue_rows(state, root)
    top = confirmed[:3]
    return {
        "project": state.get("meta", {}).get("project") or Path(root).name,
        "architectureScore": round(sum(scores) / len(scores)) if scores else None,
        "scoredModules": len(scores),
        "moduleCount": len(modules),
        "topIssues": top,
        "possibleIssues": possible_rows(state, top),
        "auditVersion": (state.get("auditVersion") or {}).get("version"),
    }


def build_dashboard(state, root, module_map_url="codemap.html"):
    payload = json.dumps(dashboard_data(state, root), ensure_ascii=False).replace("</", "<\\/")
    title = html.escape(str(state.get("meta", {}).get("project") or Path(root).name))
    return """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>架构审计仪表盘</title><style>
:root{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:#17202a;background:#f5f7f8}
*{box-sizing:border-box}body{margin:0}.shell{max-width:1120px;margin:0 auto;padding:32px 20px 56px}
header{display:flex;align-items:flex-start;justify-content:space-between;gap:20px}h1{font-size:30px;margin:0 0 8px}h2{font-size:21px;margin:32px 0 12px}.muted{color:#68737d;font-size:14px}
.link{display:inline-block;color:#fff;background:#1c6b52;border-radius:6px;padding:10px 14px;text-decoration:none;font-weight:650;white-space:nowrap}
.summary{display:flex;align-items:center;gap:24px;background:#fff;border:1px solid #d9dee3;border-radius:8px;padding:20px;margin-top:24px}.score{font-size:42px;font-weight:750;color:#1c6b52}.score small{font-size:14px;color:#68737d;font-weight:500}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.card{background:#fff;border:1px solid #d9dee3;border-radius:8px;padding:17px;min-height:140px}.card h3{font-size:17px;margin:9px 0}.card p{font-size:14px;line-height:1.55;margin:8px 0}.severity{font-size:12px;font-weight:700;color:#a33d2f}.possible .severity{color:#8c6b18}.location{color:#68737d;font-size:12px;word-break:break-word}.empty{color:#68737d;background:#fff;border:1px solid #d9dee3;border-radius:8px;padding:18px}
footer{margin-top:32px;color:#68737d;font-size:13px}@media(max-width:700px){.shell{padding:22px 13px 40px}header{display:block}.link{margin-top:15px}.grid{grid-template-columns:1fr}.summary{align-items:flex-start;flex-direction:column;gap:8px}.score{font-size:36px}}
</style></head><body><main class="shell"><header><div><h1>架构审计仪表盘</h1><p class="muted" id="project"></p></div><a class="link" href="%s">打开模块图</a></header>
<section class="summary"><div><div class="muted">当前架构分数</div><div class="score" id="score">待评分</div></div><div class="muted" id="coverage"></div></section>
<h2>目前最大的三个问题</h2><section id="top" class="grid"></section>
<h2>可能引起的三个问题</h2><section id="possible" class="grid possible"></section>
<footer id="version"></footer></main><script>
const DATA=%s;const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;", "'":"&#39;"}[c]));
document.querySelector("#project").textContent=DATA.project;document.querySelector("#score").innerHTML=DATA.architectureScore==null?"待评分":DATA.architectureScore+" <small>/ 100</small>";
document.querySelector("#coverage").textContent="已评分模块："+DATA.scoredModules+" / "+DATA.moduleCount;
function render(id,items,empty){const root=document.querySelector(id);root.innerHTML=items.length?items.map(i=>"<article class='card'><span class='severity'>"+esc(i.severityLabel||"关注")+"</span><h3>"+esc(i.label)+"</h3><p>"+esc(i.summary)+"</p>"+(i.location?"<p class='location'>位置："+esc(i.location)+"</p>":"")+"</article>").join(""):"<p class='empty'>"+empty+"</p>"}render("#top",DATA.topIssues,"当前没有已确认的问题。");render("#possible",DATA.possibleIssues,"当前没有足够证据推断后续问题。");document.querySelector("#version").textContent=DATA.auditVersion?"审计版本："+DATA.auditVersion:"当前为工作区审计结果";
</script></body></html>""" % (html.escape(module_map_url, quote=True), payload)


def build_module_map(state, state_path, dashboard_url="audit-dashboard.html"):
    renderer_path = Path(__file__).resolve().parent / "render.py"
    template_path = Path(__file__).resolve().parents[1] / "assets" / "template.html"
    spec = importlib.util.spec_from_file_location("architecture_review_free_renderer", renderer_path)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load local renderer")
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    template = template_path.read_text(encoding="utf-8")
    standard = renderer.load_standard(state_path)
    page = renderer.render_html(state, template, standard)
    return_link = html.escape(dashboard_url, quote=True)
    return page.replace(
        "</body>",
        "<a class=\"free-dashboard-return\" href=\"{}\">返回仪表盘</a>"
        "<style>.free-dashboard-return{{position:fixed;right:18px;bottom:18px;z-index:60;"
        "padding:9px 12px;border-radius:6px;background:#1c6b52;color:#fff;text-decoration:none;"
        "font:600 13px system-ui,-apple-system,Segoe UI,sans-serif}}</style></body>".format(return_link),
        1,
    )


def main():
    parser = argparse.ArgumentParser(description="build/open the read-only architecture dashboard")
    parser.add_argument("--state", required=True)
    parser.add_argument("--root")
    parser.add_argument("--out-html", required=True)
    parser.add_argument("--out-map")
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    root = os.path.abspath(args.root or os.path.dirname(os.path.dirname(args.state)))
    state = read_json(args.state)
    output = os.path.abspath(args.out_html)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    map_output = os.path.abspath(args.out_map or os.path.join(os.path.dirname(output), "codemap.html"))
    with open(output, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(build_dashboard(state, root, os.path.basename(map_output)))
    with open(map_output, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(build_module_map(state, args.state, os.path.basename(output)))
    if args.open:
        webbrowser.open(Path(output).as_uri())
    print("dashboard written -> {}".format(output))


if __name__ == "__main__":
    main()
