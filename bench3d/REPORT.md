# 3D bake-off: Remotion vs raea vs Blender

**Recommendation: use Remotion with `@remotion/three` (React Three Fiber) for Blockcut's 3D style.** It came out the fastest, it's
the only one that previews live in our editor's `@remotion/player`, and a 3D segment is just one more React component fed by
the same JSON plan, so the editor, timeline and per-segment AI edits keep working unchanged. Blender (Cycles) gives the
best-looking frames, but at 1+ min/frame on this machine it's an offline "hero shot" tool, not an editor
backend. raea's output quality is close to Remotion's and it's quick, but it can't preview in the browser and it's a canary release. Its licence
also restricts competing products, and Blockcut arguably is one (see Licence).

## What was rendered

The same scene in all three engines, driven from one spec: [`scene.json`](scene.json) (1080×1920, 30 fps, 120 frames = 4 s).
It has a paper background `#f3ece0` and two polyfork low-poly GLBs (taro plant + basket of produce). The camera does a 70° orbit
with `Easing.inOut(Easing.cubic)` (the same curve in every engine). There's one soft sun key light with shadows on a shadow-only ground,
so the paper stays exactly `#f3ece0`. "UBE SEASON" is overlaid in Archivo Black (OFL, `media/fonts/`) in `#e8432e`, with a
Georgia italic kicker and an ink rule.

| Output | |
|---|---|
| [`out/remotion.mp4`](out/remotion.mp4) | Remotion 4.0.542 + `@remotion/three`, headless Chrome `--gl=angle` |
| [`out/raea.mp4`](out/raea.mp4) | raea 0.1.1-rc4 (Bevy 0.20) |
| [`out/blender_eevee.mp4`](out/blender_eevee.mp4) | Blender 5.3.0 EEVEE, headless |
| `out/blender_cycles_frames/0060.png` | Blender 5.3.0 Cycles, **one frame only**: fell back to CPU, see below |
| [`out/compare.mp4`](out/compare.mp4) | the three MP4s side by side (1620×1016) |
| [`out/contact_sheet.png`](out/contact_sheet.png) | frames 0 / 60 / 119 per engine, plus the Cycles frame |

**Blender Cycles failed on the GPU**, with this exact log line:
`WARNING OptiX initialization failed because the installed NVIDIA driver is too old. Please update to the latest driver first!`
The installed driver is 566.36. CUDA wasn't picked up either, so Cycles silently rendered on the CPU at 40–75 s/frame (about 2 h for 4 s). I
stopped it after 34 frames, kept one corrected frame (f60, 65 s) for the quality comparison, and rendered the timed Blender
video with EEVEE instead. Updating the NVIDIA driver should bring OptiX back; I didn't do that, since it's a system change for you to make.

## Comparison

Times are wall clock on this laptop (RTX 4070 Laptop, Windows 11), from command start to MP4 on disk, and include each tool's startup.

| | **Remotion + @remotion/three** | **raea 0.1.1-rc4** | **Blender 5.3 (headless)** |
|---|---|---|---|
| Render time, 4 s | **17.9 s** (incl. webpack bundle; 4 tabs) | 24.5–28.1 s (30 ms/frame; the rest is startup + openh264 encode) | EEVEE **73.6 s** + ~3 s encode. Cycles: ~65 s *per frame* on CPU (GPU blocked by driver) |
| Lighting | three.js PBR, hemisphere + sun. Flat-ish but clean; matches our 2D style well | Bevy PBR, nicely graded, slightly more contrast | EEVEE: soft, a little washed. Cycles: clearly best (bounce light, contact shadows) |
| Shadows | PCF soft shadow map, crisp and stable (2048²) | PCSS soft shadows; a faint grain at 1:1, and a visible edge on the shadow-catcher plane at the frame bottom | EEVEE: soft but faint (EEVEE has no shadow catcher; mine is a Shader-to-RGB workaround with measured levels). Cycles: real shadow catcher, best |
| Anti-aliasing | MSAA via WebGL; clean edges | MSAA 4× default; clean | EEVEE 32 TAA samples / Cycles 48 spp + denoise; best |
| Driving it from our JSON plan | **Trivial.** Same process, same props, same `calculateMetadata` as `Main`; the 3D segment is a React component | Easy to write (Remotion-like API: `Composition`, `interpolate`, `Easing`), but plan data has to be imported into the TSX. Its sandbox refuses imports from outside the project folder (it refused `../scene.json`). No documented props flag (`--input` looks like it's for game input) | Python reads the JSON fine, but text layout isn't CSS: font sizes needed per-font fudge factors (1.2×, 1.28×) and a camera-parented text rig. Every edit means a full re-render in a separate 1 GB binary |
| Live in-browser preview (`@remotion/player`) | **Yes**: it's a normal composition, so it previews and scrubs in the editor today | **No.** Previews are its own native window (`raea play`) or rendered stills. It ships an `@raea/r3f` package (FSL) that claims to draw raea scenes inside R3F/three.js; not tested | **No.** Offline renders only |
| Windows stability | Solid. One gotcha: set `castShadow` at clone time, not in `useEffect` (an effect runs after the frame is captured, so shadows were missing) | Rendered fine once working. The installer **exits 1** on a fresh machine (an `Select-String` bug when no old `raea-bevy` skill exists), though the install itself succeeded. Undocumented API details (shadow-catcher alpha needs `Srgba.hex("#rrggbbaa")` + `alpha_mode="Blend"`) | EEVEE solid. Cycles GPU needs a newer NVIDIA driver than 566.36, and falls back to CPU with only a warning |
| Install size / effort | `npm i @remotion/three three @react-three/fiber @react-three/drei` = ~30 MB of packages, one command, nothing outside the repo | 267 MB download → **779 MB** in `~/.raea`; adds itself to user PATH and writes a skill to `~/.claude/skills/raea`. One PowerShell one-liner | 425 MB zip → **962 MB** portable folder (`bench3d/tools/`); no installer needed |
| Licence | Remotion: free for individuals and companies of ≤3 people, company licence above that (already our dependency). three / R3F / drei: MIT | **FSL-1.1-ALv2**: you may use it, *except* for a product that competes with raea; each version becomes Apache-2.0 after 2 years. raea is an AI "describe it, we render it" video engine, so Blockcut is close to that line | GPL-3.0 for Blender itself; renders you make are yours, without restriction |
| Output file | H.264 via Remotion, 1.7 MB | H.264 Constrained Baseline (openh264) 4.9 MB, larger. raea recommends re-encoding a share copy | Our encode (libx264 crf 18), 0.8 MB |

### Assets: polyfork terms (what I found)

polyfork.dev serves direct GLBs at `https://polyfork.dev/cdn/<asset-id>.glb`. The listing just says "GLB + ES module, commercial
license" and "Every low poly model is free", but each asset page embeds the actual licence text. The **mesh files** are offered
under your choice of:
1. **CC BY 4.0**: commercial use OK; credit "*Name* by Polyfork (asset URL), CC BY 4.0" and say if you changed it; or
2. **the Polyfork licence**: commercial use OK and no credit needed, but no redistributing the files as assets, and no using them
   to build or train a *commercial* 3D-asset generator.

The ES modules (`.mjs`) are Polyfork-licence only. Full terms: https://polyfork.dev/licensing. Used here:
[taro-plant-8c0493](https://polyfork.dev/asset/taro-plant-8c0493) and
[basket-of-produce-7420cf](https://polyfork.dev/asset/basket-of-produce-7420cf). For Blockcut, CC BY with a credit line in
the video description is the safe pick, since the editor ships the GLBs in its bundle (which the Polyfork licence wouldn't allow).

## Why Remotion, and what to keep from the others

- **The preview is the deciding factor.** Our editor is built around `@remotion/player`: scrubbing, per-segment edits, instant
  feedback. Only Remotion keeps that for 3D. raea and Blender both turn every AI edit into a render-and-wait step.
- **It was also the fastest end to end** here (17.9 s vs 28 s vs 74 s), and it adds about 30 MB of npm packages versus roughly 1 GB for the others.
- **The look fits.** A flat-ish, crisp three.js render with a shadow-only floor over the paper background, plus CSS type on top,
  reads as the same editorial style as our 2D segments. The title is the same DOM text as everywhere else in the app.
- **Blender Cycles is the quality ceiling.** If we ever want a "render final in high quality" button, the Blender script here
  already takes the same `scene.json`. It needs the NVIDIA driver update first, and it should run as a background job.
- **raea is promising but not for this weekend.** It's a canary build with an installer bug on Windows, has no browser preview, and its FSL "competing
  product" clause is a real risk for an AI video editor.

## Reproduce

```bash
# Remotion (from web/; GLBs + font are copied into web/public/bench3d/)
npx remotion render src/video/bench3d/index.tsx Bench3D ../bench3d/out/remotion.mp4 --gl=angle --concurrency=4
# raea (from bench3d/; it only reads files inside this folder)
raea render raea.tsx -o out/raea.mp4
# Blender (from bench3d/): eevee or cycles; ONLY=60 renders one frame, DEBUG_GROUND=1 shows the ground's light levels
tools/blender-5.3.0-windows-x64/blender.exe -b --factory-startup -P blender/scene.py -- eevee
npx remotion ffmpeg -framerate 30 -i ../bench3d/out/blender_eevee_frames/%04d.png -c:v libx264 -crf 18 -pix_fmt yuv420p ../bench3d/out/blender_eevee.mp4   # from web/
# Side by side + contact sheet (from web/)
npx remotion render src/video/bench3d/index.tsx Compare ../bench3d/out/compare.mp4 --public-dir ../bench3d
npx remotion still  src/video/bench3d/index.tsx Sheet   ../bench3d/out/contact_sheet.png --public-dir ../bench3d
```

Files: [`scene.json`](scene.json) (shared spec), [`raea.tsx`](raea.tsx), [`blender/scene.py`](blender/scene.py),
[`../web/src/video/bench3d/`](../web/src/video/bench3d/) (`Bench3D.tsx`, `Compare.tsx`, separate `index.tsx` entry), `media/` (GLBs, font).
`tools/` (Blender, 962 MB) and the PNG frame folders under `out/` can be deleted once you're done.

### Changes outside `bench3d/`
- `web/package.json`: added `@remotion/three@4.0.542`, `three`, `@react-three/fiber`, `@react-three/drei`, `@types/three`, `manifold-3d@3.5.4`.
- `web/public/bench3d/`: copies of the two GLBs, the font, `manifold.wasm` and the Blender-made `gen/*.glb` (for `staticFile`).
- `web/src/video/bench3d/`: new folder. `Video.tsx`, `App.tsx`, `Canvas.tsx` and the main `index.tsx` are untouched.
- raea installer: `~/.raea` (779 MB), a user PATH entry, `~/.claude/skills/raea`.

## Follow-up: generating models from a recipe (Manifold vs Blender)

Remotion only plays back finished models, so the question was what can *make* them from an AI-written description, fast enough
to live inside the app. Both tools built the same low-poly ube (one whole, one cut in half to show the flesh) from one JSON recipe,
[`modelgen/ube.json`](modelgen/ube.json): length, radius, taper, bend, seeded lumps, skin and flesh colours. That's the kind of JSON
Claude would write from a prompt. Both interpreters use the same deterministic lump formula, so the shapes match.

| | **Manifold** (`manifold-3d` 3.5.4, WASM) | **Blender 5.3** (headless → GLB) |
|---|---|---|
| Where it runs | Inside the page / Remotion render, no file step | Separate process, writes `.glb` that Remotion then loads |
| Time to build both models | **1–2 ms warm, 6–7 ms cold** (Node); 14–30 ms inside the headless-Chrome render; wasm loads in 7 ms | **~210 ms** of script time; **0.9 s wall warm, 2.8 s cold** (Blender startup) |
| Result | 678 triangles, cut face automatically coloured as flesh (Manifold tracks which input each face came from) | 597 faces (quads + tris); cut face coloured via the boolean modifier's material transfer |
| Bundle cost | ~2.8 MB npm package (~1 MB wasm), Apache-2.0 | 962 MB binary on the server, GPL (the output is yours) |
| Gotchas | Webpack can't bundle its Node-only loader branch: stubbed in [`remotion.config.ts`](../web/src/video/bench3d/remotion.config.ts) (pass `--config=…`). Set `shadowSide: FrontSide` on its materials or shadows come out as rings | Blender's glTF exporter makes materials double-sided by default (it hid the shadow issue) |
| Live preview in `@remotion/player` | **Yes**: rebuilds in milliseconds when the recipe changes | Only after a server round-trip of about 1 s per edit |

Outputs: [`out/modelgen_manifold.mp4`](out/modelgen_manifold.mp4), [`out/modelgen_blender.mp4`](out/modelgen_blender.mp4),
side by side in [`out/modelgen_compare.mp4`](out/modelgen_compare.mp4) / [`out/modelgen_compare_f60.png`](out/modelgen_compare_f60.png).
They look almost identical.

**Verdict:** use Manifold for generated props in Blockcut. Claude writes a JSON recipe, a small interpreter
([`manifoldModel.ts`](../web/src/video/bench3d/manifoldModel.ts), about 40 lines) builds it in the browser, and it previews live.
Keep Blender as an optional server-side tool for things Manifold's toolkit can't do well (sculpted or organic detail, rigging, simulations).
The recipe format here is a single shape family. A real version needs a small op vocabulary (revolve, extrude, boolean, warp,
array, colour) so Claude can describe arbitrary low-poly props.

Reproduce (from `web/`): `npx remotion render src/video/bench3d/index.tsx ModelgenManifold ../bench3d/out/modelgen_manifold.mp4 --gl=angle --config=src/video/bench3d/remotion.config.ts`;
Blender GLBs: `../bench3d/tools/blender-5.3.0-windows-x64/blender.exe -b --factory-startup -P ../bench3d/modelgen/blender_model.py`, then copy
`bench3d/out/modelgen/*.glb` to `web/public/bench3d/gen/`.

## Follow-up: an op vocabulary for any prop

The single-shape recipe became a general one: a JSON node tree built by
[`recipe.ts`](../web/src/video/bench3d/recipe.ts) with Manifold. The vocabulary, written as prompt text for Claude, is
[`modelgen/VOCAB.md`](modelgen/VOCAB.md):
- **Shapes:** `box`, `sphere`, `cylinder` (and cones), `capsule`, `revolve`, `extrude`.
- **Operations:** `union`, `subtract`, `intersect`, `hull`, `mirror`, `array`, `warp`, `ref`.
- **On every node:** `at` / `rot` / `scale` / `color`.

Colours survive booleans: a cut face takes the cutter's colour.

It treats the recipe as untrusted input. Unknown ops, bad numbers and colours, and over-limit sizes (600 nodes, 64 segments, 32 copies, depth 24,
±50 m) throw a `RecipeError` naming the exact node, e.g. `root.children[1].op: unknown op "cone"; use one of …`. That way a bad recipe
can go back to Claude to fix. Self-check: `node src/video/bench3d/recipe.check.mts` (from `web/`).

**Practice prop:** [`modelgen/props/boar_rider.json`](modelgen/props/boar_rider.json) is an *original* low-poly boar rider in a
salakot hat with a pennant. It was written by hand in the vocabulary, the way Claude would write it. (Not the Clash Royale Hog Rider: that's
Supercell's character design, so I didn't copy it.) It's 66 nodes and builds to 3,826 triangles in 16 colours in **55–80 ms**.
The saddle blanket follows the boar's back (an `intersect` of a slightly larger body shell and a box), the nostrils are cut
holes, and both sides of the boar come from one `mirror`. Video: [`out/prop_rider.mp4`](out/prop_rider.mp4) (rendered in 14.9 s);
stills: `out/prop_rider_f0.png`, `_f60.png`, `_f119.png`.

**Fan-art prop:** [`modelgen/props/hog_rider_fanart.json`](modelgen/props/hog_rider_fanart.json) is a low-poly fan-art take on
Clash Royale's Hog Rider, built from primitives with no Supercell assets. It has the mohawk fin, handlebar mustache, shouting mouth, gold wristbands,
raised mallet and a big tusked peach hog. It's 73 nodes, 4,596 triangles and 17 colours, built in about 45 ms. Video: [`out/prop_hogrider.mp4`](out/prop_hogrider.mp4)
(rendered in 11.3 s); stills: `out/prop_hogrider_f0.png`, `_f60.png`, `_f119.png`. The frame carries a
"Fan art · not affiliated with Supercell" line (the recipe's `credit` field). **Check Supercell's Fan Content Policy before
using it anywhere commercial**, such as a Blockcut demo, ad or store page; it limits commercial use of fan content. The original boar rider is the safe
choice for anything promotional.

**Animation (joints + motion):** recipes can now mark nodes as `joint`s (a pivot, plus a looping rotation or bob with a phase), and a
top-level `motion` sets the cycle length and travel speed. The interpreter builds each joint as its own mesh in a nested tree.
The renderer poses it from the frame number, so renders are deterministic and the preview scrubs. Travelling props get a
ground-strip recipe ([`props/ground_strip.json`](modelgen/props/ground_strip.json)) and a camera plus key light that follow them,
since the shadow map only covers ±3 m. The Hog Rider now **gallops forward**: four legs in rotary-gallop order, body pitch and
bob, the rider rocking a beat behind, the mallet arm pumping and the tail flicking, at 0.5 s per stride and 2.6 m/s. That's 9 pieces, 4,342 triangles,
built in about 35 ms. Video: [`out/prop_hogrider_gallop.mp4`](out/prop_hogrider_gallop.mp4) (rendered in 17.3 s). The self-check covers
joint splitting, nesting, the placement rules and the pose maths.

Not done yet: wiring `VOCAB.md` into the server's Claude prompt (that's `server.py`, which another session owns), and a
recipe → GLB export for when Blender-side or offline use needs a file (three.js `GLTFExporter` covers it).
