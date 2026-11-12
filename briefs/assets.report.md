# Asset discovery implementation report

## Implemented

- Added `asset_search.py` with normalized image, video and model candidate shapes; concurrent Wikimedia Commons, Openverse, NASA and DuckDuckGo queries; source-by-source count/error logs; and a separate download/validation function.
- Added `POST /api/assets/search` and `POST /api/assets/import`. Image imports go to the existing bucket with source/licence metadata. Video imports go to `/footage/` after PyAV duration validation (maximum 60 seconds). GLB imports are checked for the GLB v2 header and stored under `/models3d/`; attribution is in a sidecar file.
- Added `/models3d/` static serving and `GET /api/models3d` for persisted inventory.
- Changed `/api/assets/find` to try the new discovery/import path first and retain the ScrapeGraphAI + DuckDuckGo implementation as a fallback.
- Added kind chips, candidate previews and licence labels to the Assets panel. Imported video candidates join the existing clip list; imported models appear in a 3D models list.

## Verification

- `cd web && npx tsc -b`: passed, no TypeScript errors.
- `node src/video/bench3d/recipe.check.mts`: passed; ended with `recipe.ts OK`.
- `git diff --check`: passed.
- **Not verified:** Python import/syntax, API startup, real search requests, imports, browser preview, or the eight required topics. The prescribed shared Python executable (`C:/Users/naomi/Documents/vscode shenanigans/ManilaHack/.venv/Scripts/python`) failed to start because its configured base interpreter (`C:/Users/naomi/AppData/Local/Python/pythoncore-3.11-64/python.exe`) is unavailable; neither `python` nor `py` is on PATH. Consequently no hit counts or per-topic timings are claimed.

## Known limits / director follow-up

- There is currently no keyless, searchable GLB catalog adapter. Poly Pizza API access appears to require authentication, and the Polyfork discovery endpoint/API behavior was not confirmed. The model search chip therefore returns no results until a provider is added. Manual GLB import/search is not exposed in the panel.
- Imported GLBs are inventoried and served, but are not assignable/rendered on a segment. The task brief made segment rendering conditional on a successful `Stage3D` implementation; this was not attempted or verified.
- Openverse's public audio endpoint is queried for video candidates, but only MP4/WebM file types are accepted; it may return none. NASA and Commons can provide clips when their listings include direct browser-playable files.
- Found images keep their source and licence in metadata; unknown licences remain explicitly labelled. Users should review source terms before using assets in published work.
- Before merging, run the shared Python checks and exercise the search/import routes and browser UI on the director's machine. Test topics requested in `briefs/assets.md`: the epstein files, Manila traffic, jeepney, tower defense game, ube halaya, Mobile Legends, Philippine eagle, and how coffee is made.

## Reproduction commands

```powershell
cd web
npx tsc -b
node src/video/bench3d/recipe.check.mts
cd ..
& 'C:/Users/naomi/Documents/vscode shenanigans/ManilaHack/.venv/Scripts/python.exe' -c "import ast; ast.parse(open('server.py', encoding='utf-8').read()); import asset_search"
$env:BLOCKCUT_PORT = '8792'
& 'C:/Users/naomi/Documents/vscode shenanigans/ManilaHack/.venv/Scripts/python.exe' server.py
```

Then POST `{"query":"jeepney","kinds":["image","video","model"],"limit":8}` to `/api/assets/search`, import one returned candidate through `/api/assets/import`, and verify the resulting URL in the Assets panel and a segment.

No dependencies were added. No new licence terms are introduced by the implementation itself; each asset's provider-supplied licence remains attached to the imported item.
