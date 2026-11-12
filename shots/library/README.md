# Blockcut shot library

Three self-contained Blender shot specs. Start with a working composition and edit its prompt/spec, then render with:

```powershell
$blender = "C:/Users/naomi/Documents/vscode shenanigans/ManilaHack/bench3d/tools/blender-5.3.0-windows-x64/blender.exe"
& $blender -b --factory-startup -P shots/render_shot.py -- shots/library/<name>.json shots/out/<name> --proof
& $blender -b --factory-startup -P shots/render_shot.py -- shots/library/<name>.json shots/out/<name> --final
```

The final mode writes PNG frames and an H.264 MP4. Proof mode writes six sampled frames, a contact sheet, and exact sample times. Change the prompt first, then the JSON values for timings, camera keys, colors, or props. Specs use GLB paths relative to the repository root or Blender primitives. The sample basket comes from the existing `web/public/bench3d` asset library.

| Shot | What it demonstrates | Prompt/spec | Thumbnail |
|---|---|---|---|
| **hero-orbit** | 10-second product hero: orbit, eased push-in at 6s, title at 1s, paper ground | [prompt](hero-orbit.prompt.md) · [spec](hero-orbit.json) | ![Hero orbit proof contact sheet](thumbs/hero-orbit.png) |
| **reveal-rise** | Faceted object rises with easeOutBack and a slow camera tilt | [prompt](reveal-rise.prompt.md) · [spec](reveal-rise.json) | ![Reveal rise frame](thumbs/reveal-rise.png) |
| **flyby** | Camera dolly past three props in a row | [prompt](flyby.prompt.md) · [spec](flyby.json) | ![Flyby frame](thumbs/flyby.png) |

Generated proof frames, full-resolution PNG sequences and MP4s are in the git-ignored `shots/out/` directory. The contact sheet is deliberately low resolution; inspect the final MP4 for framing and movement.
