# Voice task report

## What works

- `tts.py` provides Edge and local speech.cpp/Qwen synthesis, caches audio by voice/rate/delivery/text, and starts/reuses the local speech server on `127.0.0.1:8792`. It detects the available NVIDIA Vulkan device, so this machine uses `Vulkan1` (RTX 4070 Laptop GPU).
- `/api/voice` generated a seven segment plan with `qwen:ryan` in **13.21 s**. After installing the local Whisper base model, all seven scenes returned Whisper word timings (11–14 words each); every timing was nonnegative and ended within that scene's measured WAV duration. Scene durations were 5.28–7.76 s.
- Filipino Edge path: a Tagalog segment returned an MP3 and 10 word timings from Whisper (`fil-PH-AngeloNeural`).
- Qwen 1.7B synthesis accepted delivery notes, and the narrator list is exposed at `/api/voices` when the executable and selected Qwen model are available. An English plan without a stored voice defaults to Qwen when available; otherwise Edge Andrew remains the fallback.
- Optional Scribe v2 timing code is present. No `ELEVENLABS_API_KEY` is configured, so that external API path was not exercised; Whisper is the verified timing source here.

## Install measurements

| Item | Size | Download time | Integrity |
|---|---:|---:|---|
| speech.cpp v0.10.1 Windows x64 Vulkan zip | 29,548,632 bytes | 23.02 s | SHA-256 matched published `a8fe0e4b4f463c460e7ace9d38c363bec08b254cac5a7f764b7967af35d4fa1a` |
| Qwen3-TTS 0.6B Q8_0 | 1,214 MB | 390.07 s | speech.cpp reported SHA-256 checked |
| Qwen3-TTS 1.7B Q8_0 | 2,288 MB | 1,043.36 s | speech.cpp reported SHA-256 checked |
| faster-whisper base `model.bin` | 145,217,532 bytes (+ tokenizer/config files) | 100.3 s | downloaded from the Hugging Face model repository; no separate digest check run |

speech.cpp and model weights are in git-ignored shared folders under the main checkout / user model cache. The generated comparison audio totals **1,680,216 bytes** in the ignored `briefs/voice-samples/` folder.

## Voice timing comparison

The three identical English lines (calm, excited, question) were each synthesized twice per engine. I removed each generated cache file between attempts so the warm measurement includes inference, not a cache hit. The 0.6B and 1.7B first request for the calm line included server/model startup; later line timings began with the server warm. The benchmark script and source lines are reproducible from the sample names and this report, but no timing spreadsheet/script was retained.

| Line | Edge first / warm (s) | Qwen 0.6B first / warm (s) | Qwen 1.7B first / warm (s) |
|---|---:|---:|---:|
| Calm | 1.52 / 0.89 | 17.26 / 1.82 | 9.42 / 2.85 |
| Excited | 0.91 / 0.82 | 1.73 / 1.64 | 1.81 / 1.72 |
| Question | 0.82 / 0.95 | 2.03 / 1.66 | 2.04 / 2.58 |

The first 0.6B value includes starting the Vulkan server and generating the calm line. Both Qwen models ran on Vulkan1; voice quality was not rated by a listener in this check. Audio files are in `briefs/voice-samples/`: `calm`, `excited`, and `question` variants for Edge, Qwen 0.6B, and Qwen 1.7B.

## Verification

- `server.py` AST parse and `import tts` with the shared Python 3.11.9 venv: passed.
- `cd web; .\\node_modules\\.bin\\tsc.cmd -b`: passed with no diagnostics (1.52 s combined with the recipe check).
- `node src/video/bench3d/recipe.check.mts`: passed with `recipe.ts OK` (boar recipe 85.3 ms; fanart recipe 57.6 ms on final run).
- Real Edge/Qwen synthesis, Qwen delivery instructions on 1.7B, full seven segment `/api/voice`, Whisper timing alignment, and Filipino fallback: verified as above.
- API used for this check: `127.0.0.1:8791`; speech.cpp used `127.0.0.1:8792`. Ports 8787, 5173, and 5175 were not touched.
- Browser verification of the Settings narrator list was not possible because the computer-use browser host was unavailable. `/api/voices` was exercised directly and the TypeScript build passed.

## Reproduce

```powershell
$env:BLOCKCUT_PORT = '8791'
$env:WHISPER_MODEL = 'C:/Users/naomi/Documents/vscode shenanigans/ManilaHack/models/faster-whisper-base'
& 'C:/Users/naomi/Documents/vscode shenanigans/ManilaHack/.venv/Scripts/python.exe' server.py
```

The speech binary is at `C:/Users/naomi/Documents/vscode shenanigans/ManilaHack/tools/speechcpp/speech.exe`. Set `BLOCKCUT_QWEN_MODEL=qwen3-tts-1.7b` before starting the API to use 1.7B and pass each scene's `delivery` note as an instruction. `qwen3-tts-0.6b` is the default model. Filipino `fil-PH-*` voices remain Edge. Set `ELEVENLABS_API_KEY` in ignored `.env` to enable optional Scribe v2 alignment.

## Dependencies, licenses, and merge note

- speech.cpp is MIT; Qwen3-TTS weights are Apache-2.0. faster-whisper is MIT and uses the converted Whisper base weights. Edge TTS remains an online, unofficial service; Scribe v2 sends generated audio to ElevenLabs and consumes that account's API usage when enabled.
- No Python or Node dependency was added. `.gitignore` already covers `tools/`, `models/`, generated media, and voice samples.
- The shared model and binary live outside this branch and should not be committed. Merge the `tts.py` readiness/cache fix and this report with the voice adapter commit. Verify model and audio exist on any demo machine before selecting Qwen.

Sources: [speech.cpp releases](https://github.com/nyosegawa/speech.cpp/releases), [speech.cpp server API](https://github.com/nyosegawa/speech.cpp/blob/main/docs/server.md), [speech.cpp license and model licenses](https://github.com/nyosegawa/speech.cpp), [ElevenLabs transcript API](https://elevenlabs.io/docs/api-reference/speech-to-text/convert).
