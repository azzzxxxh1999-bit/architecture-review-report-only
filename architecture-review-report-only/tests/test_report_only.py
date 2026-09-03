import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run_script(name, *args, cwd=None):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *args],
        cwd=cwd or ROOT, capture_output=True, text=True, encoding="utf-8",
    )


class FreeEditionTests(unittest.TestCase):
    def make_state(self, project):
        source = Path(project) / "src" / "main.py"
        source.parent.mkdir(parents=True)
        source.write_text("print('ok')\n", encoding="utf-8")
        state_path = Path(project) / ".codemap" / "modules.json"
        state_path.parent.mkdir()
        dimensions = [{"id": item, "status": "good", "score": 80,
                       "summary": "证据充分", "evidence": [], "relatedModules": ["main"]}
                      for item in ("responsibility", "boundary", "contract", "dependency",
                                   "data_logic", "composition_state", "evolution", "safeguards")]
        lenses = [{"id": item, "summary": "证据充分"}
                  for item in ("split", "connect", "change", "protect")]
        state_path.write_text(json.dumps({
            "meta": {"project": "免费版测试", "lang": "zh", "mdPath": ".codemap/codemap.md"},
            "bands": [{"id": "core", "t": "核心"}], "spine": ["main"],
            "architectureDimensions": dimensions, "architectureLenses": lenses,
            "modules": [{"id": "main", "label": "入口", "band": "core",
                          "path": "src/main.py", "paths": ["src/main.py"],
                          "desc": "程序入口", "coupling": "core", "deps": [],
                          "score": 60, "grade": "C", "tags": ["bloat"],
                          "findings": [{"sev": "HIGH", "loc": "src/main.py:1",
                                         "text": "问题证据"}]}]
        }, ensure_ascii=False), encoding="utf-8")
        scanned = run_script("scan.py", "--root", str(project), "--state", str(state_path), "--write")
        self.assertEqual(scanned.returncode, 0, scanned.stderr)
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["modules"][0]["auditedHash"] = state["modules"][0]["contentHash"]
        state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        return state_path

    def test_render_and_dashboard_are_chinese_and_read_only(self):
        with tempfile.TemporaryDirectory() as temp:
            state = self.make_state(temp)
            output = Path(temp) / ".codemap" / "codemap.html"
            report = Path(temp) / ".codemap" / "codemap.md"
            rendered = run_script("render.py", "--state", str(state), "--template",
                                  str(ROOT / "assets" / "template.html"), "--out-html", str(output),
                                  "--out-md", str(report))
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            self.assertTrue(output.is_file())
            dashboard = Path(temp) / ".codemap" / "audit-dashboard.html"
            built = run_script("dashboard.py", "--root", temp, "--state", str(state),
                               "--out-html", str(dashboard), "--out-map", str(output))
            self.assertEqual(built.returncode, 0, built.stderr)
            text = dashboard.read_text(encoding="utf-8")
            self.assertIn("架构分数", text)
            self.assertIn("目前最大的三个问题", text)
            self.assertIn("可能引起的三个问题", text)
            self.assertNotIn("开始规划并修复", text)
            self.assertNotIn("repair_bridge", text)
            self.assertNotIn("project-blueprint-planner", text)

    def test_version_publish_and_verify_keep_report_history(self):
        with tempfile.TemporaryDirectory() as temp:
            state = self.make_state(temp)
            published = run_script("version.py", "publish", "--root", temp, "--mode", "full",
                                   "--expected-baseline", "none", "--allow-unknown",
                                   "--gate", "focused-tests:pass")
            self.assertEqual(published.returncode, 0, published.stderr)
            verify = run_script("version.py", "verify", "--root", temp)
            self.assertEqual(verify.returncode, 0, verify.stderr)
            self.assertTrue(json.loads(verify.stdout)["semanticValid"])


if __name__ == "__main__":
    unittest.main()
