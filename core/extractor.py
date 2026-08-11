import re
import ssl
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple, Callable

try:
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    pass

import yt_dlp


def normalize_channel_input(channel_input: str) -> Tuple[str, str]:
    """
    Normalizes input channel string into a valid YouTube videos URL and handle.
    Accepts:
      - '@theAIsearch'
      - 'theAIsearch'
      - 'https://www.youtube.com/@theAIsearch'
      - 'https://www.youtube.com/@theAIsearch/videos'
      - 'https://www.youtube.com/channel/UC...'
    """
    channel_input = channel_input.strip()
    
    if channel_input.startswith("http://") or channel_input.startswith("https://"):
        url = channel_input
        if not url.endswith("/videos") and not "/watch?" in url:
            url = url.rstrip("/") + "/videos"
        
        handle_match = re.search(r"@([A-Za-z0-9_.-]+)", channel_input)
        if handle_match:
            handle = handle_match.group(1)
        else:
            parts = channel_input.rstrip("/").split("/")
            handle = parts[-1] if parts[-1] != "videos" else parts[-2]
            handle = handle.lstrip("@")
    else:
        handle = channel_input.lstrip("@")
        url = f"https://www.youtube.com/@{handle}/videos"
        
    return url, handle


def parse_period(period_str: str) -> timedelta:
    """Parses period strings like '1m', '3m', '6m', '1y', '30d', '90d' into timedelta."""
    period_str = period_str.strip().lower()
    if period_str.endswith("m"):
        months = int(period_str[:-1])
        return timedelta(days=months * 30)
    elif period_str.endswith("d"):
        days = int(period_str[:-1])
        return timedelta(days=days)
    elif period_str.endswith("y"):
        years = int(period_str[:-1])
        return timedelta(days=years * 365)
    elif period_str.endswith("w"):
        weeks = int(period_str[:-1])
        return timedelta(days=weeks * 7)
    else:
        # Default to 90 days (3 months) if unrecognized
        try:
            days = int(period_str)
            return timedelta(days=days)
        except ValueError:
            return timedelta(days=90)


def get_date_range(
    period: Optional[str] = "3m",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Tuple[datetime, datetime]:
    """
    Returns (start_dt, end_dt) UTC datetime range.
    """
    now = datetime.now(timezone.utc)
    
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            end_dt = now
    else:
        end_dt = now

    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            start_dt = end_dt - parse_period(period or "3m")
    else:
        delta = parse_period(period or "3m")
        start_dt = end_dt - delta
        
    return start_dt, end_dt


def parse_yt_date(date_str_or_timestamp: Any) -> Optional[datetime]:
    """Parses YYYYMMDD string or unix timestamp into UTC datetime."""
    if not date_str_or_timestamp:
        return None
    if isinstance(date_str_or_timestamp, (int, float)):
        return datetime.fromtimestamp(date_str_or_timestamp, tz=timezone.utc)
    if isinstance(date_str_or_timestamp, str):
        try:
            return datetime.strptime(date_str_or_timestamp, "%Y%m%d").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
        try:
            return datetime.strptime(date_str_or_timestamp, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def format_duration(seconds: Optional[int]) -> str:
    """Formats seconds into HH:MM:SS or MM:SS."""
    if not seconds:
        return "00:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def extract_channel_videos(
    channel_input: str,
    period: str = "3m",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_results: Optional[int] = None,
    progress_callback: Optional[Callable[[str, int, int], None]] = None
) -> Dict[str, Any]:
    """
    Extracts video metadata from a channel filtered by date range.
    Returns:
      {
        "channel_handle": str,
        "channel_title": str,
        "channel_url": str,
        "date_range": {"start": str, "end": str},
        "total_videos_found": int,
        "videos": list of video objects
      }
    """
    url, handle = normalize_channel_input(channel_input)
    start_dt, end_dt = get_date_range(period, start_date, end_date)
    
    if progress_callback:
        progress_callback("Fetching video list from YouTube...", 0, 100)

    ydl_opts = {
        "extract_flat": True,
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "nocheckcertificate": True,
    }

    channel_title = handle
    raw_entries = []

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            if info:
                channel_title = info.get("uploader") or info.get("channel") or info.get("title") or handle
                raw_entries = info.get("entries") or []
        except Exception as e:
            if progress_callback:
                progress_callback(f"Error extracting channel info: {e}", 0, 100)
            raise RuntimeError(f"Failed to fetch channel data for {channel_input}: {e}")

    videos: List[Dict[str, Any]] = []
    total_raw = len(raw_entries)
    
    if progress_callback:
        progress_callback(f"Found {total_raw} total channel entries. Filtering by date range...", 20, 100)

    # Process and fetch missing dates if needed
    video_ydl_opts = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "nocheckcertificate": True,
    }

    processed_count = 0
    consecutive_old_count = 0

    def fetch_video_detail(entry_item):
        video_id = entry_item.get("id")
        if not video_id:
            return None
        video_title = entry_item.get("title") or "Untitled Video"
        upload_dt = parse_yt_date(entry_item.get("upload_date") or entry_item.get("timestamp"))

        if not upload_dt:
            try:
                v_opts = {
                    "skip_download": True,
                    "quiet": True,
                    "no_warnings": True,
                    "ignoreerrors": True,
                    "nocheckcertificate": True,
                }
                with yt_dlp.YoutubeDL(v_opts) as video_ydl:
                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                    detail = video_ydl.extract_info(video_url, download=False)
                    if detail:
                        upload_dt = parse_yt_date(detail.get("upload_date") or detail.get("timestamp"))
                        video_title = detail.get("title") or video_title
                        entry_item["duration"] = detail.get("duration") or entry_item.get("duration")
                        entry_item["view_count"] = detail.get("view_count") or entry_item.get("view_count")
            except Exception:
                pass

        if not upload_dt:
            return None

        dur_sec = entry_item.get("duration")
        return {
            "video_id": video_id,
            "title": video_title,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "upload_date": upload_dt.strftime("%Y-%m-%d"),
            "upload_timestamp": int(upload_dt.timestamp()),
            "upload_dt": upload_dt,
            "duration_seconds": dur_sec,
            "duration_str": format_duration(dur_sec),
            "view_count": entry_item.get("view_count"),
            "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        }

    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Chunk processing to maintain chronological ordering and early stopping
    batch_size = 8
    stop_extraction = False

    for i in range(0, len(raw_entries), batch_size):
        if stop_extraction:
            break
        if max_results and len(videos) >= max_results:
            break

        batch = raw_entries[i:i + batch_size]
        batch_results = []

        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            future_to_entry = {executor.submit(fetch_video_detail, entry): entry for entry in batch}
            for future in as_completed(future_to_entry):
                res = future.result()
                if res:
                    batch_results.append(res)

        # Sort batch results by timestamp descending
        batch_results.sort(key=lambda x: x["upload_timestamp"], reverse=True)

        for item in batch_results:
            processed_count += 1
            upload_dt = item["upload_dt"]

            if upload_dt < start_dt:
                consecutive_old_count += 1
                if consecutive_old_count >= 2:
                    stop_extraction = True
                    if progress_callback:
                        progress_callback(f"Reached video from {upload_dt.strftime('%Y-%m-%d')} before timeframe cut-off ({start_dt.strftime('%Y-%m-%d')}). Stopping scan.", 85, 100)
                    break
            else:
                consecutive_old_count = 0
                if start_dt <= upload_dt <= end_dt:
                    clean_item = {k: v for k, v in item.items() if k != "upload_dt"}
                    videos.append(clean_item)

        if progress_callback and total_raw > 0:
            pct = 20 + int((min(processed_count, total_raw) / total_raw) * 70)
            progress_callback(f"Evaluated {processed_count}/{total_raw} videos (Matched: {len(videos)})", pct, 100)

    # Sort videos by upload_date descending (newest first)
    videos.sort(key=lambda v: v["upload_timestamp"], reverse=True)

    if progress_callback:
        progress_callback(f"Filtered {len(videos)} videos in date range.", 90, 100)

    return {
        "channel_handle": handle,
        "channel_title": channel_title,
        "channel_url": url,
        "date_range": {
            "start": start_dt.strftime("%Y-%m-%d"),
            "end": end_dt.strftime("%Y-%m-%d"),
            "period": period
        },
        "total_videos_found": len(videos),
        "videos": videos
    }
