# Recipe -> GLB with headless Blender. Same shape math as web/src/video/bench3d/manifoldModel.ts.
#   blender -b --factory-startup -P bench3d/modelgen/blender_model.py
# Writes bench3d/out/modelgen/<instance name>.glb (one per instance, at the origin; the scene places them).
import json, math, os, time
import bpy

T0 = time.perf_counter()
HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = json.load(open(os.path.join(HERE, "ube.json")))
R = SPEC["model"]
OUT = os.path.join(os.path.dirname(HERE), "out", "modelgen")


def lin(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c] + [1]


def shape(px, py, pz):  # unit-sphere vertex (y up) -> tuber, identical to the TS version
    s, amt = R["lumps"]["seed"], R["lumps"]["amount"]
    n = (math.sin(3.1 * px + s) * math.sin(2.3 * py + 1.7 * s) * math.sin(2.9 * pz + 2.3 * s)
         + 0.5 * math.sin(6.1 * px + 0.7 * s) * math.sin(5.3 * pz + 1.3 * s))
    k = 1 + amt * n
    prof = R["radius"] * (1 - R["taper"] * px * px) * k
    return px * (R["length"] / 2) * (1 + 0.5 * amt * n), py * prof + R["bend"] * R["radius"] * (px * px - 0.33), pz * prof


def material(name, hexstr):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = lin(hexstr)
    bsdf.inputs["Roughness"].default_value = 0.8
    return m


bpy.ops.wm.read_factory_settings(use_empty=True)
skin, flesh = material("skin", R["skin"]), material("flesh", R["flesh"])
os.makedirs(OUT, exist_ok=True)
built = {}
for inst in SPEC["instances"]:
    t = time.perf_counter()
    bpy.ops.object.select_all(action="DESELECT")
    seg = R["segments"]
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=seg // 2, radius=1)
    ob = bpy.context.object
    ob.name = inst["name"]
    ob.data.materials.append(skin)
    for v in ob.data.vertices:  # Blender is z-up: recipe (x, y, z) = Blender (x, z, -y)
        x, y, z = shape(v.co.x, v.co.z, -v.co.y)
        v.co = (x, -z, y)
    if inst["cut"]:
        bpy.ops.mesh.primitive_cube_add(size=4, location=(0, 0, 2))  # removes recipe y > 0
        cutter = bpy.context.object
        cutter.data.materials.append(flesh)
        mod = ob.modifiers.new("cut", "BOOLEAN")
        mod.operation, mod.solver, mod.object, mod.material_mode = "DIFFERENCE", "EXACT", cutter, "TRANSFER"
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.modifier_apply(modifier="cut")
        bpy.data.objects.remove(cutter)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.shade_flat()
    path = os.path.join(OUT, inst["name"] + ".glb")
    bpy.ops.export_scene.gltf(filepath=path, use_selection=True, export_yup=True)
    built[inst["name"]] = (time.perf_counter() - t) * 1000, len(ob.data.polygons)
    bpy.data.objects.remove(ob)

for k, (ms, faces) in built.items():
    print(f"BUILT {k}: {ms:.1f} ms (incl. GLB export), {faces} faces")
print(f"BUILT total script time {(time.perf_counter() - T0) * 1000:.0f} ms")
