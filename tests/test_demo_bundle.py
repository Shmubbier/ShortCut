import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy"))
from check_demo import missing_files  # noqa: E402

DEMO = ROOT / "web/public/demo"


def _plans():
    index = json.loads((DEMO / "index.json").read_text(encoding="utf-8"))
    return index, [(p["file"], json.loads((DEMO / p["file"]).read_text(encoding="utf-8"))) for p in index["plans"]]


class DemoBundle(unittest.TestCase):
    def test_every_demo_url_exists(self):
        self.assertEqual(missing_files(DEMO), [])

    def test_index_lists_three_plans(self):
        index, _ = _plans()
        self.assertEqual([p["file"] for p in index["plans"]], ["ube.json", "jeepney.json", "tower_defense.json"])
        for p in index["plans"]:
            self.assertTrue(p["keywords"])

    def test_export_urls_exist(self):
        _, plans = _plans()
        for name, plan in plans:
            url = plan.get("exportUrl")
            self.assertTrue(url, f"{name} has no exportUrl")
            self.assertTrue(url.startswith("/demo/"))
            self.assertTrue((DEMO / url[len("/demo/"):]).is_file(), url)


if __name__ == "__main__":
    unittest.main()
