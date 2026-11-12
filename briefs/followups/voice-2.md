Director follow-up (Claude Code). You now have FULL ACCESS: no sandbox, so HTTPS downloads work (the network is ~2 MB/s), the shared
venv works (`C:/Users/naomi/Documents/vscode shenanigans/ManilaHack/.venv/Scripts/python`), and `git commit` works in your worktree.
I committed your first pass (f2a54e0) and merged the latest `main` into your branch (ecf6438). Keep everything that's there.

**Port fix:** port 8792 belongs to the assets agent's API. Run the speech.cpp server on **8795** (update `tts.py`) and your own API on 8791.

Finish the task, in this order, stopping to commit after each working step:
1. **Install speech.cpp** for Windows x64 (Vulkan) from https://github.com/nyosegawa/speech.cpp/releases into
   `C:/Users/naomi/Documents/vscode shenanigans/ManilaHack/tools/speechcpp/`. Verify the SHA-256 if one is published.
   Prefer the release zip over piping the install script into PowerShell; if you use the script, read it first.
2. **Get Qwen3-TTS 0.6B working** (`speech tts qwen3-tts-0.6b --voice <speaker> -o test.wav "Hello from Blockcut."`).
   Record the download size and time, the list of English speakers, and the first-call and warm-call latency.
3. **Try 1.7B** with an instruction ("excited, fast-paced") if VRAM allows (RTX 4070 Laptop, 8 GB). If it doesn't fit or is too slow
   (> 3 s per short line warm), keep 0.6B as the default and say so.
4. **End to end:** with your API on 8791, voice a 7-segment plan (`samples/ube.json` scenes are fine) through `/api/voice` with a
   `qwen:<speaker>` voice. Confirm audio, durations and Whisper word timings, and that captions stay aligned. Re-check that a
   `fil-PH-*` voice still works on Edge.
5. **Listening samples:** the three lines (calm, excited, question) in Edge vs Qwen 0.6B (vs 1.7B) in `briefs/voice-samples/`, plus
   the timing table in `briefs/voice.report.md`. Name the files clearly (`qwen06b-excited.wav`, etc.) so the user can compare.
6. Commit; final message as before.
