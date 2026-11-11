# Headless Blender render of bench3d/scene.json.
#   blender -b --factory-startup -P bench3d/blender/scene.py -- [cycles|eevee]
# Writes PNGs to bench3d/out/blender_<engine>_frames/ (encode with: npx remotion ffmpeg -framerate 30 -i %04d.png ...).
import json, math, os, sys
import bpy
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = json.load(open(os.path.join(ROOT, "scene.json")))
ENGINE = (sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv[:-1] else "cycles").lower()
OUT = os.path.join(ROOT, "out", f"blender_{ENGINE}_frames")


def lin(hexstr, a=1.0):  # sRGB hex -> linear RGBA (Blender color sockets are linear)
    c = [int(hexstr[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c] + [a]


bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
r = sc.render
r.resolution_x, r.resolution_y, r.fps = S["width"], S["height"], S["fps"]
sc.frame_start, sc.frame_end = 0, S["frames"] - 1
r.image_settings.file_format = "PNG"
r.image_settings.color_mode = "RGB"
r.filepath = OUT + os.sep
sc.view_settings.view_transform = "Standard"  # hex colors come out as hex

if ENGINE == "cycles":
    r.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for backend in ("OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = backend
            prefs.get_devices()
            if any(d.type == backend for d in prefs.devices):
                break
        except TypeError:
            pass
    for d in prefs.devices:
        d.use = d.type != "CPU"
    sc.cycles.device = "GPU"
    sc.cycles.samples = 48
    sc.cycles.use_denoising = True
    print("cycles device:", prefs.compute_device_type, [d.name for d in prefs.devices if d.use])
else:
    r.engine = "BLENDER_EEVEE"
    sc.eevee.taa_render_samples = 32

world = bpy.data.worlds.new("paper")
sc.world = world
world.use_nodes = True
# camera rays see the paper color exactly (strength 1); everything else is lit by it at 0.9
wn = world.node_tree.nodes
bg, lp, mx = wn["Background"], wn.new("ShaderNodeLightPath"), wn.new("ShaderNodeMix")
mx.data_type = "RGBA"
bg.inputs[0].default_value = lin(S["background"])
mx.inputs[6].default_value, mx.inputs[7].default_value = [0.9] * 3 + [1], [1, 1, 1, 1]
world.node_tree.links.new(lp.outputs["Is Camera Ray"], mx.inputs[0])
world.node_tree.links.new(mx.outputs[2], bg.inputs[1])

# models
for m in S["models"]:
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(ROOT, "media", m["file"]))
    for o in set(bpy.data.objects) - before:
        if o.parent is None:
            o.location = Vector((m["position"][0], -m["position"][2], m["position"][1]))  # glTF Y-up -> Blender Z-up
            o.rotation_mode = "XYZ"
            o.rotation_euler[2] += math.radians(m["rotationY"])
            o.scale = [s * m["scale"] for s in o.scale]

# shadow-only ground
bpy.ops.mesh.primitive_plane_add(size=40)
ground = bpy.context.object
ground.is_shadow_catcher = True  # Cycles only
if ENGINE != "cycles":
    # EEVEE has no shadow catcher: read the ground's own lighting (Shader to RGB) and turn "less light" into ink alpha.
    # ponytail: lit/shadow levels measured with DEBUG_GROUND=1 for sun 3.5 + world 0.9; re-measure if the lights change
    gm = bpy.data.materials.new("shadow_only")
    gm.use_nodes = True
    gm.surface_render_method = "BLENDED"
    nt = gm.node_tree
    nt.nodes.clear()
    N = nt.nodes.new
    dif, s2r, bw, mr = N("ShaderNodeBsdfDiffuse"), N("ShaderNodeShaderToRGB"), N("ShaderNodeRGBToBW"), N("ShaderNodeMapRange")
    tr, ink, mix, out = N("ShaderNodeBsdfTransparent"), N("ShaderNodeEmission"), N("ShaderNodeMixShader"), N("ShaderNodeOutputMaterial")
    ink.inputs[0].default_value = lin(S["ink"])
    mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = 0.58, 1.27
    mr.inputs["To Min"].default_value, mr.inputs["To Max"].default_value = S["shadowOpacity"], 0.0
    for a, b in ((dif.outputs[0], s2r.inputs[0]), (s2r.outputs[0], bw.inputs[0]), (bw.outputs[0], mr.inputs[0]),
                 (mr.outputs[0], mix.inputs[0]), (tr.outputs[0], mix.inputs[1]), (ink.outputs[0], mix.inputs[2]), (mix.outputs[0], out.inputs[0])):
        nt.links.new(a, b)
    if os.environ.get("DEBUG_GROUND"):  # write the ground's light level (/4) as its colour, to retune From Min/Max
        dbg = N("ShaderNodeMath"); dbg.operation = "MULTIPLY"; dbg.inputs[1].default_value = 0.25
        nt.links.new(bw.outputs[0], dbg.inputs[0]); e2 = N("ShaderNodeEmission"); nt.links.new(dbg.outputs[0], e2.inputs[0]); nt.links.new(e2.outputs[0], out.inputs[0])
    ground.data.materials.append(gm)

# soft key light
kp = Vector((S["keyLight"]["position"][0], -S["keyLight"]["position"][2], S["keyLight"]["position"][1]))
sun = bpy.data.objects.new("key", bpy.data.lights.new("key", "SUN"))
sun.data.energy = 3.5
sun.data.angle = math.radians(10)
sun.rotation_euler = kp.to_track_quat("Z", "Y").to_euler()
sc.collection.objects.link(sun)

# orbit camera, keyed every frame with the same easing as Remotion's Easing.inOut(Easing.cubic)
C = S["camera"]
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.sensor_fit = "VERTICAL"
cam.data.angle_y = math.radians(C["fovY"])
sc.collection.objects.link(cam)
sc.camera = cam
tgt = Vector((C["target"][0], -C["target"][2], C["target"][1]))
ease = lambda t: 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2
for f in range(S["frames"]):
    a = math.radians(C["orbitFromDeg"] + (C["orbitToDeg"] - C["orbitFromDeg"]) * ease(f / (S["frames"] - 1)))
    cam.location = Vector((tgt.x + C["radius"] * math.sin(a), tgt.y - C["radius"] * math.cos(a), C["height"]))
    cam.rotation_euler = (tgt - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.keyframe_insert("location", frame=f)
    cam.keyframe_insert("rotation_euler", frame=f)

# overlaid title: flat emission text parented to the camera, laid out like the Remotion overlay (px -> camera plane)
D = 1.0
u = 2 * D * math.tan(math.radians(C["fovY"]) / 2) / S["height"]  # world units per pixel at distance D
left, top = -S["width"] / 2 * u + 80 * u, S["height"] / 2 * u - 170 * u
FONTS = "C:/Windows/Fonts/"


def emit(name, hexstr):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    e, o = nt.nodes.new("ShaderNodeEmission"), nt.nodes.new("ShaderNodeOutputMaterial")
    e.inputs[0].default_value = lin(hexstr)
    nt.links.new(e.outputs[0], o.inputs[0])
    return mat


def text(body, font, px, y_px, hexstr, fit=1.0):  # fit: Blender sizes fonts smaller than CSS px (measured per font)
    cu = bpy.data.curves.new(body, "FONT")
    cu.body, cu.font, cu.size, cu.align_y = body, bpy.data.fonts.load(os.path.join(FONTS, font)), px * fit * u, "TOP"
    ob = bpy.data.objects.new(body, cu)
    ob.data.materials.append(emit(body, hexstr))
    ob.visible_shadow = False
    sc.collection.objects.link(ob)
    ob.parent = cam
    ob.location = (left, top - y_px * u, -D)
    return ob


text(S["kicker"], "georgiai.ttf", 40, 0, S["ink"], fit=1.28)
for i, word in enumerate(S["title"].split()):
    text(word, os.path.join(ROOT, "media", S["font"]), 168, 70 + i * 151, S["accent"], fit=1.2)
bpy.ops.mesh.primitive_plane_add(size=1)
rule = bpy.context.object
rule.data.materials.append(emit("rule", S["ink"]))
rule.visible_shadow = False
rule.parent = cam
rule.scale = (260 * u, 10 * u, 1)
rule.location = (left + 130 * u, top - (70 + 2 * 151 + 28 + 5) * u, -D)

os.makedirs(OUT, exist_ok=True)
if os.environ.get("ONLY"):  # test one frame: ONLY=60
    sc.frame_start = sc.frame_end = int(os.environ["ONLY"])
bpy.ops.render.render(animation=True)
