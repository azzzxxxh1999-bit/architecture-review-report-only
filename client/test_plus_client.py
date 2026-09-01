import json
import tempfile
import unittest
from pathlib import Path

from plus_client import summary_from_state


class PlusClientTests(unittest.TestCase):
    def test_summary_allow_list_excludes_paths_and_source(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root) / "modules.json"
            state.write_text(json.dumps({
                "meta": {"architectureScore": 71},
                "modules": [{
                    "id": "combat", "path": "src/combat.gd", "score": 60, "grade": "D",
                    "loc": 120, "findings": [{"sev": "HIGH", "text": "private source"}],
                    "tags": ["god-component"], "source": "must-not-send",
                }],
            }), encoding="utf-8")
            summary = summary_from_state(state)
            self.assertEqual(summary["modules"][0]["codeLines"], 120)
            self.assertNotIn("path", summary["modules"][0])
            self.assertNotIn("source", json.dumps(summary))

    def test_summary_has_stable_project_hash(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root) / "modules.json"
            state.write_text(json.dumps({"modules": [{"id": "a", "score": 80, "grade": "B"}]}), encoding="utf-8")
            self.assertEqual(summary_from_state(state)["projectHash"], summary_from_state(state)["projectHash"])


if __name__ == "__main__":
    unittest.main()
