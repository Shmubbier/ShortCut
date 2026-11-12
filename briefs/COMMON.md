# Rules for every Codex task (from the director, Claude Code)

You are one of several agents working on **Blockcut** in parallel, each in its own git worktree and branch. Read `AGENTS.md`
(architecture, the Plan contract, verification) and `HANDOFF.md` (current state) first. The demo is **tonight, 6 PM**:
working and verified beats ambitious and half-done.

## Your workspace
- **Stay in your worktree.** It's the folder you were started in, on the branch named in your brief. Commit there only:
  small commits with clear messages ending in `Co-Authored-By: Codex <noreply@openai.com>`. **Don't merge into `main`, don't
  push, don't touch other branches or the main checkout** (`C:/Users/naomi/Documents/vscode shenanigans/ManilaHack`).
- **Python:** use the shared venv by absolute path:
  `"C:/Users/naomi/Documents/vscode shenanigans/ManilaHack/.venv/Scripts/python"`. Install new packages into it with `-m pip`,
  and add them to `requirements.txt` in your branch.
- **Node:** `web/node_modules` is linked from the main checkout; don't run `npm install` unless you add a package (then say so).
- **Your own ports.** The user is live-testing on the shared servers (API :8787, UI :5173, :5175). **Never stop or restart those.**
  Run your own API with `BLOCKCUT_PORT=<your port>` and, if you need the UI, `BLOCKCUT_API=http://127.0.0.1:<your port> npm --prefix web run dev -- --port <ui port>`.
- **Large downloads** (models, binaries): use resumable methods (`curl -L -C -`); verify checksums when published. Put them under
  the main checkout's git-ignored `models/` or `tools/` folder (absolute path) so other worktrees can reuse them.

## Ownership (to keep merges clean)
- Put new logic in **new modules** (named in your brief). Touch shared files (`server.py`, `App.tsx`, `Panels.tsx`,
  `Inspector.tsx`, `Video.tsx`) only with small, clearly delimited hooks: a route entry, an import, one call site.
- The Plan contract (types in `Video.tsx`, pydantic models in `server.py`) changes only with **optional** fields. Old plans must still load.

## Done means
1. `cd web && npx tsc -b` prints nothing; `node src/video/bench3d/recipe.check.mts` ends with "recipe.ts OK";
   `server.py` imports cleanly with the shared venv.
2. You exercised the feature for real (an actual model, download, render or request), not only a typecheck.
3. You wrote `briefs/<your-task>.report.md`: what works (with measured numbers), what doesn't, exact commands to reproduce,
   anything the director must do when merging, and any dependency or licence the user should know about. Be honest; say
   "not verified" when you didn't verify something.
4. Everything is committed on your branch. Your final message: the branch name, the commit list, and the report path.
