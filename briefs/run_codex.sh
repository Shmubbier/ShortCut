#!/usr/bin/env bash
# Director launcher: run one Codex task headless in its worktree.
# usage: briefs/run_codex.sh <task> <api_port> <ui_port>
set -u
TASK="$1"; API="$2"; UI="$3"
ROOT="C:/Users/naomi/Documents/vscode shenanigans/ManilaHack"
WT="C:/Users/naomi/Documents/vscode shenanigans/ManilaHack-wt/$TASK"
CX="$LOCALAPPDATA/OpenAI/Codex/bin/9e1da79431da526b/codex.exe"
LOGS="$ROOT/briefs/logs"; mkdir -p "$LOGS"
PROMPT="You are Codex, working as part of a team directed by Claude Code. Your worktree is $WT on branch codex/$TASK.
Read briefs/COMMON.md and then briefs/$TASK.md in this worktree, and do that task completely.
Your ports: run your own API with BLOCKCUT_PORT=$API and, if you need the UI, a dev server on port $UI with BLOCKCUT_API=http://127.0.0.1:$API.
Never stop or restart anything on ports 8787, 5173 or 5175: the user is live-testing there.
Shared Python venv: $ROOT/.venv/Scripts/python. Main checkout (read-mostly; only its git-ignored tools/, models/ and .venv may be written): $ROOT.
Work autonomously, without asking questions. When done, follow 'Done means' in COMMON.md."
"$CX" exec -C "$WT" -s workspace-write -c sandbox_workspace_write.network_access=true --add-dir "$ROOT" \
  --skip-git-repo-check --json -o "$LOGS/$TASK.final.md" "$PROMPT" > "$LOGS/$TASK.jsonl" 2> "$LOGS/$TASK.err"
echo "codex task $TASK exited with $?" >> "$LOGS/$TASK.final.md"
