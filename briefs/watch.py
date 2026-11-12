"""Live view of the director's Codex tasks: what each one is doing right now.
Run:  .venv/Scripts/python briefs/watch.py        (Ctrl+C to stop; refreshes every 5 s)
Reads briefs/logs/<task>.jsonl, the event stream `codex exec --json` writes."""
import json
import os
import subprocess
import time
from pathlib import Path

LOGS = Path(__file__).parent / "logs"
WT = Path(__file__).parent.parent.parent / "ManilaHack-wt"


def summarize(path: Path) -> dict:
    out = {"messages": [], "commands": 0, "last_cmd": "", "done": False, "tokens": 0}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        item = d.get("item") or {}
        kind = item.get("type") or d.get("type")
        if kind == "agent_message" and item.get("text"):
            out["messages"].append(item["text"].strip().replace("\n", " "))
        elif kind in ("command_execution", "exec_command", "local_shell_call"):
            out["commands"] += 1
            out["last_cmd"] = str(item.get("command") or item.get("cmd") or "")[:110]
        elif d.get("type") == "turn.completed":
            out["done"] = True
            out["tokens"] = (d.get("usage") or {}).get("output_tokens", 0)
    return out


def commits(task: str) -> list[str]:
    try:
        r = subprocess.run(["git", "-C", str(WT / task), "log", "--oneline", "main..HEAD"], capture_output=True, text=True, timeout=10)
        return r.stdout.strip().splitlines()
    except Exception:
        return []


while True:
    os.system("cls" if os.name == "nt" else "clear")
    print(f"Codex tasks (director: Claude Code) · {time.strftime('%H:%M:%S')} · Ctrl+C to stop\n")
    for log in sorted(LOGS.glob("*.jsonl")):
        task = log.stem
        s = summarize(log)
        final = LOGS / f"{task}.final.md"
        state = "DONE" if final.exists() and final.stat().st_size > 0 else "running"
        age = int(time.time() - log.stat().st_mtime)
        print(f"■ {task:<14} {state:<8} last activity {age:>4}s ago · {s['commands']} commands · commits on branch: {len(commits(task))}")
        if s["messages"]:
            print(f"    says: {s['messages'][-1][:150]}")
        if s["last_cmd"]:
            print(f"    ran:  {s['last_cmd']}")
        for c in commits(task)[:3]:
            print(f"    ✓ {c}")
        print()
    time.sleep(5)
