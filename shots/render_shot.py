"""Render a shot spec using Blender 5.x: blender -b -P shots/render_shot.py -- spec.json out/ --proof|--final"""
import json, math, os, sys, time, subprocess
from pathlib import Path
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
args = sys.argv[sys.argv.index("--") + 1:]
if len(args) != 3 or args[2] not in ("--proof", "--final"):
    raise SystemExit("usage: render_shot.py <spec.json> <out-dir> --proof|--final")
spec_path = Path(args[0]); spec_path = spec_path if spec_path.is_absolute() else ROOT / spec_path
out = Path(args[1]); out = out if out.is_absolute() else ROOT / out
mode = args[2][2:]
S = json.loads(spec_path.read_text(encoding="utf-8"))
fps, duration = int(S["fps"]), float(S["duration"])
frames = round(fps * duration)
W, H = map(int, S["resolution"])

def color(h):
    vals = [int(h[i:i+2], 16)/255 for i in (1,3,5)]
    return [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in vals] + [1]

def ease(name, x):
    x = max(0., min(1., x))
    if name == "easeInOutCubic": return 4*x**3 if x < .5 else 1-(-2*x+2)**3/2
    if name == "easeOutBack": return 1+2.70158*(x-1)**3+1.70158*(x-1)**2
    if name == "easeInExpo": return 0 if x == 0 else 2**(10*x-10)
    return x

def at(keys, t):
    if t <= keys[0]["t"]: return keys[0]
    for a,b in zip(keys, keys[1:]):
        if t <= b["t"]:
            q = ease(a.get("easing", "linear"), (t-a["t"])/(b["t"]-a["t"]))
            result = {}
            for k in a:
                if k in ("t", "easing"): continue
                if k not in b: result[k] = a[k]
                elif isinstance(a[k], list): result[k] = [x+(y-x)*q for x,y in zip(a[k],b[k])]
                elif isinstance(a[k], (int,float)): result[k] = a[k]+(b[k]-a[k])*q
                else: result[k] = a[k]
            return result
    return keys[-1]

bpy.ops.wm.read_factory_settings(use_empty=True)
sc=bpy.context.scene; sc.render.engine="BLENDER_EEVEE"
sc.render.resolution_x=W; sc.render.resolution_y=H; sc.render.resolution_percentage=25 if mode=="proof" else 100
sc.render.fps=fps; sc.render.image_settings.file_format="PNG"; sc.render.image_settings.color_mode="RGB"
sc.render.film_transparent=False; sc.view_settings.view_transform="Standard"
sc.world=bpy.data.worlds.new("paper"); sc.world.use_nodes=True
sc.world.node_tree.nodes["Background"].inputs[0].default_value=color(S.get("background", "#f3ece0"))
sc.world.node_tree.nodes["Background"].inputs[1].default_value=.8
cam_data=bpy.data.cameras.new("Shot Camera"); cam=bpy.data.objects.new("Shot Camera",cam_data); sc.collection.objects.link(cam); sc.camera=cam
for obj in S.get("objects",[]):
    if "glb" in obj:
        before=set(bpy.data.objects); p=ROOT/obj["glb"]
        bpy.ops.import_scene.gltf(filepath=str(p))
        imported=[o for o in set(bpy.data.objects)-before]
        root=bpy.data.objects.new(obj["name"],None); sc.collection.objects.link(root)
        for ob in imported:
            if ob.parent is None: ob.parent=root
        root.location=obj.get("position",[0,0,0]); root.scale=(obj.get("scale",1),)*3 if isinstance(obj.get("scale",1),(float,int)) else obj["scale"]
        root.rotation_euler=[math.radians(v) for v in obj.get("rotation",[0,0,0])]; ob=root
    else:
        prim=obj.get("primitive","icosphere")
        if prim=="cube": bpy.ops.mesh.primitive_cube_add(size=1)
        elif prim=="sphere": bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12)
        elif prim=="cylinder": bpy.ops.mesh.primitive_cylinder_add(vertices=12)
        else: bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2)
        ob=bpy.context.object; ob.name=obj["name"]; ob.location=obj.get("position",[0,0,0]); ob.scale=obj.get("scale",[1,1,1])
        mat=bpy.data.materials.new(obj["name"]+" material"); mat.diffuse_color=color(obj.get("color","#d49a58")); ob.data.materials.append(mat)
    if "keyframes" in obj: ob["shot_keyframes"]=json.dumps(obj["keyframes"])

# Matte paper plane receives the object shadow and gives the product its ground contact.
bpy.ops.mesh.primitive_plane_add(size=200, location=(0,0,-1.15))
ground=bpy.context.object; ground.name="Paper ground"
gm=bpy.data.materials.new("Paper"); gm.diffuse_color=color(S.get("background","#f3ece0")); ground.data.materials.append(gm)
for l in S.get("lights",[{"position":[-4,-5,8],"energy":1100,"size":5}]):
    d=bpy.data.lights.new("Softbox","AREA"); d.energy=l.get("energy",1100); d.shape="DISK"; d.size=l.get("size",5)
    o=bpy.data.objects.new("Softbox",d); sc.collection.objects.link(o); o.location=l.get("position",[-4,-5,8]); o.rotation_euler=(Vector((0,0,0))-o.location).to_track_quat("-Z","Y").to_euler()

# Camera-facing titles use a flat emission shader, with visibility controlled per sampled frame.
def emission(hexcolor):
    m=bpy.data.materials.new("Overlay ink"); m.use_nodes=True; n=m.node_tree.nodes; n.clear(); e=n.new("ShaderNodeEmission"); e.inputs[0].default_value=color(hexcolor); o=n.new("ShaderNodeOutputMaterial"); m.node_tree.links.new(e.outputs[0],o.inputs[0]); return m
for item in S.get("text",[]):
    cu=bpy.data.curves.new("Overlay","FONT"); cu.body=item["body"]; cu.size=item.get("size",.55); cu.extrude=0
    ob=bpy.data.objects.new("Overlay: "+item["body"],cu); sc.collection.objects.link(ob); ob.parent=cam
    ob.location=((item.get("position",[.08,.15])[0]-.5)*1.2,(.5-item.get("position",[.08,.15])[1])*0.68,-2)
    ob.data.materials.append(emission(item.get("color","#332a24")))

out.mkdir(parents=True,exist_ok=True); frame_dir=out/("proof_frames" if mode=="proof" else "frames"); frame_dir.mkdir(exist_ok=True)
sample_frames=sorted(set(round(i*(frames-1)/5) for i in range(6))) if mode=="proof" else range(frames)
start=time.perf_counter()
for f in sample_frames:
    t=f/fps; c=at(S["camera"]["keyframes"],t)
    cam.location=c["position"]; cam.rotation_euler=(Vector(c["look_at"])-cam.location).to_track_quat("-Z","Y").to_euler(); cam.data.lens=35; cam.data.angle=math.radians(c.get("fov",42))
    for ob in [o for o in sc.objects if "shot_keyframes" in o]:
        keys=json.loads(ob["shot_keyframes"]); v=at(keys,t)
        for prop in ("position","rotation","scale"):
            if prop in v:
                attr={"position":"location","rotation":"rotation_euler","scale":"scale"}[prop]
                setattr(ob,attr,[math.radians(x) for x in v[prop]] if prop=="rotation" else v[prop])
    for textobj,item in zip([o for o in sc.objects if o.name.startswith("Overlay:")],S.get("text",[])):
        textobj.hide_render=not (item.get("in",0)<=t<item.get("out",duration))
    sc.render.filepath=str(frame_dir/f"{f:05d}.png"); bpy.ops.render.render(write_still=True)
elapsed=time.perf_counter()-start
if mode=="proof":
    sheet=out/"proof.png"
    js="const sharp=require('sharp'),fs=require('fs'),path=require('path'); const d=process.argv[1],out=process.argv[2],files=fs.readdirSync(d).filter(x=>x.endsWith('.png')).sort(); (async()=>{const m=await sharp(path.join(d,files[0])).metadata(),w=m.width,h=m.height; await sharp({create:{width:w*3,height:h*2,channels:3,background:'#ffffff'}}).composite(await Promise.all(files.map(async(f,i)=>({input:await sharp(path.join(d,f)).png().toBuffer(),left:(i%3)*w,top:Math.floor(i/3)*h})))).png().toFile(out)})().catch(e=>{console.error(e);process.exit(1)})"
    result=subprocess.run(["node","-e",js,str(frame_dir),str(sheet)],cwd=str(ROOT/"web"),capture_output=True,text=True)
    if result.returncode: raise RuntimeError("sharp contact sheet failed: "+result.stderr)
    (out/"proof-times.txt").write_text("\n".join(f"frame {f}: {f/fps:.3f}s" for f in sample_frames),encoding="utf-8")
    print("Proof frames:",[(f,round(f/fps,3)) for f in sample_frames]); print("Proof seconds:",round(elapsed,2),"contact sheet:",sheet)
else:
    movie=out/(spec_path.stem+".mp4")
    ffmpeg=ROOT/"web"/"node_modules"/"@remotion"/"compositor-win32-x64-msvc"/"ffmpeg.exe"
    encoder=subprocess.run([str(ffmpeg),"-y","-framerate",str(fps),"-i",str(frame_dir/"%05d.png"),"-c:v","libx264","-pix_fmt","yuv420p",str(movie)],cwd=str(ROOT/"web"),capture_output=True,text=True)
    if encoder.returncode: raise RuntimeError("Remotion FFmpeg encode failed: "+encoder.stderr[-3000:])
    print("Final rendered",len(list(sample_frames)),"frames in",round(elapsed,2),"seconds; encoded",movie,"bytes",movie.stat().st_size)
