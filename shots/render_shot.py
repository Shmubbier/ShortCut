"""Render shots: blender -b -P shots/render_shot.py -- spec.json out/ --proof|--final [--aspect 9:16] [--draft|--force]"""
import hashlib, json, math, os, subprocess, sys, time
from pathlib import Path
import bpy
from mathutils import Vector
sys.path.insert(0, str(Path(__file__).resolve().parent))
from proof_checks import check_frame

ROOT = Path(__file__).resolve().parents[1]
args = sys.argv[sys.argv.index("--") + 1:]
if len(args) < 3 or args[2] not in ("--proof", "--final"):
    raise SystemExit("usage: render_shot.py <spec.json> <out-dir> --proof|--final [--aspect 9:16] [--draft|--force]")
spec_path = Path(args[0]); spec_path = spec_path if spec_path.is_absolute() else ROOT / spec_path
out = Path(args[1]); out = out if out.is_absolute() else ROOT / out
mode = args[2][2:]
aspect = None; draft = "--draft" in args; force = "--force" in args
if "--aspect" in args:
    aspect = args[args.index("--aspect") + 1]
ASPECTS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350)}
if aspect and aspect not in ASPECTS:
    raise SystemExit("aspect must be 9:16, 16:9, 1:1, or 4:5")
S = json.loads(spec_path.read_text(encoding="utf-8"))
if aspect:
    W, H = ASPECTS[aspect]
else:
    W, H = map(int, S["resolution"])
effective_aspect = aspect or (f"{W}:{H}")
if draft and mode == "final":
    W, H = W // 2, H // 2
fps, duration = int(S.get("fps", 30)), float(S["duration"])
frames = round(fps * duration)
proof_hash = hashlib.sha256(spec_path.read_bytes()).hexdigest()
proof_file = out / "proof.json"
if mode == "final" and not force:
    if not proof_file.is_file():
        raise SystemExit("Final blocked: no proof.json found; run --proof first or pass --force")
    saved = json.loads(proof_file.read_text(encoding="utf-8"))
    if not saved.get("passed") or saved.get("spec_sha256") != proof_hash or saved.get("aspect") != effective_aspect or saved.get("resolution") != [W, H]:
        raise SystemExit("Final blocked: the matching proof failed or is stale; fix the spec and rerun --proof, or pass --force")

def lin(hexstr, alpha=1):
    vals = [int(hexstr[i:i+2], 16)/255 for i in (1,3,5)]
    return [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in vals] + [alpha]

def rgb(hexstr): return [int(hexstr[i:i+2], 16)/255 for i in (1,3,5)]

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
sc.render.resolution_x=W; sc.render.resolution_y=H
sc.render.resolution_percentage=25 if mode=="proof" else 50 if draft else 100
sc.render.fps=fps; sc.render.image_settings.file_format="PNG"; sc.render.image_settings.color_mode="RGB"
sc.render.film_transparent=False; sc.view_settings.view_transform="Standard"
paper=S.get("background", "#f3ece0")
sc.world=bpy.data.worlds.new("paper"); sc.world.use_nodes=True
world_nodes=sc.world.node_tree.nodes; world_links=sc.world.node_tree.links
bg=world_nodes["Background"]; bg.inputs[0].default_value=lin(paper); bg.inputs[1].default_value=1
path=world_nodes.new("ShaderNodeLightPath"); mix=world_nodes.new("ShaderNodeMix"); mix.data_type="RGBA"
mix.inputs[6].default_value=[.9,.9,.9,1]; mix.inputs[7].default_value=[1,1,1,1]
# Camera rays must retain the exact sRGB paper color; the catcher handles the floor shadow separately.

cam_data=bpy.data.cameras.new("Shot Camera"); cam=bpy.data.objects.new("Shot Camera",cam_data); sc.collection.objects.link(cam); sc.camera=cam
shot_objects=[]
for obj in S.get("objects",[]):
    if "glb" in obj:
        before=set(bpy.data.objects); asset=(ROOT/obj["glb"]).resolve()
        if not asset.is_relative_to(ROOT.resolve()): raise SystemExit("GLB path must stay inside repository")
        bpy.ops.import_scene.gltf(filepath=str(asset))
        imported=[o for o in set(bpy.data.objects)-before]
        root=bpy.data.objects.new(obj["name"],None); sc.collection.objects.link(root)
        for child in imported:
            if child.parent is None: child.parent=root
        root.location=obj.get("position",[0,0,0]); scale=obj.get("scale",1)
        root.scale=(scale,)*3 if isinstance(scale,(float,int)) else scale
        root.rotation_euler=[math.radians(v) for v in obj.get("rotation",[0,0,0])]
        parts=[o for o in imported if o.type=="MESH"]
        motion=root
    else:
        prim=obj.get("primitive","icosphere")
        if prim=="cube": bpy.ops.mesh.primitive_cube_add(size=1)
        elif prim=="sphere": bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12)
        elif prim=="cylinder": bpy.ops.mesh.primitive_cylinder_add(vertices=12)
        else: bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2)
        motion=bpy.context.object; motion.name=obj["name"]; motion.location=obj.get("position",[0,0,0]); motion.scale=obj.get("scale",[1,1,1])
        mat=bpy.data.materials.new(obj["name"]+" material"); mat.diffuse_color=lin(obj.get("color","#d49a58")); motion.data.materials.append(mat)
        parts=[motion]
    if "keyframes" in obj: motion["shot_keyframes"]=json.dumps(obj["keyframes"])
    shot_objects.append((obj["name"],parts,obj,motion))

# The EEVEE Shader-to-RGB plane leaves the world camera color untouched and draws soft shadow alpha on paper.
bpy.ops.mesh.primitive_plane_add(size=200, location=(0,0,0)); ground=bpy.context.object; ground.name="Paper shadow floor"
gm=bpy.data.materials.new("Paper shadow catcher"); gm.use_nodes=True; gm.surface_render_method="BLENDED"
nt=gm.node_tree; nt.nodes.clear(); N=nt.nodes.new
diffuse,s2r,bw,mr=N("ShaderNodeBsdfDiffuse"),N("ShaderNodeShaderToRGB"),N("ShaderNodeRGBToBW"),N("ShaderNodeMapRange")
trans,ink,mixshader,outmat=N("ShaderNodeBsdfTransparent"),N("ShaderNodeEmission"),N("ShaderNodeMixShader"),N("ShaderNodeOutputMaterial")
ink.inputs[0].default_value=lin("#302922"); mr.inputs["From Min"].default_value=.58; mr.inputs["From Max"].default_value=1.27
mr.inputs["To Min"].default_value=float(S.get("shadow_opacity",.04)); mr.inputs["To Max"].default_value=0
for a,b in ((diffuse.outputs[0],s2r.inputs[0]),(s2r.outputs[0],bw.inputs[0]),(bw.outputs[0],mr.inputs[0]),(mr.outputs[0],mixshader.inputs[0]),(trans.outputs[0],mixshader.inputs[1]),(ink.outputs[0],mixshader.inputs[2]),(mixshader.outputs[0],outmat.inputs[0])): nt.links.new(a,b)
ground.data.materials.append(gm)
for l in S.get("lights",[{"position":[-4,-5,8],"energy":1400,"size":5}]):
    d=bpy.data.lights.new("Softbox","AREA"); d.energy=l.get("energy",1400); d.shape="DISK"; d.size=l.get("size",5)
    o=bpy.data.objects.new("Softbox",d); sc.collection.objects.link(o); o.location=l.get("position",[-4,-5,8]); o.rotation_euler=(Vector((0,0,0))-o.location).to_track_quat("-Z","Y").to_euler()

def emission(hexcolor):
    m=bpy.data.materials.new("Overlay ink"); m.use_nodes=True; nodes=m.node_tree.nodes; nodes.clear()
    e=nodes.new("ShaderNodeEmission"); e.inputs[0].default_value=lin(hexcolor); o=nodes.new("ShaderNodeOutputMaterial"); m.node_tree.links.new(e.outputs[0],o.inputs[0]); return m
overlays=[]
for item in S.get("text",[]):
    cu=bpy.data.curves.new("Overlay","FONT"); cu.body=item["body"]; cu.size=item.get("size",.15); cu.extrude=0
    ob=bpy.data.objects.new("Overlay: "+item["body"],cu); sc.collection.objects.link(ob); ob.parent=cam; ob.data.materials.append(emission(item.get("color","#332a24")))
    overlays.append((item["body"],[ob],item))

out.mkdir(parents=True,exist_ok=True); frame_dir=out/("proof_frames" if mode=="proof" else "frames"); frame_dir.mkdir(exist_ok=True)
sample_frames=sorted(set(round(i*(frames-1)/5) for i in range(6))) if mode=="proof" else range(frames)
all_checks=[]; start=time.perf_counter()
for f in sample_frames:
    t=f/fps; c=at(S["camera"]["keyframes"],t)
    cam.location=c["position"]; cam.rotation_euler=(Vector(c["look_at"])-cam.location).to_track_quat("-Z","Y").to_euler()
    cam.data.sensor_fit="VERTICAL"; cam.data.angle=math.radians(c.get("fov",42))
    distance=2.; vfov=cam.data.angle; vsize=2*distance*math.tan(vfov/2); hsize=vsize*W/H
    for _,parts,cfg,motion in shot_objects:
        if motion and "shot_keyframes" in motion:
            v=at(json.loads(motion["shot_keyframes"]),t)
            for prop,attr in (("position","location"),("rotation","rotation_euler"),("scale","scale")):
                if prop in v: setattr(motion,attr,[math.radians(x) for x in v[prop]] if prop=="rotation" else v[prop])
    for _,parts,item in overlays:
        px,py=item.get("position",[.08,.12]); ob=parts[0]
        ob.location=((px-.5)*hsize,(.5-py)*vsize,-distance)
        ob.hide_render=not (item.get("in",0)<=t<item.get("out",duration))
    bpy.context.view_layer.update(); depsgraph=bpy.context.evaluated_depsgraph_get()
    sc.render.filepath=str(frame_dir/f"{f:05d}.png"); bpy.ops.render.render(write_still=True)
    if mode=="proof":
        frame_checks=check_frame({**S,"_frame_count":frames},f,t,[(n,p,cfg) for n,p,cfg,_ in shot_objects],overlays,cam,sc,depsgraph,sc.render.filepath,rgb(paper))
        all_checks.extend(frame_checks)
elapsed=time.perf_counter()-start
if mode=="proof":
    sheet=out/"proof.png"
    js="const sharp=require('sharp'),fs=require('fs'),path=require('path'); const d=process.argv[1],out=process.argv[2],files=fs.readdirSync(d).filter(x=>x.endsWith('.png')).sort(); (async()=>{const m=await sharp(path.join(d,files[0])).metadata(),w=m.width,h=m.height; await sharp({create:{width:w*3,height:h*2,channels:3,background:'#f3ece0'}}).composite(await Promise.all(files.map(async(f,i)=>({input:await sharp(path.join(d,f)).png().toBuffer(),left:(i%3)*w,top:Math.floor(i/3)*h})))).png().toFile(out)})().catch(e=>{console.error(e);process.exit(1)})"
    result=subprocess.run(["node","-e",js,str(frame_dir),str(sheet)],cwd=str(ROOT/"web"),capture_output=True,text=True)
    if result.returncode: raise RuntimeError("contact sheet failed: "+result.stderr)
    passed=all(c["status"]=="PASS" for c in all_checks)
    proof={"passed":passed,"spec":str(spec_path.relative_to(ROOT)),"spec_sha256":proof_hash,"aspect":effective_aspect,"resolution":[W,H],"fps":fps,"frames":sample_frames,"elapsed_s":round(elapsed,3),"checks":all_checks}
    proof_file.write_text(json.dumps(proof,indent=2),encoding="utf-8")
    for c in all_checks: print(f'{c["status"]}: frame={c["frame"]} t={c["time"]:.3f}s {c["name"]}: {c["detail"]}')
    print(("PASS" if passed else "FAIL")+f": proof overall ({sum(c['status']=='PASS' for c in all_checks)}/{len(all_checks)} checks); {elapsed:.2f}s; {sheet}; {proof_file}")
else:
    movie=out/(spec_path.stem+".mp4")
    ffmpeg=ROOT/"web"/"node_modules"/"@remotion"/"compositor-win32-x64-msvc"/"ffmpeg.exe"
    encoder=subprocess.run([str(ffmpeg),"-y","-framerate",str(fps),"-i",str(frame_dir/"%05d.png"),"-c:v","libx264","-pix_fmt","yuv420p",str(movie)],cwd=str(ROOT/"web"),capture_output=True,text=True)
    if encoder.returncode: raise RuntimeError("Remotion FFmpeg encode failed: "+encoder.stderr[-3000:])
    print(f"PASS: final rendered {len(list(sample_frames))} frames in {elapsed:.2f}s; encoded {movie} ({movie.stat().st_size} bytes)")
