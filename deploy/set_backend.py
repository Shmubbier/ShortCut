"""Point the Vercel-hosted editor at the live backend (Railway), then push (Vercel redeploys on push).

usage: .venv/Scripts/python deploy/set_backend.py https://<railway-host> [--no-push]

Vercel serves the built editor (web/dist) and the bundled /demo/ (never forwarded). API, media and the /admin page are
forwarded to the backend.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREFIXES = ["api", "assets", "media", "music", "footage", "models3d", "renders"]


def build_config(url):
    if not url.startswith("https://"):
        raise ValueError("backend URL must start with https://")
    url = url.rstrip("/")
    rewrites = [{"source": f"/{p}/:path*", "destination": f"{url}/{p}/:path*"} for p in PREFIXES]
    rewrites += [{"source": "/admin", "destination": f"{url}/admin"},
                 {"source": "/admin/:path*", "destination": f"{url}/admin/:path*"}]
    return {"$schema": "https://openapi.vercel.sh/vercel.json", "framework": "vite", "buildCommand": "npm run build",
            "outputDirectory": "dist", "rewrites": rewrites}


if __name__ == "__main__":
    try:
        config = build_config(sys.argv[1] if len(sys.argv) > 1 else "")
    except ValueError:
        sys.exit(__doc__)
    url = sys.argv[1].rstrip("/")
    (ROOT / "web" / "vercel.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print("web/vercel.json now forwards to", url)
    if "--no-push" not in sys.argv:
        git = lambda *a: subprocess.run(["git", "-C", str(ROOT), *a], check=True)
        git("add", "web/vercel.json")
        git("commit", "-m", f"Vercel: forward API, media and /admin to {url}\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>")
        git("push")
