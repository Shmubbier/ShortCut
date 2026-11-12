# Polyfork-first 3D models report

Branch: `codex/polyfork`

## What works

- Generated 3D plans now ask for short Polyfork catalogue nouns (and optional remix words), not full recipes. Catalogue searches run concurrently with a shared 20-second plan deadline and per-request timeouts capped at 8 seconds. Search tries noun prefixes plus a likely class, requests free assets under 5,000 triangles, and ranks title matches above description matches.
- Successful matches download to `web/public/models3d/` and keep a JSON sidecar containing the Polyfork asset ID, source, licence, credit, triangle count, and any remix result. Search results are cached on disk; repeated lookup of `windmill` returned the cached result in 0.00 seconds in the local timing check.
- Misses do not silently generate recipes. The existing image search is attempted, and absent an image the normal 2D/text segment stays in place. Recipe validation/repair is only reached when the request explicitly asks to create/build/make/generate a 3D model (or passes `buildCustomModels`) and Polyfork did not resolve it. Old `prop` plans still render.
- Local GLBs render in the Remotion 3D stage using Three's bundled `GLTFLoader`; the camera auto-fits and grounds the model. Rendering now waits for the GLB load. Models in the Assets panel can be dragged or clicked onto a segment and removed from the inspector.
- `/api/models3d` exposes the saved attribution metadata, `/models3d/` serves the GLB, and export props rewrite local model paths to the active API port.

## Real exercises

API was run on `127.0.0.1:8796`. The three full-plan requests used the allowed maximum of three attempts.

| Topic | API result | Polyfork result / fallback | Lookup measurements |
|---|---|---|---|
| Philippine fruit basket | Claude plan completed in 3D style | Hook: **Banana** (`banana-09c206`, 286 tris); payoff: **Basket of Humitas** (`basket-of-humitas-3cb716`, 772 tris). Other unresolved beats stayed recipe-free and had no image result in this run. | Individual resolutions: 2.62–3.08 s; 4 models resolved. |
| Philippine jeepney and modern buses | Claude plan completed in 3D style | 7 models resolved. Included **Hover City Coupe** (2,582 tris), **Military Cargo Truck** (2,284), **Team Minibus** (2,404), **Campus Shuttle Bus** (2,616), **Bus Tub Trolley** (706), **Fuel Depot** (1,436), and **Parking Garage** (2,229). Two medium-confidence remixes returned `field-olive` and `council-white`. `Parking Garage` and `Fuel Depot` are imperfect semantic matches; review them before presenting those beats as exact jeepney visuals. | Individual resolutions: 2.84–5.02 s; 7 models resolved. |
| Windmill electricity | API returned its offline fallback because Claude Code reported the 5-hour usage limit. I did not make a fourth full-plan call. | Direct catalogue lookup succeeded with **Windmill** (`windmill-3aad49`, 1,842 tris). I attached it to the API fallback plan for the render check; this manual attachment is not evidence that the failed generation resolved it automatically. | Direct lookup: 2.72 s; warm cache: 0.00 s. |

The fruit plan's first scene was rendered with Remotion to `web/out/polyfork.png` at frame 40 and visually inspected. The banana is visible, centered below the title, with a ground shadow. I removed music from the render-only props because this worktree had no `public/music/tropical-ride.wav`; this did not change the plan or renderer. A first still attempt without waiting for the local GLB showed only the title; the load wait fixed that.

**Latency limitation:** the lookup times above are measured, but I did not record a controlled end-to-end generation baseline against the previous recipe prompt. I therefore cannot claim a measured before/after total-generation speedup. The full plan calls themselves remain dependent on Claude availability.

## Forced Codex live test (after the Codex fallback landed on main)

I merged `main` into `codex/polyfork`, then started the isolated API on port 8796 with `BLOCKCUT_AI=codex`. The shared demo API
and UIs on 8787, 5173 and 5175 were not restarted or changed.

The first forced request returned the offline Jeepney sample in 38.88 s. The Codex response was rejected because `_strict()`
was stripping the JSON Schema metadata key `title` even when it was a required property name. I fixed the sanitizer to strip
metadata from schema nodes while preserving every key inside each `properties` map, restarted the isolated server and retried.

| Operation | Result | Time |
|---|---|---:|
| `POST /api/plan`, topic “A woven basket of tropical fruit at a Filipino market”, style 3D, 9:16 | Codex returned a researched seven-scene plan; all seven scenes resolved a Polyfork GLB. The models were Kagaribi Fire Basket (three scenes), Kete Reed Basket, Banana, Fruit tree, and Cordwood Pile. | 47.22 s |
| `POST /api/edit`, whole-plan request to tighten narration/pacing and keep the scene count/models | Codex returned seven scenes and retained the same seven model assignments. | 29.10 s |
| Remotion still, first revised-plan scene | GLB loaded and visibly rendered centered in the 3D stage with shadow. `tropical-ride.wav` was absent in this worktree, so I set `music: null` in a render-only props copy. | succeeded |
| UI/API routing on `:5186` → `:8796` | Vite root returned HTTP 200; `/api/models3d` returned 18 entries through the proxy; the first model URL returned HTTP 200. | succeeded |

This verifies the path when Claude is unavailable: `BLOCKCUT_AI=codex` forced Codex for both initial generation and the follow-up edit,
and generation used Polyfork lookup. Model search is word matching, so the result list is not always semantically exact: for this
fruit-market plan, several scenes reused basket/fire-basket assets and one used a cordwood pile. Review the images before showing
these particular assignments as factual fruit visuals. The seven-segment count and stable model preservation are verified; the
look remains an editor review decision.

## Verification

- `cd web && npx tsc -b` — passed with no output.
- `cd web && node src/video/bench3d/recipe.check.mts` — passed; ended with `recipe.ts OK`.
- Shared-venv AST parse and `import server` — passed.
- After merging the Codex fallback: shared-venv AST parse/import — passed; strict Script schema includes root, direction and scene `title` fields.
- `GET /api/models3d` and `GET /models3d/windmill-3aad49.glb` on port 8796 — metadata returned and GLB returned HTTP 200.
- Remotion still render — passed after adding the GLB load wait; visual inspection confirmed the banana model.
- Forced-Codex plan, follow-up edit, GLB still, and isolated UI/API proxy — passed after fixing `_strict()`.

## Reproduce

From the worktree root in PowerShell:

```powershell
$env:BLOCKCUT_PORT='8796'
$env:BLOCKCUT_AI='codex' # force Codex rather than Claude for the fallback rehearsal
& 'C:/Users/naomi/Documents/vscode shenanigans/ManilaHack/.venv/Scripts/python' server.py
```

In another PowerShell window, request the plans (the captured run used these three topics):

```powershell
$body = @{topic='A fruit basket and the story of Philippine tropical fruit'; style='3d'; pace='punchy'; aspect='9:16'; assets=@()} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8796/api/plan -ContentType 'application/json' -Body $body -TimeoutSec 600
```

Repeat with `topic='The Philippine jeepney and modern city buses'` and `topic='How windmills turn wind into electricity'`. These requests use the signed-in Claude plan when available. Do not make more than three full-plan calls for this task. To render the captured fruit plan, remove `music` from a render-only props copy if the local music file is absent, then run from `web/`:

```powershell
npx remotion still src/video/index.tsx Main out/polyfork.png --frame=40 --props=../fruit-render.json --gl=angle
```

## Merge and licence notes

- Merge the code commit on `codex/polyfork` into `main` normally. No new package or requirements dependency was added.
- `web/public/models3d/` and `.cache/polyfork/` are ignored runtime data and are not in the commit. On a fresh checkout, Polyfork assets download on demand; to make the demo independent of network access, copy selected `.glb` and matching `.glb.json` sidecars into that checkout's ignored `web/public/models3d/`.
- Polyfork's public mesh licence offers CC BY 4.0 with the returned credit line, or Polyfork's licence with no redistribution. Preserve the sidecars and visible credit/source when using the hosted GLBs. The `remix` call is metadata/runtime-param information; the cached GLB remains the returned baked variant where Polyfork supplied one.
- `briefs/polyfork.md` and `HANDOFF.md` are updated on this branch with the Codex verification and the queued HyperFrames study.
