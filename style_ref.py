"""Extract reusable editing and writing characteristics from a public YouTube video.

Only numeric frame summaries and transcript text are sent to the model; source media is never retained.
"""
import json
import itertools
import re
import statistics
import tempfile
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import av
import numpy as np
from pydantic import BaseModel, Field

PALETTES = {"paper": [(243,236,224),(29,29,27),(232,67,46)], "ube": [(239,230,247),(59,31,92),(122,79,179)],
 "jeepney": [(255,210,63),(29,63,187),(230,57,70)], "pop": [(255,243,226),(255,107,74),(47,91,255)],
 "night": [(18,18,20),(42,29,58),(255,90,54)], "arcade": [(26,28,44),(93,39,93),(239,125,87)], "mono": [(244,244,242),(17,17,17),(128,128,128)]}

class ExtractedStyle(BaseModel):
    label: str
    description: str
    video_type: str
    structure: str
    writing: str
    pace: str
    cuts: str
    transitions: str
    captions: str
    effects: str
    visual_style: Literal["editorial", "2d", "pixel", "3d"]
    palette: Literal["paper", "ube", "jeepney", "pop", "night", "arcade", "mono"]
    segments: list[int] = Field(min_length=2, max_length=2)

def _analyse(path: Path, duration: float, contact_sheet: Path):
    container = av.open(str(path))
    stream = container.streams.video[0]
    step = max(.25, min(1.0, duration / 240))
    samples, prev, cuts = [], None, []
    try:
        for frame in container.decode(stream):
            sec = float(frame.pts * stream.time_base) if frame.pts is not None else 0
            if sec > duration or sec % step > .12:
                continue
            rgb = frame.to_ndarray(format="rgb24")
            small = rgb[::8, ::8]
            hist = np.histogramdd(small.reshape(-1,3), bins=(8,8,8), range=((0,256),)*3, density=True)[0]
            thumb = rgb[::max(1,rgb.shape[0]//72), ::max(1,rgb.shape[1]//72)]
            samples.append((sec, thumb, np.quantile(thumb.reshape(-1,3), [.2,.5,.8], axis=0).round().astype(int).tolist()))
            if prev and np.abs(hist-prev[1]).sum() > .72:
                cuts.append(sec)
            prev=(sec,hist)
    finally:
        container.close()
    # Treat first and last bounds as shot edges; avoid claiming zero or implausible durations.
    spans=np.diff([0,*cuts,duration]).tolist()
    # 10 evenly spaced keyframes make the colour summary representative across the whole reference.
    keyframes=[samples[round(i*(len(samples)-1)/9)] for i in range(10)] if len(samples) > 1 else samples
    if keyframes:
        thumbs=[x[1] for x in keyframes]
        h,w=thumbs[0].shape[:2]
        sheet=np.zeros((h*3,w*4,3),dtype=np.uint8)
        for i,thumb in enumerate(thumbs):
            thumb=thumb[np.linspace(0,thumb.shape[0]-1,h).astype(int)][:,np.linspace(0,thumb.shape[1]-1,w).astype(int)]
            sheet[(i//4)*h:(i//4+1)*h,(i%4)*w:(i%4+1)*w]=thumb
        with av.open(str(contact_sheet),"w",format="image2") as out:
            frame=av.VideoFrame.from_ndarray(sheet,format="rgb24")
            stream=out.add_stream("png")
            for packet in stream.encode(frame): out.mux(packet)
            for packet in stream.encode(): out.mux(packet)
    pixels=np.concatenate([x[1].reshape(-1,3) for x in keyframes]).astype(float) if keyframes else np.empty((0,3))
    if len(pixels):
        # Small deterministic k-means over keyframe pixels keeps the palette summary lightweight.
        centroids=np.percentile(pixels,[15,50,85],axis=0)
        for _ in range(8):
            labels=np.linalg.norm(pixels[:,None,:]-centroids[None,:,:],axis=2).argmin(axis=1)
            centroids=np.array([pixels[labels==i].mean(axis=0) if np.any(labels==i) else centroids[i] for i in range(3)])
        centroids=centroids.round().astype(int)
        palette=min(PALETTES, key=lambda k: min(sum(np.linalg.norm(centroids[i]-np.array(PALETTES[k][p[i]])) for i in range(3))
                                                  for p in itertools.permutations(range(3))))
    else:
        centroids=np.empty((0,3),dtype=int); palette="paper"
    return {"duration_seconds":round(duration,2),"sampled_frames":len(samples),"cut_count":len(cuts),
            "cuts_per_minute":round(len(cuts)*60/duration,2),"mean_shot_seconds":round(statistics.mean(spans),2),
            "median_shot_seconds":round(statistics.median(spans),2),"dominant_palette":palette,
            "dominant_rgb_centroids":centroids.tolist(),
            "keyframes_seconds_rgb_percentiles":[{"seconds":round(x[0],2),"rgb_percentiles":x[2]} for x in keyframes]}

def extract(url: str, ask, progress=None):
    parsed=urlparse(url)
    if parsed.scheme not in {"http","https"} or parsed.hostname not in {"youtube.com","www.youtube.com","m.youtube.com","youtu.be","www.youtube-nocookie.com"}:
        raise ValueError("Enter a YouTube video URL")
    import yt_dlp
    with yt_dlp.YoutubeDL({"quiet":True,"no_warnings":True,"skip_download":True,"noplaylist":True}) as ydl:
        info=ydl.extract_info(url, download=False)
    duration=float(info.get("duration") or 0)
    if not duration or duration > 180:
        raise ValueError("Reference must be a public video between 1 and 180 seconds")
    subs=[]
    with tempfile.TemporaryDirectory(prefix="blockcut-style-") as td:
        opts={"quiet":True,"no_warnings":True,"noplaylist":True,"skip_download":True,"writesubtitles":True,
              "writeautomaticsub":True,"subtitleslangs":["en.*","fil.*","tl.*"],"subtitlesformat":"vtt",
              "outtmpl":str(Path(td)/"ref.%(ext)s")}
        with yt_dlp.YoutubeDL(opts) as ydl: ydl.download([url])
        for f in Path(td).glob("*.vtt"):
            for line in f.read_text(encoding="utf-8",errors="ignore").splitlines():
                if line.strip() and "-->" not in line and not line.startswith(("WEBVTT","Kind:","Language:")):
                    text=re.sub(r"<[^>]+>","",line).strip()
                    if text and (not subs or subs[-1] != text): subs.append(text)
        if progress: progress(25,"downloading low-resolution reference")
        # Prefer 360p or lower; cap filesize as an additional safeguard.
        opts={"quiet":True,"no_warnings":True,"noplaylist":True,"format":"best[height<=360][ext=mp4]/best[height<=360]/worst",
              "max_filesize":100_000_000,"outtmpl":str(Path(td)/"video.%(ext)s"),"overwrites":True}
        with yt_dlp.YoutubeDL(opts) as ydl: ydl.download([url])
        files=list(Path(td).glob("video.*"))
        if not files: raise ValueError("YouTube did not provide a downloadable low-resolution video")
        if progress: progress(65,"measuring cuts, keyframes and colours")
        measured=_analyse(files[0],duration,Path(td)/"contact-sheet.png")
        transcript=" ".join(subs)[:10000]
        if not transcript:
            try:
                from youtube_transcript_api import YouTubeTranscriptApi
                vid=(url.split("youtu.be/")[-1].split("?")[0] if "youtu.be/" in url else
                     dict(x.split("=",1) for x in url.split("?",1)[-1].split("&") if "=" in x).get("v", ""))
                fetched=YouTubeTranscriptApi().fetch(vid, languages=["en","fil","tl"])
                transcript=" ".join(row.text for row in fetched)[:10000]
            except Exception:
                transcript=(info.get("description") or "")[:3000]
        prompt=f"""Analyze the reference as reusable general characteristics only. Never reproduce its exact lines, person, channel, footage, assets, or distinctive catchphrases. Return a style. Choose visual_style editorial, 2d, pixel, or 3d; palette one of paper, ube, jeepney, pop, night, arcade, mono. Use measured median shot <2.5s => punchy pace. Keep all fields concise.
Title: {info.get('title','')}
Channel: {info.get('channel','')}
Measured video analysis: {json.dumps(measured)}
Transcript sample: {transcript}"""
        if progress: progress(82,"synthesizing reusable style")
        result=ask(prompt,ExtractedStyle)
        d=result.model_dump()
        d["segments"]=sorted(max(4,min(10,int(x))) for x in d["segments"])
        d["pace"]="punchy" if measured["median_shot_seconds"] < 2.5 else "documentary"
        # Palette selection is derived from the sampled frame colours, not guessed from genre.
        d["palette"]=measured["dominant_palette"]
        slug=re.sub(r"[^a-z0-9]+","-",d["label"].lower()).strip("-")[:36] or "youtube-style"
        from content_styles import STYLES_DIR
        STYLES_DIR.mkdir(parents=True,exist_ok=True)
        target=STYLES_DIR/f"{slug}.json"
        i=2
        while target.exists(): target=STYLES_DIR/f"{slug}-{i}.json"; i+=1
        style={"id":target.stem,"label":d["label"],"description":d["description"],"video_type":d["video_type"],
               "structure":d["structure"],"writing":d["writing"],"editing":{"pace":d["pace"],"cuts":d["cuts"],
               "transitions":d["transitions"],"captions":d["captions"],"effects":d["effects"]},
               "visual":{"style":d["visual_style"],"palette":d["palette"]},"segments":d["segments"],
               "source":{"url":url,"title":info.get("title",""),"channel":info.get("channel","" )},"measured":measured}
        target.write_text(json.dumps(style,ensure_ascii=False,indent=2),encoding="utf-8")
        return style
