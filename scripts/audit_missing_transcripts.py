import os
import glob
import json
import csv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TRANSCRIPTS_DIR = BASE_DIR / "data" / "transcripts"
REDO_DIR = BASE_DIR / "data" / "redo"


def audit_transcripts():
    """
    Audits all stored video transcript JSON files.
    Finds videos missing transcript segment content and writes reports to data/redo/.
    """
    REDO_DIR.mkdir(parents=True, exist_ok=True)

    files = sorted(list(TRANSCRIPTS_DIR.glob("*/*.json")))
    files = [f for f in files if not f.name.endswith("channel.json")]

    total_count = len(files)

    valid_records = []
    missing_records = []

    for filepath in files:
        channel_handle = Path(filepath).parent.name
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        meta = data.get("metadata", {})
        t_data = data.get("transcript", {})

        video_id = meta.get("video_id", Path(filepath).stem)
        title = meta.get("title", "")
        url = meta.get("url", f"https://www.youtube.com/watch?v={video_id}")
        upload_date = meta.get("upload_date", "")

        has_t = t_data.get("has_transcript", False)
        segments = t_data.get("segments", [])
        word_count = t_data.get("word_count", 0)
        full_text = t_data.get("full_text", "")

        # Audit rule: transcript must have has_transcript True, non-empty segments, and non-zero word count
        is_missing = not has_t or len(segments) == 0 or word_count == 0 or not full_text

        record = {
            "channel": channel_handle,
            "video_id": video_id,
            "title": title,
            "url": url,
            "upload_date": upload_date,
            "status": "Missing transcript segments" if is_missing else "Valid",
            "error": t_data.get("error") if is_missing else None,
            "file_path": str(Path(filepath).relative_to(BASE_DIR))
        }

        if is_missing:
            missing_records.append(record)
        else:
            valid_records.append(record)

    print("=" * 60)
    print("TRANSCRIPT AUDIT SUMMARY")
    print("=" * 60)
    print(f"Total Videos Checked: {total_count}")
    print(f"Valid Transcripts   : {len(valid_records)}")
    print(f"Missing / Need Redo : {len(missing_records)}")
    print("=" * 60)

    # 1. Save missing_transcripts.json
    json_path = REDO_DIR / "missing_transcripts.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "audit_summary": {
                "total_videos": total_count,
                "valid_count": len(valid_records),
                "missing_count": len(missing_records)
            },
            "missing_videos": missing_records
        }, f, indent=2, ensure_ascii=False)
    print(f"Saved JSON report: {json_path}")

    # 2. Save missing_transcripts.csv
    csv_path = REDO_DIR / "missing_transcripts.csv"
    fieldnames = ["channel", "video_id", "title", "url", "upload_date", "status", "error", "file_path"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(missing_records)
    print(f"Saved CSV report : {csv_path}")

    # 3. Save redo_urls.txt (simple text list of YouTube URLs)
    txt_path = REDO_DIR / "redo_urls.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        for rec in missing_records:
            f.write(f"{rec['url']}\n")
    print(f"Saved URL list   : {txt_path}")
    print("=" * 60)

    return missing_records


if __name__ == "__main__":
    audit_transcripts()
