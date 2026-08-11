import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"
INDEX_FILE = DATA_DIR / "index.json"


def ensure_dirs():
    DATA_DIR.mkdir(exist_ok=True)
    TRANSCRIPTS_DIR.mkdir(exist_ok=True)


def get_channel_dir(channel_handle: str) -> Path:
    ensure_dirs()
    handle_clean = channel_handle.lstrip("@").lower()
    ch_dir = TRANSCRIPTS_DIR / handle_clean
    ch_dir.mkdir(exist_ok=True)
    return ch_dir


def load_main_index() -> Dict[str, Any]:
    ensure_dirs()
    if INDEX_FILE.exists():
        try:
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"channels": {}}


def save_main_index(index_data: Dict[str, Any]):
    ensure_dirs()
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index_data, f, indent=2, ensure_ascii=False)


def save_channel_data(channel_data: Dict[str, Any], transcripts_map: Dict[str, Dict[str, Any]]):
    """
    Saves extracted channel video metadata and transcripts to disk.
    Structure:
      data/transcripts/<channel_handle>/channel.json
      data/transcripts/<channel_handle>/<video_id>.json
    """
    ensure_dirs()
    handle = channel_data["channel_handle"].lstrip("@").lower()
    ch_dir = get_channel_dir(handle)

    # Save channel metadata
    channel_json_path = ch_dir / "channel.json"
    with open(channel_json_path, "w", encoding="utf-8") as f:
        json.dump(channel_data, f, indent=2, ensure_ascii=False)

    # Save individual video transcript JSONs
    videos_list = channel_data.get("videos", [])
    for video in videos_list:
        vid_id = video["video_id"]
        t_data = transcripts_map.get(vid_id, {})
        video_record = {
            "metadata": video,
            "transcript": t_data
        }
        vid_path = ch_dir / f"{vid_id}.json"
        with open(vid_path, "w", encoding="utf-8") as f:
            json.dump(video_record, f, indent=2, ensure_ascii=False)

    # Update global index
    main_index = load_main_index()
    main_index["channels"][handle] = {
        "channel_handle": channel_data.get("channel_handle"),
        "channel_title": channel_data.get("channel_title"),
        "channel_url": channel_data.get("channel_url"),
        "last_updated": channel_data.get("date_range", {}).get("end"),
        "video_count": len(videos_list),
        "period": channel_data.get("date_range", {}).get("period")
    }
    save_main_index(main_index)


def get_stored_channels() -> List[Dict[str, Any]]:
    main_index = load_main_index()
    return list(main_index.get("channels", {}).values())


def load_channel_videos(channel_handle: str) -> Optional[Dict[str, Any]]:
    handle = channel_handle.lstrip("@").lower()
    ch_dir = TRANSCRIPTS_DIR / handle
    ch_json = ch_dir / "channel.json"
    if ch_json.exists():
        with open(ch_json, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def load_video_data(channel_handle: str, video_id: str) -> Optional[Dict[str, Any]]:
    handle = channel_handle.lstrip("@").lower()
    vid_json = TRANSCRIPTS_DIR / handle / f"{video_id}.json"
    if vid_json.exists():
        with open(vid_json, "r", encoding="utf-8") as f:
            return json.load(f)
    return None
