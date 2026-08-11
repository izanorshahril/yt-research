import os
import uuid
import asyncio
import threading
import zipfile
import io
from pathlib import Path
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, BackgroundTasks, HTTPException, Query, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

from core.extractor import extract_channel_videos
from core.transcript import fetch_transcript
from core.formatter import to_markdown, to_srt, to_txt
from core.storage import (
    save_channel_data,
    get_stored_channels,
    load_channel_videos,
    load_video_data,
    DATA_DIR,
)

BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"

app = FastAPI(
    title="YouTube Channel Research Tool API",
    version="0.1.0",
    description="Backend API for YouTube Video Metadata & Timestamped Transcript Extraction"
)

# In-memory job state tracker
jobs_store: Dict[str, Dict[str, Any]] = {}


class ExtractRequest(BaseModel):
    channel: str = Field(..., example="@theAIsearch")
    period: str = Field("3m", example="3m")
    start_date: Optional[str] = Field(None, example="2026-05-11")
    end_date: Optional[str] = Field(None, example="2026-08-11")
    max_results: Optional[int] = Field(None, example=20)


class AIAnalyzeRequest(BaseModel):
    video_id: str
    channel: str
    prompt: Optional[str] = "Summarize the key insights and timestamped takeaways of this transcript."
    provider: Optional[str] = "local-stub"  # local-stub, ollama, lm-studio, openai, gemini


def run_background_extraction(job_id: str, req: ExtractRequest):
    job = jobs_store[job_id]
    job["status"] = "running"
    job["progress"] = 5
    job["logs"].append(f"Starting extraction for channel '{req.channel}' (Period: {req.period})...")

    try:
        def progress_cb(msg: str, pct: int, total: int):
            job["progress"] = max(5, min(95, pct))
            job["logs"].append(f"[{job['progress']}%] {msg}")

        # Extract videos metadata
        channel_data = extract_channel_videos(
            channel_input=req.channel,
            period=req.period,
            start_date=req.start_date,
            end_date=req.end_date,
            max_results=req.max_results,
            progress_callback=progress_cb
        )

        videos = channel_data.get("videos", [])
        total_vids = len(videos)
        job["logs"].append(f"Discovered {total_vids} videos matching date criteria.")

        transcripts_map = {}
        from concurrent.futures import ThreadPoolExecutor

        completed_count = 0
        def fetch_task(vid_item):
            nonlocal completed_count
            vid_id = vid_item["video_id"]
            title = vid_item["title"]
            job["logs"].append(f"Fetching transcript for '{title}'...")
            t_data = fetch_transcript(vid_id)
            completed_count += 1
            curr_pct = 50 + int((completed_count / max(1, total_vids)) * 45)
            job["progress"] = min(95, curr_pct)
            return vid_id, t_data

        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(fetch_task, videos))
            for vid_id, t_data in results:
                transcripts_map[vid_id] = t_data

        # Save results
        save_channel_data(channel_data, transcripts_map)

        job["status"] = "completed"
        job["progress"] = 100
        job["logs"].append("Extraction successfully completed!")
        job["result"] = {
            "channel_handle": channel_data["channel_handle"],
            "channel_title": channel_data["channel_title"],
            "date_range": channel_data["date_range"],
            "total_videos": len(videos),
            "transcripts_extracted": sum(1 for t in transcripts_map.values() if t.get("has_transcript"))
        }

    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
        job["logs"].append(f"ERROR: Extraction failed - {e}")


@app.post("/api/extract")
def start_extraction(req: ExtractRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())[:8]
    jobs_store[job_id] = {
        "job_id": job_id,
        "channel": req.channel,
        "period": req.period,
        "status": "pending",
        "progress": 0,
        "logs": ["Job queued."],
        "result": None,
        "error": None
    }
    background_tasks.add_task(run_background_extraction, job_id, req)
    return {"job_id": job_id, "status": "pending", "message": "Extraction task started."}


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str):
    if job_id not in jobs_store:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs_store[job_id]


@app.get("/api/channels")
def list_channels():
    return {"channels": get_stored_channels()}


@app.get("/api/channels/{channel_handle}")
def get_channel(channel_handle: str):
    data = load_channel_videos(channel_handle)
    if not data:
        raise HTTPException(status_code=404, detail="Channel data not found")
    return data


@app.get("/api/channels/{channel_handle}/videos/{video_id}")
def get_video_transcript(channel_handle: str, video_id: str):
    data = load_video_data(channel_handle, video_id)
    if not data:
        raise HTTPException(status_code=404, detail="Video transcript not found")
    return data


@app.get("/api/export/{channel_handle}")
def export_channel_transcripts(channel_handle: str, format: str = Query("md", pattern="^(md|json|srt|txt)$")):
    ch_data = load_channel_videos(channel_handle)
    if not ch_data:
        raise HTTPException(status_code=404, detail="Channel data not found")

    videos = ch_data.get("videos", [])
    handle = ch_data.get("channel_handle", channel_handle)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for video in videos:
            vid_id = video["video_id"]
            vid_record = load_video_data(handle, vid_id) or {}
            t_data = vid_record.get("transcript", {})

            if format == "md":
                content = to_markdown(video, t_data)
                filename = f"{handle}/{video['upload_date']}_{vid_id}.md"
            elif format == "srt":
                content = to_srt(t_data)
                filename = f"{handle}/{video['upload_date']}_{vid_id}.srt"
            elif format == "txt":
                content = to_txt(video, t_data)
                filename = f"{handle}/{video['upload_date']}_{vid_id}.txt"
            else:
                import json
                content = json.dumps(vid_record, indent=2, ensure_ascii=False)
                filename = f"{handle}/{video['upload_date']}_{vid_id}.json"

            zf.writestr(filename, content)

    zip_buffer.seek(0)
    headers = {"Content-Disposition": f"attachment; filename={handle}_transcripts_{format}.zip"}
    return StreamingResponse(zip_buffer, media_type="application/zip", headers=headers)


@app.post("/api/ai/analyze")
def ai_analyze_stub(req: AIAnalyzeRequest):
    """
    Modular AI Analysis Stub Interface.
    Can be connected to local Ollama / LM Studio or cloud APIs (OpenAI/Gemini/Claude).
    """
    vid_data = load_video_data(req.channel, req.video_id)
    if not vid_data:
        raise HTTPException(status_code=404, detail="Video data not found")

    meta = vid_data.get("metadata", {})
    transcript = vid_data.get("transcript", {})
    segments = transcript.get("segments", [])

    # Stub analysis generation
    sample_takeaways = []
    if segments:
        for seg in segments[:3]:
            sample_takeaways.append(f"• **[{seg.get('start_formatted')}]**: {seg.get('text')}")

    analysis_response = {
        "video_id": req.video_id,
        "channel": req.channel,
        "title": meta.get("title"),
        "provider": req.provider,
        "status": "success",
        "summary": f"Transcript summary for '{meta.get('title')}' ({transcript.get('word_count', 0)} words).",
        "key_insights": [
            "Extracted core technological discussion and timestamped references.",
            f"Analyzed video published on {meta.get('upload_date')} (Duration: {meta.get('duration_str')})."
        ],
        "timestamped_takeaways": sample_takeaways if sample_takeaways else ["No transcript segments available."],
        "note": "AI Layer is modular. Connect local Ollama / LM Studio or API keys for deep model analysis."
    }

    return analysis_response


# Mount Web Frontend if directory exists
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    @app.get("/")
    def read_root():
        index_file = WEB_DIR / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return {"status": "ok", "message": "Backend API running. Web frontend files under /web"}
