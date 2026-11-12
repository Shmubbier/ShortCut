# YouTube style extraction report

## Implemented

- `POST /api/styles/from-url` creates a background style-extraction job; `GET /api/styles/jobs/<id>` reports its state and result.
- The extractor validates YouTube URLs and the 1–180 second duration bound, reads metadata and auto captions, and falls back to `youtube-transcript-api` captions when yt-dlp supplies none.
- It downloads a low-resolution copy into a temporary directory, samples frames, measures histogram cuts and shot durations, builds a temporary 10-keyframe contact sheet, and estimates three RGB colour clusters. Both the video and contact sheet are removed when processing finishes.
- The AI produces general writing, structure, visual and editing guidance. The measured cut pace and nearest supported palette are applied, and the result is saved in the registry shape with `source` and `measured` fields.
- The Style panel accepts a YouTube URL, polls job progress, reports failures, displays learned characteristics and refreshes the format selector when extraction succeeds. `style_brief()` now includes pace and visual look/palette so extracted styles steer generation.

## Verification

- `cd web && npx.cmd tsc -b` — passed with no TypeScript errors.
- `cd web && node src/video/bench3d/recipe.check.mts` — passed; ended with `recipe.ts OK`.
- `git diff --check` — passed.
- Python import/syntax checks, dependency installation, API requests, and the three real-video trials — **not verified**. The required launcher (`C:/Users/naomi/Documents/vscode shenanigans/ManilaHack/.venv/Scripts/python`) fails before starting: it cannot launch its configured base interpreter at `C:/Users/naomi/AppData/Local/Python/pythoncore-3.11-64/python.exe`. No Python command is available on PATH. Installing the new packages failed for the same reason. Consequently, no extracted measurements or generated-style prompts can honestly be reported, and no API/UI server was started.
- Git commit — **not created**. Git stores this worktree's index in the main checkout's `.git/worktrees/youtube-style/index.lock`; creating it failed with `Permission denied`. The task sandbox permits writes only inside this worktree, so the branch changes remain uncommitted.

## Reproduction once Python is available

```powershell
"C:/Users/naomi/Documents/vscode shenanigans/ManilaHack/.venv/Scripts/python" -m pip install -r requirements.txt
$env:BLOCKCUT_PORT = "8794"
"C:/Users/naomi/Documents/vscode shenanigans/ManilaHack/.venv/Scripts/python" server.py
# In another shell:
$env:BLOCKCUT_API = "http://127.0.0.1:8794"
npm --prefix web run dev -- --port 5184
```

Then create styles from three public videos of different formats through the Style panel, poll each job to completion, use each `id` with `content_styles.style_brief(id)`, and record the resulting `measured` values and style prompt. A logged-in Claude Code CLI or `ANTHROPIC_API_KEY` is required for synthesis.

## Merge notes and dependencies

- Added `yt-dlp` and `youtube-transcript-api` to `requirements.txt`; install them in the shared venv before running the endpoint.
- Runtime style JSON files are written under `styles/` and ignored by Git; no sample styles or downloaded media are committed.
- No other server or UI ports were started or changed.
- yt-dlp is distributed under [The Unlicense](https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE); `youtube-transcript-api` is [MIT licensed](https://github.com/jdepoix/youtube-transcript-api/blob/master/LICENSE). Extraction follows YouTube download/caption availability and will surface provider restrictions as job errors.
