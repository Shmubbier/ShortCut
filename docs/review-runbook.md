# Hosted review runbook (owner)

Vercel serves the editor and a bundled `/demo/` (works with no backend). A Railway container runs `server.py` behind a
reviewer code, with a usage log and an `/admin` page. Never commit a real code to this repo.

Note: `web/vercel.json` currently contains the placeholder `https://REPLACE-WITH-RAILWAY-URL.up.railway.app`. Step 5 replaces it.

## 1. Railway project
1. New project, deploy from GitHub repo `Shmubbier/ShortCut` (the root `Dockerfile` and `railway.json` are picked up; healthcheck is `/api/session/status`).
2. Plan: Hobby (about 2 GB RAM). Turn app sleeping OFF.
3. Add a volume mounted at `/data`.

## 2. Variables (Railway service > Variables)
| Name | Value |
|---|---|
| `REVIEWER_CODE` | shared with panelists, at least 10 characters |
| `ADMIN_CODE` | owner only, at least 16 characters |
| `REVIEW_EXPIRES_AT` | ISO 8601 with timezone, 7 days after you send the email, e.g. `2026-11-21T18:00:00+08:00` |
| `CODEX_AUTH_JSON` | optional fallback seed: contents of your laptop's `~/.codex/auth.json` |

The image already sets `BLOCKCUT_AI=codex`, `CODEX_HOME=/data/codex`, `REVIEW_DATA_DIR=/data`.

## 3. Server's own Codex sign-in
Open the service's shell in Railway and run:

```bash
CODEX_HOME=/data/codex codex login --device-auth
```

It prints a code; enter it in your browser. This keeps the server's sign-in separate from your laptop's.

## 4. Copy the public URL
Service > Settings > Networking > generate a domain, e.g. `https://shortcut-production.up.railway.app`.

## 5. Point Vercel at Railway
From the repo root:

```bash
.venv/Scripts/python deploy/set_backend.py https://<railway-url>
```

This rewrites `web/vercel.json` (api, assets, media, music, footage, models3d, renders, `/admin`; never `/demo` or `/_app`), commits and pushes.
Add `--no-push` to only write the file. Confirm the Vercel deployment (Root Directory `web`) finished.

## 6. Test
- Open `https://<vercel-domain>/demo/`: the three demo videos play without a code.
- Click "Reviewer access" (start screen or editor header), enter `REVIEWER_CODE` and a name, generate a short video, export.
- Open `https://<vercel-domain>/admin`, enter `ADMIN_CODE`: your test shows up.

## 7. Email template
Subject: ShortCut: hackathon review link (valid until <DATE>)

> Hi <NAME>,
>
> You can try ShortCut here: https://<vercel-domain>
>
> Click "Reviewer access" (start screen or editor header) and enter this code and your name: <REVIEWER CODE>
>
> With it you can generate a video from a topic, edit it, add voice, and export. It works for 7 days, until <DATE>.
> Without the code you can still open the three demo videos.

## 8. Usage log
`https://<vercel-domain>/admin`, enter the admin code. The table is in Manila time; "Download CSV" exports it.

## 9. Ending
- Early: set `REVIEW_EXPIRES_AT` in Railway to a past time (or remove `REVIEWER_CODE`).
- Automatically: after the window the server deletes `/data/codex/auth.json` and refuses live requests; the site stays in demo mode.
