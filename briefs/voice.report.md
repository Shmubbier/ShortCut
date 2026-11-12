# Voice task report

## Implemented

- Added `tts.py` with Edge TTS compatibility, a managed speech.cpp server on `127.0.0.1:8792`, Qwen WAV synthesis, SHA-1 keyed audio/timing cache, Qwen rate mapping, and optional 1.7B delivery instructions.
- Routed `/api/voice` through the adapter. Qwen uses WAV duration and the existing Whisper caption path; Edge retains its own word timings. If `ELEVENLABS_API_KEY` is present, Scribe v2 word timestamps are attempted first and Whisper/engine timings remain the fallback.
- Added optional `delivery` to the server and Plan segment shape and instructed the generator to write a short delivery note.
- Added `/api/voices`; the narrator settings add Qwen choices only when a speech.cpp executable or running Qwen service is discoverable. New English plans select Qwen when available, otherwise retain Edge Andrew.
- No Python package dependencies were added. `.gitignore` already ignores `tools/` and `briefs/voice-samples/`.

## Verification and limits

| Case | Result | Timing |
|---|---|---:|
| TypeScript build (`tsc -b`) | Passed; no diagnostics | included in 2.64 s combined command |
| Recipe self-check | Passed, ended with `recipe.ts OK` | boar recipe 84.6 ms; fanart recipe 61.3 ms |
| Shared Python interpreter | Not verified: interpreter process was denied by this sandbox (`Access is denied`) | n/a |
| speech.cpp Windows release / Qwen 0.6B / 1.7B | Not installed; GitHub download failed before transfer (`curl.exe` Schannel `SEC_E_NO_CREDENTIALS`); no local speech executable | n/a |
| Edge, Qwen, and Scribe audio comparisons (calm/excited/question) | Not run: Python server could not start; Qwen models absent and no ElevenLabs key was available to this task | n/a |
| Seven segment `/api/voice`, caption alignment, Filipino regression | Not verified | n/a |

The release page describes Windows x64 Vulkan archives and Qwen 0.6B/1.7B models; the current speech.cpp server takes `input`, `voice`, and `response_format: wav`, with `instructions` supported only by models that accept it. See [speech.cpp releases](https://github.com/nyosegawa/speech.cpp/releases), [speech.cpp server API](https://github.com/nyosegawa/speech.cpp/blob/main/docs/server.md), and [ElevenLabs transcript API](https://elevenlabs.io/docs/api-reference/speech-to-text/convert). The release archive SHA-256 and model download sizes/times could not be obtained in this environment, so installation and checksums remain for the director to complete.

## Reproduce / enable

After installing the verified Windows x64 Vulkan archive into `C:/Users/naomi/Documents/vscode shenanigans/ManilaHack/tools/speechcpp/` and making the Qwen model available to speech.cpp:

```powershell
$env:BLOCKCUT_PORT = '8791'
& 'C:/Users/naomi/Documents/vscode shenanigans/ManilaHack/.venv/Scripts/python' server.py
```

The first request with voice `qwen:ryan` starts/reuses `speech serve qwen3-tts-0.6b` at port 8792. Set `BLOCKCUT_QWEN_MODEL=qwen3-tts-1.7b` before starting the API to enable delivery instructions on the larger model. Set `ELEVENLABS_API_KEY` in the ignored `.env` to enable optional Scribe v2 timings. Filipino voice ids such as `fil-PH-AngeloNeural` stay on Edge. Voice rate remains in the plan's `voiceRate` field.

## Merge note

No main-checkout files were changed. Do not claim the Qwen voice task complete until the binary/model are installed and the missing real audio, timing comparison, Filipino, and seven-segment checks pass. The UI build and recipe self-check were run from this branch's `web/` directory.

The required commit is still pending: this environment denied writes to the worktree Git index at `C:/Users/naomi/Documents/vscode shenanigans/ManilaHack/.git/worktrees/voice/index.lock` because `.git` is read-only under the active filesystem policy. The working tree changes are left in place and unstaged for the director to commit from an authorized Git context.
