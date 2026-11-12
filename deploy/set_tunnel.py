"""Point the Vercel-hosted editor at the laptop's API through a public tunnel, then push (Vercel redeploys on push).

usage: .venv/Scripts/python deploy/set_tunnel.py https://<tunnel-host> [--no-push]

Vercel serves the built editor (web/dist); every API call and media file (/api, /assets, /media, /music, /footage,
/models3d, /renders) is forwarded to the tunnel, so the full app keeps running on the laptop.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREFIXES = ["api", "assets", "media", "music", "footage", "models3d", "renders"]

url = sys.argv[1].rstrip("/") if len(sys.argv) > 1 and sys.argv[1].startswith("https://") else sys.exit(__doc__)
config = {
    "$schema": "https://openapi.vercel.sh/vercel.json",
    "framework": "vite",
    "buildCommand": "npm run build",
    "outputDirectory": "dist",
    "rewrites": [{"source": f"/{p}/:path*", "destination": f"{url}/{p}/:path*"} for p in PREFIXES],
}
(ROOT / "web" / "vercel.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
print("web/vercel.json now forwards to", url)
if "--no-push" not in sys.argv:
    git = lambda *a: subprocess.run(["git", "-C", str(ROOT), *a], check=True)
    git("add", "web/vercel.json")
    git("commit", "-m", f"Vercel: forward API and media to {url}\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>")
    git("push")
