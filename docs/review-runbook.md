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
| `REVIEW_EXPIRES_AT` | set this right before you send the email (step 7): ISO 8601 with timezone, 7 days later, e.g. `2026-11-21T18:00:00+08:00` |
| `CODEX_AUTH_JSON` | optional fallback seed: contents of your laptop's `~/.codex/auth.json` |

The image already sets `BLOCKCUT_AI=codex`, `CODEX_HOME=/data/codex`, `REVIEW_DATA_DIR=/data`, `REVIEW_HOSTED=1` (the hosted lock-down and credential removal key off `REVIEW_HOSTED`, not `PORT`).

## 3. Server's own Codex sign-in
Use the Railway CLI from Git Bash (all commands in this runbook are for Git Bash):

```bash
npm i -g @railway/cli
railway login
railway link        # pick the project and the service
railway ssh         # opens a shell inside the container
CODEX_HOME=/data/codex codex login --device-auth   # run this inside that shell
```

If your Railway dashboard shows a shell for the service, that works too. The login prints a code; enter it in your browser. This keeps the server's sign-in separate from your laptop's.

## 4. Copy the public URL
Service > Settings > Networking > generate a domain, e.g. `https://shortcut-production.up.railway.app`.

## 5. Point Vercel at Railway
From the repo root:

```bash
.venv/Scripts/python deploy/set_backend.py https://<railway-url>
```

This rewrites `web/vercel.json` (api, assets, media, music, footage, models3d, renders, `/admin`; never `/demo` or `/_app`), commits and pushes.
Vercel deploys from `main`, so push or merge there. Add `--no-push` to only write the file. Confirm the Vercel deployment (Root Directory `web`) finished.

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
> If the code says invalid, wait a minute and try again.

## 8. Usage log
`https://<vercel-domain>/admin`, enter the admin code. The table is in Manila time; "Download CSV" exports it.

## 9. Ending
- Early: set `REVIEW_EXPIRES_AT` in Railway to a past time. Do not just remove `REVIEWER_CODE`; keep it set until the service is gone (the server also fails closed if it is missing on Railway).
- Automatically: after the window the server deletes `/data/codex/auth.json` and refuses live requests; the site stays in demo mode.
- After the window: delete the `CODEX_AUTH_JSON` variable in Railway. After downloading the CSV from `/admin`, remove the Railway service and its volume.
