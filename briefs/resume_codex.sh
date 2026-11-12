#!/usr/bin/env bash
# Director: resume a Codex task's conversation (same context) with full access and a follow-up instruction.
# usage: briefs/resume_codex.sh <task> <thread-id> <prompt-file>
# Full access because the sandbox blocked the shared venv's base Python and git's worktree index under the main .git folder.
set -u
TASK="$1"; THREAD="$2"; PROMPT_FILE="$3"
ROOT="C:/Users/naomi/Documents/vscode shenanigans/ManilaHack"
WT="C:/Users/naomi/Documents/vscode shenanigans/ManilaHack-wt/$TASK"
CX="$LOCALAPPDATA/OpenAI/Codex/bin/9e1da79431da526b/codex.exe"
LOGS="$ROOT/briefs/logs"; mkdir -p "$LOGS"
cd "$WT" || exit 1
"$CX" exec resume "$THREAD" --dangerously-bypass-approvals-and-sandbox --json -o "$LOGS/$TASK.final.md" "$(cat "$PROMPT_FILE")" >> "$LOGS/$TASK.jsonl" 2>> "$LOGS/$TASK.err"
echo "codex task $TASK (resumed) exited with $?" >> "$LOGS/$TASK.final.md"
