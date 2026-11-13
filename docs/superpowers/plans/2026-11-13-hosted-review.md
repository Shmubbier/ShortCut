# Hosted Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An always-on ShortCut demo on Vercel, plus one week of live generation for panelists (shared reviewer code + name) served by a Railway container, with a private usage log.

**Architecture:** Vercel serves the built editor and a bundled demo (`web/public/demo/`). The frontend runs in *demo mode* by default and switches to *live mode* only when `/api/session/status` says review is open and the browser holds an accepted code + name; live calls carry `X-Reviewer-Code` / `X-Reviewer-Name` headers and any failure drops back to demo. Vercel rewrites `/api`, media paths and `/admin` to Railway, where `server.py` runs with a new `review.py` module that gates costly routes, enforces expiry and a daily cap, logs usage to `/data/review-log.jsonl`, and serves `/admin`.

**Tech Stack:** Python 3.11 stdlib HTTP server (`server.py`), `unittest` (no new test deps), React 19 + Vite + Remotion (`web/`), Docker on Railway, Vercel rewrites, Codex CLI (`@openai/codex`).

**Spec:** `docs/superpowers/specs/2026-11-13-hosted-review-design.md`

## Global Constraints

- Env names, exactly: `REVIEWER_CODE`, `ADMIN_CODE`, `REVIEW_EXPIRES_AT` (ISO 8601 **with** timezone), `REVIEW_DAILY_CAP` (default `80`), `CODEX_AUTH_JSON`, `CODEX_HOME` (`/data/codex` on Railway), `REVIEW_DATA_DIR` (default `/data`; tests point it at a temp dir).
- Gate is active only when `REVIEWER_CODE` is set; the laptop (`BLOCKCUT_AI=codex`) and demo instance (`BLOCKCUT_DEMO=1`) must behave exactly as today without it.
- Name: required, trimmed, 2-40 characters.
- Wrong code: message `That code isn't valid or has expired`; after 5 wrong tries the client address waits 60 s. Addresses live in memory only.
- Log file `REVIEW_DATA_DIR/review-log.jsonl`; entry keys exactly `time` (UTC ISO), `name`, `action`, `topic` (≤120 chars), `ok`, `seconds`. **No IP, no user agent.**
- Admin page shows times in Asia/Manila (UTC+8), newest first.
- Gated routes: `/api/plan`, `/api/edit`, `/api/voice`, `/api/assets/find`, `/api/assets/search`, `/api/assets/import`, `/api/assets/scrape`, `/api/assets/upload`, `/api/assets/delete`, `GET /api/assets`, `/api/render`, `/api/styles/from-url`, `/api/styles/delete`, `/api/footage/*`, `/api/shots/render`. Ungated: `GET /api/styles`, `/api/voices`, `/api/models3d`, job status GETs, static media, `/api/session`, `/api/session/status`.
- Locked/expired/cap responses: HTTP 401 `{"error": "locked"}` (cap: 429 `{"error": "Today's live limit is reached; the demo still works."}`).
- Secrets never in the repo, the Vercel bundle, responses or log lines.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Backend goes away mid-session (Railway restart, expiry passes while a reviewer is working) → the next live call shows a short notice and the editor keeps the current video in demo mode; nothing is lost. Test in Task 3.
2. A browser still holding a code after expiry, or an old/wrong code → on load the site quietly starts in demo mode and the chip offers "Enter code" again; no error banner. Test in Task 3.
3. A reviewer name containing HTML (`<script>`, `&`) → `/admin` shows it as text (escaped) and the CSV keeps it intact. Test in Task 5.
4. Two reviewers acting at the same moment → log lines never interleave or get lost. Test in Task 4.
5. `REVIEW_EXPIRES_AT` set without a timezone or unparsable → treated as already expired (fail closed), with a startup warning. Test in Task 4.

---

### Task 1: Demo bundle, checked and committed

**Files:**
- Keep/complete: `web/public/demo/` (index.json, ube.json, jeepney.json, tower_defense.json, styles.json, media/)
- Create: `deploy/check_demo.py`
- Test: `tests/test_demo_bundle.py`

**Interfaces:**
- Produces: `web/public/demo/index.json` shape `{"plans": [{"file": str, "keywords": [str], "title": str}], "credits": ...}`; every `/demo/...` URL inside a plan resolves to a file under `web/public/demo/`. `deploy/check_demo.py` exposes `missing_files(demo_dir: Path) -> list[str]`.

- [ ] **Step 1: Write the failing test** `tests/test_demo_bundle.py::test_every_demo_url_exists` — imports `missing_files` from `deploy/check_demo.py`, asserts `missing_files(ROOT/"web/public/demo") == []`; and `test_index_lists_three_plans` asserting the files are `ube.json`, `jeepney.json`, `tower_defense.json` and each has a non-empty `keywords` list.
- [ ] **Step 2: Run** `.venv/Scripts/python -m unittest tests.test_demo_bundle -v` → FAIL (`No module named ... check_demo`).
- [ ] **Step 3: Implement `missing_files(demo_dir) -> list[str]`** in `deploy/check_demo.py`: walk every plan JSON listed in index.json, collect string values starting with `/demo/`, return those whose file is missing. Add `if __name__ == "__main__"` printing the result and exiting 1 if any. Fix any missing file it reports (copy from `web/public/{assets,media,music,models3d}` of the main checkout, keeping the referenced name).
- [ ] **Step 4: Run** the test → PASS.
- [ ] **Step 5: Complete each demo video**: any scene without `audio` gets voiced through the laptop API (`POST /api/voice {plan, index: null}`), with the new audio copied into `demo/media/` and URLs rewritten to `/demo/media/...`. Then render each plan to MP4 with the laptop's `POST /api/render` (or `remotion render ... --scale=0.5` for size), save as `web/public/demo/<name>.mp4`, and add `"exportUrl": "/demo/<name>.mp4"` to that plan. Add a test `test_export_urls_exist` asserting every plan has an `exportUrl` that `missing_files` covers.
- [ ] **Step 6: Run** the tests → PASS; `du -sh web/public/demo` stays under 45 MB (re-render at a lower scale if not).
- [ ] **Step 7: Commit** `web/public/demo deploy/check_demo.py tests/test_demo_bundle.py` — "Demo bundle for the always-on Vercel site, with a file check".

### Task 2: Frontend demo mode (works with no backend at all)

**Files:**
- Create: `web/src/demo.ts`
- Modify: `web/src/App.tsx` (the `api()` helper at top, `generate()` ~line 300, styles fetch ~line 90, gated actions: `prompt()`, `voice()`, image find, render/export buttons)
- Test: browser verification (no frontend test runner in this repo) + `npx tsc -b`

**Interfaces:**
- Produces (in `demo.ts`): `type Mode = 'demo' | 'live'`; `loadDemoIndex(): Promise<DemoIndex>`; `matchDemo(topic: string, index: DemoIndex): DemoEntry | null` (case-insensitive keyword substring, first match); `loadDemoPlan(entry: DemoEntry): Promise<Plan>`; `DEMO_COOK_MS = 4000`.
- Produces (in `App.tsx`): state `mode: Mode` (starts `'demo'`), function `needsCode(action: string)` that shows the notice "Needs a reviewer code" with an "Enter code" button (opens Task 3's dialog via `setUnlockOpen(true)`).
- Consumes: Task 1's `index.json` shape.

- [ ] **Step 1: Implement `demo.ts`** with the signatures above. `loadDemoIndex` fetches `/demo/index.json` once and caches it.
- [ ] **Step 2: In `generate()`**, when `mode === 'demo'`: run the normal cooking screen; `matchDemo(text)` → wait `DEMO_COOK_MS`, then open `loadDemoPlan(entry)` exactly as a generated plan (same reveal animation); no match → stop cooking and show "Live generation is for reviewers. Try one of the demo videos" with the demo titles as buttons that start that demo. Skip the `/api/assets/find` call in demo mode.
- [ ] **Step 3: Styles in demo mode**: if `GET /api/styles` fails, load `/demo/styles.json` (so the format menu still fills).
- [ ] **Step 4: Gated actions in demo mode** (`prompt()` AI edits, `voice()`, image search/import, Render MP4, style-from-YouTube, footage upload) call `needsCode(...)` instead of the API. Export in demo mode: if `plan` is a demo plan with `exportUrl`, offer "Download video" pointing at it; else `needsCode`.
- [ ] **Step 5: Verify** `cd web && npx tsc -b` passes; run `npx vite --port 5191` with `BLOCKCUT_API=http://127.0.0.1:9` (nothing listening) and check in the browser: start screen loads, format menu filled, the ube starter opens the ube video after ~4 s, "a video about cats" shows the reviewer message with three demo buttons, timeline/inspector/playback work, AI edit shows "Needs a reviewer code".
- [ ] **Step 6: Commit** `web/src/demo.ts web/src/App.tsx` — "Demo mode: the editor and ready videos work with no backend".

### Task 3: Reviewer access in the frontend

**Files:**
- Create: `web/src/review.ts`
- Modify: `web/src/App.tsx` (api() headers, start screen + header chip, mode switch), `web/src/App.css` (dialog + chip, both themes)
- Test: browser verification against a local server from Task 5 + `npx tsc -b`

**Interfaces:**
- Produces (`review.ts`): `getAccess(): {code: string, name: string} | null` (localStorage key `shortcut.review`); `saveAccess(a)`, `clearAccess()`; `reviewHeaders(): Record<string,string>` → `{'X-Reviewer-Code', 'X-Reviewer-Name'}` or `{}`; `checkStatus(): Promise<{open: boolean, expiresAt?: string}>` (GET `/api/session/status`, any failure → `{open:false}`); `unlock(code, name): Promise<{ok: true, name: string, expiresAt: string} | {ok: false, error: string}>` (POST `/api/session`).
- Consumes: Task 2's `mode`, `needsCode`; Task 5's `/api/session` and `/api/session/status` responses.

- [ ] **Step 1: Implement `review.ts`** with those signatures; `api()` in App.tsx merges `reviewHeaders()` into every request's headers.
- [ ] **Step 2: Mode switch on load**: `checkStatus()`; if open and `getAccess()` exists, call `unlock()` with it; success → `mode='live'`, else `clearAccess()` and stay `demo` silently (Review Focus 2).
- [ ] **Step 3: Unlock dialog** (`unlockOpen` state): fields Code + Your name (2-40 chars, validated before sending), button "Unlock live generation"; error text shown under the fields; on success `saveAccess`, `mode='live'`, close. Open it from a "Reviewer access" link on the start screen (under the composer) and from `needsCode`'s "Enter code" button.
- [ ] **Step 4: Live chip** in the editor header and on the start screen: "Live · {name} · until {date in Manila time}" with "Sign out" (`clearAccess()`, `mode='demo'`).
- [ ] **Step 5: Fallback** (Review Focus 1): in `api()`, when `mode==='live'` and a response is 401 `locked`, 429, 5xx, or a network error: set `mode='demo'`, toast "Live access ended or is unavailable. You're back in demo mode; your video is kept.", and rethrow so the current action stops cleanly. The open plan stays on screen.
- [ ] **Step 6: Verify** `npx tsc -b`; with the Task 5 local server (`REVIEWER_CODE=test-code`, `REVIEW_EXPIRES_AT` = tomorrow), check: wrong code → error text; right code + name → chip appears and a real generation works; set `REVIEW_EXPIRES_AT` to the past and restart server → next action toasts and falls back; reload → starts in demo with no error.
- [ ] **Step 7: Commit** — "Reviewer access: code + name unlock, live chip, graceful fallback to demo".

### Task 4: `review.py` — gate, expiry, cap, limiter, log

**Files:**
- Create: `review.py`
- Test: `tests/test_review.py`

**Interfaces:**
- Produces:
  - `active() -> bool` — `REVIEWER_CODE` is set.
  - `expires_at() -> datetime | None` — parsed `REVIEW_EXPIRES_AT`; naive or invalid → returns `datetime.min` with tz UTC (fail closed) and prints one warning.
  - `is_open(now: datetime | None = None) -> bool` — active and now < expires_at.
  - `check(code: str, name: str, client: str) -> tuple[bool, str]` — constant-time compare (`hmac.compare_digest`); validates name 2-40 after trim; applies the 5-tries/60 s limiter keyed by `client` (in-memory dict, never persisted); returns `(True, clean_name)` or `(False, message)`.
  - `allow_action() -> bool` — daily cap from `REVIEW_DAILY_CAP` (default 80), counted per UTC date, in memory.
  - `log(name: str, action: str, topic: str, ok: bool, seconds: float) -> None` — appends one JSON line under a `threading.Lock`; keys exactly per Global Constraints; topic cut to 120 chars.
  - `read_log() -> list[dict]` (newest first), `log_csv() -> str`.
  - `expire_credentials() -> bool` — if not `is_open()`, delete `$CODEX_HOME/auth.json` if present; returns whether a file was removed.
  - `seed_credentials() -> None` — if `is_open()` and `$CODEX_HOME/auth.json` is absent and `CODEX_AUTH_JSON` is set, write it (mode 0600).

- [ ] **Step 1: Write failing tests** in `tests/test_review.py` (each test sets env via `unittest.mock.patch.dict(os.environ, ...)` and `REVIEW_DATA_DIR`/`CODEX_HOME` to a `tempfile.TemporaryDirectory`):
  - `test_inactive_without_code`: no `REVIEWER_CODE` → `active() is False`.
  - `test_check_accepts_right_code_and_trims_name`: `check("abc", "  Maria ", "c1") == (True, "Maria")`.
  - `test_check_rejects_wrong_code_message`: `check("nope","Maria","c1") == (False, "That code isn't valid or has expired")`.
  - `test_name_length`: names `"A"` and `"x"*41` rejected; `"Al"` accepted.
  - `test_limiter_after_five_wrong`: 5 wrong tries from `"c2"`, then the right code from `"c2"` is rejected; from `"c3"` it is accepted.
  - `test_expired_rejects`: `REVIEW_EXPIRES_AT` in the past → `check(...)[0] is False` and `is_open() is False`.
  - `test_naive_expiry_fails_closed` (Review Focus 5): `"2030-01-01T00:00:00"` (no tz) → `is_open() is False`.
  - `test_daily_cap`: `REVIEW_DAILY_CAP=3` → three `allow_action()` True, fourth False.
  - `test_log_line_shape`: after `log("Maria","plan","x"*200,True,1.5)`, the single line has exactly the keys `{"time","name","action","topic","ok","seconds"}` and `len(topic)==120`.
  - `test_log_concurrent_writes` (Review Focus 4): 20 threads × 25 `log()` calls → 500 lines, every line valid JSON.
  - `test_expire_and_seed_credentials`: open window + `CODEX_AUTH_JSON='{"x":1}'` → `seed_credentials()` creates the file; set expiry to past → `expire_credentials() is True` and file gone; `seed_credentials()` then writes nothing.
- [ ] **Step 2: Run** `.venv/Scripts/python -m unittest tests.test_review -v` → FAIL (no module).
- [ ] **Step 3: Implement `review.py`** with the signatures above. Read env on each call (no import-time caching) so tests and Railway env changes apply.
- [ ] **Step 4: Run** the tests → all PASS.
- [ ] **Step 5: Commit** `review.py tests/test_review.py` — "review.py: reviewer gate, expiry, daily cap, usage log".

### Task 5: Wire the gate, session routes and `/admin` into `server.py`

**Files:**
- Modify: `server.py` (`Handler.do_GET`, `Handler.do_POST`, `reply_slow`, `__main__` block ~line 1400)
- Test: `tests/test_server_review.py`

**Interfaces:**
- Consumes: Task 4's `review` functions.
- Produces (HTTP):
  - `GET /api/session/status` → `{"open": bool, "expiresAt": iso|null}` (ungated).
  - `POST /api/session {code, name}` → 200 `{"ok": true, "name": str, "expiresAt": iso}` or 401 `{"error": msg}`; logs action `"unlock"` (ok true/false; name as typed, trimmed to 40).
  - Gated routes (Global Constraints list): without valid headers or when closed → 401 `{"error":"locked"}`; over cap → 429; otherwise run, then `review.log(name, action, topic, ok, seconds)` where `action` = route tail (`plan`, `edit`, `voice`, `assets/find`, …) and `topic` = `body.topic` or `body.instruction` or `body.query` or `body.url`.
  - `GET /admin` → HTML login form; `POST /admin` with `code` (form-encoded) → sets cookie `sc_admin=<random token>; Path=/admin; HttpOnly; SameSite=Lax; Max-Age=43200` (tokens in memory) and redirects to `GET /admin`; with a valid cookie `GET /admin` shows the table (Manila time, newest first, counts per name, link to `/admin/log.csv`); all user text passed through `html.escape`.
  - `GET /admin/log.csv` (valid cookie) → `text/csv` of `review.log_csv()`.
- Startup (`__main__`): bind `0.0.0.0` when env `PORT` is set (use `PORT`), else today's `127.0.0.1` + `BLOCKCUT_PORT`; call `review.seed_credentials()` then `review.expire_credentials()`; when the gate is active, `review.expire_credentials()` also runs at the start of every gated request.

- [ ] **Step 1: Write failing tests** in `tests/test_server_review.py`: start `ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)` in a thread with env (`REVIEWER_CODE=test-code`, `ADMIN_CODE=admin-code`, `REVIEW_EXPIRES_AT`=+1 day, `REVIEW_DATA_DIR`=temp), and replace `server.ROUTES["/api/plan"]` with a stub returning `{"title":"stub","scenes":[]}`:
  - `test_status_open`: GET `/api/session/status` → `open is True`.
  - `test_plan_locked_without_headers`: POST `/api/plan` → 401 body `{"error":"locked"}`.
  - `test_plan_with_headers_runs_and_logs`: headers `X-Reviewer-Code: test-code`, `X-Reviewer-Name: Maria` → response contains `"stub"`; `review.read_log()[0]` has `name=="Maria"`, `action=="plan"`, `ok is True`.
  - `test_session_wrong_code`: POST `/api/session` wrong code → 401 with the exact wrong-code message.
  - `test_ungated_styles_without_headers`: GET `/api/styles` → 200.
  - `test_assets_list_gated`: GET `/api/assets` without headers → 401.
  - `test_admin_requires_code_and_escapes` (Review Focus 3): log a name `<script>x</script>`; GET `/admin` without cookie shows a form and not the name; POST the admin code, follow the cookie; page contains `&lt;script&gt;` and not `<script>x`.
  - `test_csv`: with the admin cookie, `/admin/log.csv` → `text/csv`, header row `time,name,action,topic,ok,seconds`.
  - `test_gate_inactive_by_default`: without `REVIEWER_CODE`, POST `/api/plan` with no headers reaches the stub (laptop behaviour unchanged).
- [ ] **Step 2: Run** `.venv/Scripts/python -m unittest tests.test_server_review -v` → FAIL.
- [ ] **Step 3: Implement** the routes and the gate. Check the gate **before** `reply_slow` starts (so locked requests get a real 401, not a 200 with spaces). Log after the route returns (success) or fails (`ok=False`), including from inside `reply_slow`'s worker.
- [ ] **Step 4: Run** Task 4 + Task 5 tests → PASS. Also start the server locally with no review env and confirm `curl http://127.0.0.1:8787/api/styles` still 200 and a plan request is not gated.
- [ ] **Step 5: Commit** — "server: reviewer gate, session routes, usage log and /admin page".

### Task 6: Railway container

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `railway.json`, `deploy/start.sh`
- Modify: `requirements.txt` only if a runtime import is missing

**Interfaces:**
- Consumes: Task 5 startup behaviour (`PORT`, `seed_credentials`, `expire_credentials`).
- Produces: an image that runs `deploy/start.sh` → `exec python server.py` with `BLOCKCUT_AI=codex`, `CODEX_HOME=/data/codex`, `REVIEW_DATA_DIR=/data`.

- [ ] **Step 1: Write the Dockerfile** (my calls, builder may adjust layering): base `python:3.11-slim-bookworm`; install Node 22 (NodeSource) and Remotion's Chrome deps (`libnss3 libdbus-1-3 libatk1.0-0 libgbm1 libasound2 libxrandr2 libxkbcommon0 libxfixes3 libxcomposite1 libxdamage1 libatk-bridge2.0-0 libpango-1.0-0 libcairo2 libcups2`); `pip install -r requirements.txt`; `npm i -g @openai/codex`; `npm ci --prefix web` and `npx remotion browser ensure` in `web/`; download faster-whisper `base` into `models/faster-whisper-base` at build; copy the repo (respecting `.dockerignore`: `.git`, `.venv`, `web/node_modules`, `tools/`, `models/` except whisper, `web/public/{assets,media,renders,footage,models3d}`, `briefs/logs`, `.env`).
- [ ] **Step 2: `deploy/start.sh`**: `mkdir -p /data/codex`; export the three env defaults above if unset; `exec python server.py`.
- [ ] **Step 3: `railway.json`**: Dockerfile builder, start command `sh deploy/start.sh`, healthcheck path `/api/session/status`, restart policy on failure.
- [ ] **Step 4: Local proof without Docker**: run `REVIEWER_CODE=test-code ADMIN_CODE=admin-code REVIEW_EXPIRES_AT=<+1d> REVIEW_DATA_DIR=$TEMP/rv CODEX_HOME=$TEMP/rv/codex PORT=8790 .venv/Scripts/python server.py` and confirm it listens on `0.0.0.0:8790`, `/api/session/status` → open, a gated generation with headers works through Codex, and `$TEMP/rv/review-log.jsonl` gains a line.
- [ ] **Step 5: Commit** — "Railway container: Dockerfile, start script, healthcheck".

### Task 7: Vercel wiring, owner runbook

**Files:**
- Create: `deploy/set_backend.py` (generalises `deploy/set_tunnel.py`; keep `set_tunnel.py` as a thin wrapper or delete it and update references)
- Modify: `web/vercel.json` (generated), `HANDOFF.md`, `README.md`
- Create: `docs/review-runbook.md`

**Interfaces:**
- Produces: `set_backend.py <https-url> [--no-push]` writes rewrites for `api, assets, media, music, footage, models3d, renders, admin` (`/admin` and `/admin/:path*`) to the URL, keeps `framework`, `buildCommand`, `outputDirectory`, and never rewrites `/demo/*` or `/_app/*`.

- [ ] **Step 1: Implement `set_backend.py`**; run it with a placeholder Railway URL `--no-push` and assert by eye that `web/vercel.json` has 9 rewrites and no `/demo` rule.
- [ ] **Step 2: Runbook** `docs/review-runbook.md`: owner steps in order — Railway: new project from GitHub repo, add volume `/data`, set `REVIEWER_CODE`, `ADMIN_CODE`, `REVIEW_EXPIRES_AT` (7 days after sending), optional `CODEX_AUTH_JSON`; open Railway shell and run `CODEX_HOME=/data/codex codex login --device-auth` (own server sign-in); copy the public URL → `.venv/Scripts/python deploy/set_backend.py https://<railway-url>`; confirm Vercel redeployed; test; send the email (template included, with link and code); how to read `/admin`; how to end early (change `REVIEW_EXPIRES_AT`).
- [ ] **Step 3: Update** HANDOFF "Now" section and README "Run it" with the hosted setup (one paragraph each, pointing to the runbook).
- [ ] **Step 4: Commit** — "Deploy: set_backend.py, review runbook".

### Task 8: End-to-end check on the real hosts (after owner actions)

**Files:** none (verification); fixes go to the task that owns the broken code.

- [ ] **Step 1: Demo with no backend**: before Railway exists (or with `vercel.json` pointing at an unreachable host), open the Vercel URL: start screen, ube/jeepney/tower-defense demos, theme pill, editor playback; no console errors besides the expected failed `/api/session/status`.
- [ ] **Step 2: Live**: with Railway up, enter the test code + a name on the Vercel URL; generate one short video; AI edit one segment; voice; export MP4 (or confirm the demo-only export message if memory is short — then record that in HANDOFF).
- [ ] **Step 3: Admin**: `/admin` on the Vercel domain shows those actions under the test name, Manila time; CSV downloads.
- [ ] **Step 4: Expiry drill**: set `REVIEW_EXPIRES_AT` to 1 minute ahead in Railway, wait, act → fallback toast; Railway shell shows `/data/codex/auth.json` gone. Restore the real expiry and sign the server in again.
- [ ] **Step 5: Commit** any fixes; push; update HANDOFF status.
