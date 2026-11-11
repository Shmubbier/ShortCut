# Prop recipe vocabulary (for Claude's prompt)

Write a 3D prop as JSON. It's built with Manifold in the browser (`web/src/video/bench3d/recipe.ts`) and drawn low-poly with flat
shading in the paper style. **Units are metres, y is up, the ground is y = 0, the camera looks from +z, angles are degrees.**

```json
{ "name": "lantern", "title": "PAROL NIGHT",
  "parts": { "spoke": { "op": "capsule", "r": 0.02, "from": [0, 0, 0], "to": [0, 0.3, 0] } },
  "root": { "op": "union", "children": [ ... ] } }
```

## Every node may have
| field | meaning |
|---|---|
| `at` | `[x, y, z]` move (applied last) |
| `rot` | `[x, y, z]` rotation in degrees (applied after scale) |
| `scale` | number or `[x, y, z]` (applied first): squash a sphere into an egg, a body, a leaf |
| `color` | `"#rrggbb"`; children inherit it, and a child's own colour wins. Colours survive booleans: a cut face takes the cutter's colour |

## Shapes
| op | fields | notes |
|---|---|---|
| `box` | `size: [x, y, z]` | centred |
| `sphere` | `r`, `seg?` | centred. `seg` is roundness (default 20, max 64); 8–12 looks chunky low-poly |
| `cylinder` | `r`, `h`, `r2?`, `seg?` | stands along y, centred. `r2` is the top radius: `0` gives a cone, smaller gives a taper |
| `capsule` | `r`, `from: [x,y,z]`, `to: [x,y,z]`, `seg?` | rounded rod between two points: limbs, handles, horns, tails |
| `revolve` | `profile: [[radius, height], ...]`, `seg?` | spins an outline around the y axis: hats, vases, torsos, bottles, bells. Points go counter-clockwise; radius ≥ 0 |
| `extrude` | `points: [[x, y], ...]`, `h` | flat outline in the x-y plane, `h` thick along z, centred: flags, blades, signs, leaves, letters |

## Operations (take `children`)
| op | fields | does |
|---|---|---|
| `union` | `children` | joins parts (also just a group, to move or colour them together) |
| `subtract` | `children` | first child minus all the others: holes, nostrils, eye sockets, bites, cut halves |
| `intersect` | `children` | only where all overlap: rounded boxes (box ∩ sphere), lenses |
| `hull` | `children` | shrink-wrap around the children, **one colour**: smooth blobby bodies, rocks, snouts |
| `mirror` | `axis`, `children` | children plus their mirror across the plane through the origin facing `axis`. Build the +z side of a symmetric creature once, then `"axis": "z"` |
| `array` | `count`, `step: [x,y,z]`, `stepRot?: [x,y,z]`, `children` | repeats: fence posts, spines, teeth, petals (`stepRot` about the origin) |
| `warp` | `amount` (0–0.5), `seed`, `children` | seeded organic lumps. Build the part centred on the origin, warp it, then move the warp node with `at` |
| `ref` | `part` | reuse `parts[part]` |

## Moving parts (joints + motion)
Mark any node with `joint` to make it a separate piece that moves: a leg, an arm, a tail, a wheel. Joints nest: a joint
inside a joint moves with it, like a hand on an arm. Give the recipe a top-level `"motion": { "cycle": 0.5, "travel": [2.6, 0, 0] }`:
`cycle` is seconds per loop, and `travel` is metres per second the whole prop moves. A travelling prop gets a ground strip, and
the camera follows it.

| `joint` field | meaning |
|---|---|
| `name` | unique, letters/digits/_ |
| `pivot` | `[x, y, z]` where it turns, in rest-pose coordinates (a hip, a shoulder, the base of a tail) |
| `rot` | `[x, y, z]` swing in degrees: the piece rotates ±this much around the pivot each cycle |
| `at` | `[x, y, z]` bob in metres, ±this much each cycle |
| `phase` | 0–1, where in the cycle it starts. Offset legs for a gait: gallop hind 0 / 0.1, front 0.45 / 0.55; walk 0 / 0.25 / 0.5 / 0.75 |
| `speed` | loops per cycle (default 1); 2 for a tail flicking twice per stride |

Motion is `amplitude × sin(2π(speed·t/cycle + phase))`, so it loops cleanly. Rules: a joint can't sit inside
`mirror`, `array`, `hull`, `subtract`, `intersect`, `warp`, or under a node with `at`/`rot`/`scale`. Put it in a plain `union`
(or another joint). The joint node itself may have `at`/`rot`/`scale`. For four legs, write them out one by one instead of mirroring them.
Example: [`props/hog_rider_fanart.json`](props/hog_rider_fanart.json) (body, 4 legs, tail, rider, mallet arm).

## How to build well
- Block out big masses first (body, head), then features. Stay within about 150 nodes; low-poly reads better than detail.
- Make creatures and characters symmetric with `mirror` on `z` (they face +x), and give them 6–10 flat colours with one accent.
- Rest the prop on y = 0: feet, hooves and bases touch the ground, and nothing floats.
- Overlap the parts you join by a few centimetres, so the union looks solid.
- Errors name the bad node, e.g. `root.children[3].op: unknown op "cone"; use one of ...`. Fix that node and resend.

Limits: 600 nodes, `seg` ≤ 64, `count` ≤ 32, nesting ≤ 24, every number within ±50 m.
Example: [`props/boar_rider.json`](props/boar_rider.json).
