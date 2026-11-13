"""Check that every /demo/... URL inside the demo plans points at a real file."""
import json
import sys
from pathlib import Path


def _urls(node):
    if isinstance(node, str):
        if node.startswith("/demo/"):
            yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _urls(v)
    elif isinstance(node, list):
        for v in node:
            yield from _urls(v)


def missing_files(demo_dir: Path) -> list[str]:
    demo_dir = Path(demo_dir)
    index = json.loads((demo_dir / "index.json").read_text(encoding="utf-8"))
    missing = set()
    for entry in index["plans"]:
        plan = json.loads((demo_dir / entry["file"]).read_text(encoding="utf-8"))
        for url in _urls(plan):
            if not (demo_dir / url[len("/demo/"):]).is_file():
                missing.add(url)
    return sorted(missing)


if __name__ == "__main__":
    out = missing_files(Path(__file__).resolve().parent.parent / "web/public/demo")
    print("\n".join(out) or "ok")
    sys.exit(1 if out else 0)
