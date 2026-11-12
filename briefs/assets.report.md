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
- Python syntax and imports passed with the shared venv. The API started on port 8792. A live search/import of a Wikimedia Commons jeepney image succeeded: 3.64 MB JPEG returned HTTP 200, with source, author and CC BY-SA 4.0 metadata retained.
- Live image candidate searches (limit 8): `the epstein files` 8 (8.3 s); `Manila traffic` 8 (8.4 s); `jeepney` 8 (8.4 s); `tower defense game` 8 (8.6 s); `Mobile Legends` 8 (8.4 s); `Philippine eagle` 8 (8.3 s); `how coffee is made` 8 (8.6 s); `ube halaya` 8 on retry (3.3 s). All 8 topics returned at least four candidates. Most of the first seven topic results came from Wikimedia Commons; Epstein also had one ABC News result. The ube retry was split 2 each across Wikimedia Commons, Openverse, DuckDuckGo and NASA after provider interleaving was added. Counts are candidates, not proof every image downloads successfully.
- The first `ube halaya` search exposed a DuckDuckGo edge case (non-HTTPS result became a null candidate and caused HTTP 400); candidate assembly now filters it and the retry returned 8. A broad concurrent all-kinds run hit upstream Wikimedia 429 rate limits and two client-side connection failures.
- Real media imports succeeded: a 3.64 MB Commons jeepney JPEG returned HTTP 200 at `/assets/...` with source/author/CC BY-SA 4.0 metadata; a Commons coffee brewing WebM returned HTTP 200 at `/footage/...`, size 3,868,605 bytes and measured duration 67.06 s (CC BY 3.0, Coffee Circle). Longer clips are accepted because the existing segment UI trims them; the imported clip's browser playback/segment render was not verified. No GLB candidate was found.
- No browser click-through was performed.
- TypeScript build, recipe self-check and `git diff --check` passed as recorded above.

## Known limits / director follow-up

- Model discovery currently accepts GLBs indexed by Wikimedia Commons only. No hits were found in the topic checks. Poly Pizza API access appears to require authentication, and the Polyfork discovery endpoint/API behavior was not confirmed. Manual GLB upload/search is not exposed in the panel.
- Imported GLBs are inventoried and served, but are not assignable/rendered on a segment. The task brief made segment rendering conditional on a successful `Stage3D` implementation; this was not attempted or verified.
- Openverse's public audio endpoint is queried for video candidates, but only MP4/WebM file types are accepted; it may return none. NASA and Commons can provide clips when their listings include direct browser-playable files.
- Found images keep their source and licence in metadata; unknown licences remain explicitly labelled. Users should review source terms before using assets in published work.
- Before merging, exercise the browser UI and verify playback/segment trimming of the imported 67.06 s clip. The eight requested image searches now returned 8 candidates each, including the ube retry.

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
