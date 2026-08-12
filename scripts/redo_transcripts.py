import os
import glob
import json
import time
import argparse
from pathlib import Path
from core.transcript import fetch_transcript, extract_video_id
from core.storage import BASE_DIR, TRANSCRIPTS_DIR


def find_channel_for_video(video_id: str) -> str:
    """Finds which channel directory contains the video ID."""
    if TRANSCRIPTS_DIR.exists():
        for ch_dir in TRANSCRIPTS_DIR.iterdir():
            if ch_dir.is_dir():
                ch_json = ch_dir / "channel.json"
                if ch_json.exists():
                    try:
                        with open(ch_json, "r", encoding="utf-8") as f:
                            cdata = json.load(f)
                        vids = [v.get("video_id") for v in cdata.get("videos", [])]
                        if video_id in vids:
                            return ch_dir.name
                    except Exception:
                        pass
                if (ch_dir / f"{video_id}.json").exists():
                    return ch_dir.name
    return "starterstory"




def update_video_transcript(video_url_or_id: str, channel_handle: str = None, cookies_from_browser: str = None, delay: float = 1.0) -> bool:
    """Fetches and updates the transcript for a single video URL or ID."""
    vid_id = extract_video_id(video_url_or_id)
    if not channel_handle:
        channel_handle = find_channel_for_video(vid_id)

    channel_dir = TRANSCRIPTS_DIR / channel_handle
    channel_dir.mkdir(parents=True, exist_ok=True)
    vid_json_path = channel_dir / f"{vid_id}.json"

    metadata = {
        "video_id": vid_id,
        "title": f"Video {vid_id}",
        "url": f"https://www.youtube.com/watch?v={vid_id}"
    }

    if vid_json_path.exists():
        try:
            with open(vid_json_path, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
                metadata = existing_data.get("metadata", metadata)
        except Exception:
            pass

    print(f"-> Fetching transcript for '{metadata.get('title')}' ({vid_id})...")
    t_data = fetch_transcript(vid_id, cookies_from_browser=cookies_from_browser, delay=delay)

    record = {
        "metadata": metadata,
        "transcript": t_data
    }

    with open(vid_json_path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)

    if t_data.get("has_transcript") and t_data.get("word_count", 0) > 0:
        print(f"   [SUCCESS] {vid_id}: {t_data['word_count']} words, {len(t_data['segments'])} segments saved to {vid_json_path.name}")
        return True
    else:
        print(f"   [FAILED] {vid_id}: {t_data.get('error')}")
        return False


def redo_batch_from_file(file_path: str, cookies_from_browser: str = None, delay: float = 1.0):
    """Processes a file containing video URLs or IDs line by line."""
    file_p = Path(file_path)
    if not file_p.exists():
        print(f"Error: File not found at {file_path}")
        return

    with open(file_p, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    print(f"Starting transcript redo batch for {len(lines)} items from {file_path}...")
    success_count = 0

    for idx, item in enumerate(lines, 1):
        print(f"[{idx}/{len(lines)}]", end=" ")
        if update_video_transcript(item, cookies_from_browser=cookies_from_browser, delay=delay):
            success_count += 1

    print("=" * 60)
    print(f"BATCH REDO COMPLETED: {success_count}/{len(lines)} transcripts successfully retrieved.")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="YouTube Single or Batch Transcript Redo Tool")
    parser.add_argument("--url", "-u", help="Single YouTube video URL or Video ID to fetch/redo")
    parser.add_argument("--file", "-f", help="Path to text/JSON/CSV file containing YouTube URLs/IDs (default: data/redo/redo_urls.txt)")
    parser.add_argument("--channel", "-c", help="Channel handle override (e.g. starterstory)")
    parser.add_argument("--cookies-from-browser", help="Browser to export cookies from (chrome, firefox, edge)")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay in seconds between requests (default: 1.0)")
    parser.add_argument("--rebuild-catalogue", action="store_true", help="Re-run starterstory catalogue extraction script after completion")

    args = parser.parse_args()

    if args.url:
        update_video_transcript(args.url, channel_handle=args.channel, cookies_from_browser=args.cookies_from_browser, delay=args.delay)
    else:
        file_target = args.file or str(BASE_DIR / "data" / "redo" / "redo_urls.txt")
        redo_batch_from_file(file_target, cookies_from_browser=args.cookies_from_browser, delay=args.delay)

    if args.rebuild_catalogue:
        print("\nRebuilding Starter Story Catalogue CSV...")
        from scripts.extract_starterstory_catalogue import process_all_transcripts
        process_all_transcripts()


if __name__ == "__main__":
    main()
