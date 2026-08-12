import sys
import argparse
import json
import logging
from pathlib import Path
from core.extractor import extract_channel_videos
from core.transcript import fetch_transcript
from core.formatter import to_markdown, to_srt, to_txt
from core.storage import save_channel_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("yt-research-cli")


def run_extraction(
    channel: str,
    period: str = "3m",
    start_date: str = None,
    end_date: str = None,
    max_results: int = None,
    save_local: bool = True,
    export_format: str = None,
    output_dir: str = None
) -> dict:
    logger.info(f"Starting YouTube extraction for channel '{channel}' (Period: {period})...")

    def progress_callback(msg, pct, total):
        logger.info(f"[{pct}%] {msg}")

    # Step 1: Discover & filter channel videos by date range
    channel_data = extract_channel_videos(
        channel_input=channel,
        period=period,
        start_date=start_date,
        end_date=end_date,
        max_results=max_results,
        progress_callback=progress_callback
    )

    videos = channel_data.get("videos", [])
    logger.info(f"Discovered {len(videos)} videos within date range ({channel_data['date_range']['start']} to {channel_data['date_range']['end']}).")

    transcripts_map = {}
    from concurrent.futures import ThreadPoolExecutor

    def process_video_transcript(idx_and_video):
        idx, video = idx_and_video
        vid_id = video["video_id"]
        title = video["title"]
        logger.info(f"[{idx}/{len(videos)}] Extracting transcript for '{title}' ({vid_id})...")
        t_data = fetch_transcript(vid_id)
        if t_data.get("has_transcript"):
            logger.info(f"  -> Transcript retrieved ({t_data['word_count']} words, {len(t_data['segments'])} segments).")
        else:
            logger.warning(f"  -> Transcript unavailable: {t_data.get('error')}")
        return vid_id, t_data

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(process_video_transcript, list(enumerate(videos, 1))))
        for vid_id, t_data in results:
            transcripts_map[vid_id] = t_data

    if save_local:
        save_channel_data(channel_data, transcripts_map)
        logger.info("Saved extraction results to data/ store.")

    # Export formats if requested
    if export_format and output_dir:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        handle = channel_data["channel_handle"]

        for video in videos:
            vid_id = video["video_id"]
            t_data = transcripts_map.get(vid_id, {})

            if export_format.lower() in ("md", "markdown"):
                content = to_markdown(video, t_data)
                filename = f"{vid_id}_{video['upload_date']}.md"
            elif export_format.lower() == "srt":
                content = to_srt(t_data)
                filename = f"{vid_id}_{video['upload_date']}.srt"
            elif export_format.lower() == "txt":
                content = to_txt(video, t_data)
                filename = f"{vid_id}_{video['upload_date']}.txt"
            else:
                content = json.dumps({"metadata": video, "transcript": t_data}, indent=2, ensure_ascii=False)
                filename = f"{vid_id}_{video['upload_date']}.json"

            file_file = out_path / filename
            with open(file_file, "w", encoding="utf-8") as f:
                f.write(content)

        logger.info(f"Exported {len(videos)} transcript files ({export_format.upper()}) to {output_dir}")

    return {
        "channel": channel_data["channel_handle"],
        "channel_title": channel_data["channel_title"],
        "date_range": channel_data["date_range"],
        "video_count": len(videos),
        "transcripts_count": sum(1 for t in transcripts_map.values() if t.get("has_transcript")),
        "videos": videos
    }


def main():
    parser = argparse.ArgumentParser(description="Headless YouTube Channel Video & Transcript Extractor")
    parser.add_argument("--channel", "-c", help="YouTube channel handle or URL (e.g. @theAIsearch)")
    parser.add_argument("--url", "-u", help="Fetch transcript for a specific YouTube video URL or ID")
    parser.add_argument("--period", "-p", default="3m", help="Time period window (e.g. 3m, 1m, 30d, 6m, 1y). Default: 3m")
    parser.add_argument("--start-date", help="Optional start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", help="Optional end date (YYYY-MM-DD)")
    parser.add_argument("--max-results", type=int, help="Optional maximum number of videos to extract")
    parser.add_argument("--format", choices=["json", "md", "srt", "txt"], help="Export format")
    parser.add_argument("--output-dir", help="Directory path to write export files")
    parser.add_argument("--no-save", action="store_true", help="Disable saving to default data store")
    parser.add_argument("--cookies-from-browser", help="Browser to export cookies from (chrome, firefox, edge)")

    args = parser.parse_args()

    if args.url:
        from scripts.redo_transcripts import update_video_transcript
        print(f"Fetching transcript for URL/ID: {args.url}")
        success = update_video_transcript(args.url, channel_handle=args.channel, cookies_from_browser=args.cookies_from_browser)
        sys.exit(0 if success else 1)

    if not args.channel:
        parser.error("Either --channel or --url is required.")

    try:
        res = run_extraction(
            channel=args.channel,
            period=args.period,
            start_date=args.start_date,
            end_date=args.end_date,
            max_results=args.max_results,
            save_local=not args.no_save,
            export_format=args.format,
            output_dir=args.output_dir
        )
        print("\n" + "=" * 50)
        print("EXTRACTION SUMMARY")
        print("=" * 50)
        print(f"Channel: @{res['channel']} ({res['channel_title']})")
        print(f"Time Range: {res['date_range']['start']} to {res['date_range']['end']} ({res['date_range']['period']})")
        print(f"Videos Found: {res['video_count']}")
        print(f"Transcripts Extracted: {res['transcripts_count']}")
        print("=" * 50)
        sys.exit(0)
    except Exception as e:
        logger.error(f"Headless extraction failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

