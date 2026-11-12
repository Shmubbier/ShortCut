# Codex task 1: natural voiceover (speech.cpp + Qwen3-TTS), optional Scribe v2

Branch `codex/voice`. Read `briefs/COMMON.md` first.

## Problem
Voiceover uses Edge TTS (`server.py` `speak()` / `_tts()`): no intonation, robotic. The user wants
https://github.com/nyosegawa/speech.cpp, which runs **Qwen3-TTS** locally (Windows x64 Vulkan build, an OpenAI-style server
`speech serve <model>` → `POST /v1/audio/speech`, or the CLI `speech tts <model> --voice <name> -o out.wav "text"`).
The 0.6B model is ~1.2 GB. The 1.7B model can follow an **instruction on how to speak** ("excited, quick", "warm, slower"),
which is the expressiveness we want. Qwen3-TTS languages: en, zh, ja, ko, de, fr, es, it, pt, ru. **No Filipino**, so Filipino
voices (`fil-PH-*`) stay on Edge TTS.

## Build
1. **Install** speech.cpp's Windows release (the README's installer or the release zip; verify the SHA-256) into the main
   checkout's `tools/speechcpp/` (git-ignored; add it to `.gitignore` if needed). Fetch Qwen3-TTS **0.6B first**, then try **1.7B** if
   time and VRAM allow (RTX 4070 Laptop, 8 GB). Record download sizes and times.
2. **New module `tts.py`:** `synthesize(text, voice, style_hint) -> (wav_or_mp3_path, words)` with engines:
   - `qwen` (speech.cpp: start `speech serve` once as a managed subprocess on a free port, reuse it, restart if it dies);
   - `edge` (move the existing Edge TTS code here unchanged; still the fallback and the Filipino path).
   Pick the engine from the voice id: `qwen:<speaker>` → speech.cpp; anything else → Edge. Keep the per-(voice, text, style)
   file cache in `web/public/media/`.
   **Word timings:** Edge gives them; for Qwen output, run the existing `captions()` / Whisper path on the audio (it's already
   wired). If `ELEVENLABS_API_KEY` is set in `.env`, use **ElevenLabs Scribe v2** for word timings instead (batch STT, model
   `scribe_v2`, word-level timestamps; check their current API docs). Otherwise Whisper. Never require the key.
3. **Expressive delivery:** each segment can carry an optional `delivery` string (e.g. "punchy, excited"). Add it as an optional
   field to the pydantic `Scene` and `SceneData` (`delivery?: string`), and to `EDITING_GUIDE`: one short line telling the AI to
   write a delivery note per segment. Pass it to Qwen 1.7B as the speaking instruction (ignore it on 0.6B and Edge).
   Keep the existing voice-rate setting working.
4. **Hook-up (small):** `server.py` `speak()` / `voice()` call `tts.synthesize`; add the Qwen speakers to the narrator list in
   `web/src/Panels.tsx` (`VOICES`), labelled e.g. "Ryan · natural (Qwen)", and make a Qwen voice the default for English if it works.
   `GET /api/voices` (new) can report which engines are actually available, so the UI only lists working voices.
5. **Measure and compare:** for the same three lines (calm, excited, question), time Edge vs Qwen 0.6B vs Qwen 1.7B (first call and
   warm call). Save the audio files to `briefs/voice-samples/` (git-ignored if > 2 MB total) so the user can listen.

## Done
Voicing a full 7-segment plan with a Qwen voice works end to end through `/api/voice`. Captions stay aligned, the
Filipino path still works, and the report includes the timing table and how to switch engines.
