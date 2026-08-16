import os
import sys
import json
import urllib.request
import subprocess
import yt_dlp
import imageio_ffmpeg

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
FFMPEG_DIR = os.path.dirname(FFMPEG_EXE)
if FFMPEG_DIR not in os.environ.get("PATH", ""):
    os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLIPS_DIR = os.path.join(BASE_DIR, "clips")
TEMP_DIR = os.path.join(BASE_DIR, "temp_segments")
os.makedirs(CLIPS_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

def get_manifest_info(url):
    if not url:
        raise ValueError("URL is required to fetch manifest info.")
    ydl_opts = {'quiet': True, 'no_warnings': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return info

def sanitize_title(title, max_len=20):
    import re
    if not title:
        return "clip"
    # Remove brackets like 【】, [], （）, (), etc.
    cleaned = re.sub(r'[【】\[\]\(\)（）「」『』〈〉《》]', ' ', title)
    # Remove prohibited filename characters: \ / : * ? " < > |
    cleaned = re.sub(r'[\\/*?:"<>|]', '', cleaned)
    # Remove multiple spaces/underscores
    cleaned = re.sub(r'\s+', '_', cleaned.strip())
    # Trim to max length without trailing underscore
    cleaned = cleaned[:max_len].rstrip('_')
    return cleaned if cleaned else "clip"

def generate_clip_by_segments(start_sec, end_sec, output_filename=None, quality="720p", url=None, title=None):
    import datetime
    import re
    
    if not url:
        # Fallback to highlights.json if available
        hl_file = os.path.join(BASE_DIR, "highlights.json")
        if os.path.exists(hl_file):
            with open(hl_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                url = data.get("video_url")
        if not url:
            raise ValueError("Video URL must be provided.")
    
    info = get_manifest_info(url)
    video_title = title or info.get('title', '')
    title_prefix = sanitize_title(video_title, max_len=20)

    start_m, start_s = int(start_sec // 60), int(start_sec % 60)
    end_m, end_s = int(end_sec // 60), int(end_sec % 60)
    time_tag = datetime.datetime.now().strftime("%H%M%S")

    if output_filename is None:
        output_filename = f"{title_prefix}_{start_m:02d}m{start_s:02d}s-{end_m:02d}m{end_s:02d}s_{time_tag}.mp4"
    elif not output_filename.endswith(".mp4"):
        output_filename = f"{output_filename}.mp4"

    # Avoid collision if file exists
    base_name, ext = os.path.splitext(output_filename)
    counter = 1
    while os.path.exists(os.path.join(CLIPS_DIR, output_filename)):
        output_filename = f"{base_name}_{counter}{ext}"
        counter += 1

    output_path = os.path.join(CLIPS_DIR, output_filename)
    print(f"\n[Clip Generator] Extracting {start_sec}s - {end_sec}s -> {output_filename}")
    
    # 298 (720p), 299 (1080p), or 135 (480p)
    target_itag = '298' if quality == '720p' else '299'
    video_format = next((f for f in info.get('formats', []) if f['format_id'] == target_itag), None)
    if not video_format:
        video_format = next(f for f in info.get('formats', []) if f['format_id'] == '135')
    
    audio_format = next(f for f in info.get('formats', []) if f['format_id'] == '140')

    video_frags = video_format.get('fragments', [])
    audio_frags = audio_format.get('fragments', [])

    start_idx = max(0, int(start_sec // 5))
    end_idx = min(len(video_frags) - 1, int(end_sec // 5) + 1)

    print(f"Downloading segments from sq={start_idx} to sq={end_idx}...")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    raw_v_path = os.path.join(TEMP_DIR, f"stream_{start_idx}_{end_idx}.m4v")
    raw_a_path = os.path.join(TEMP_DIR, f"stream_{start_idx}_{end_idx}.m4a")

    with open(raw_v_path, "wb") as f_v:
        for sq in range(start_idx, end_idx + 1):
            req = urllib.request.Request(video_frags[sq]['url'], headers=headers)
            with urllib.request.urlopen(req) as resp:
                f_v.write(resp.read())

    with open(raw_a_path, "wb") as f_a:
        for sq in range(start_idx, end_idx + 1):
            req = urllib.request.Request(audio_frags[sq]['url'], headers=headers)
            with urllib.request.urlopen(req) as resp:
                f_a.write(resp.read())

    base_time = start_idx * 5.0
    offset = max(0, start_sec - base_time)
    duration = end_sec - start_sec

    print(f"Trimming precise section: offset={offset:.2f}s, duration={duration:.2f}s...")

    cmd = [
        FFMPEG_EXE, "-y",
        "-ss", f"{offset:.2f}",
        "-i", raw_v_path,
        "-ss", f"{offset:.2f}",
        "-i", raw_a_path,
        "-t", f"{duration:.2f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        output_path
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print("FFmpeg trim error:", res.stderr)
        raise RuntimeError("FFmpeg trim failed")

    # Cleanup temp segment stream files
    for f in [raw_v_path, raw_a_path]:
        try:
            if os.path.exists(f):
                os.remove(f)
        except Exception:
            pass

    print(f"[Success] Clip generated successfully: {output_path} ({os.path.getsize(output_path)} bytes)")
    return output_path

if __name__ == "__main__":
    if len(sys.argv) >= 3:
        st = float(sys.argv[1])
        et = float(sys.argv[2])
        out_name = sys.argv[3] if len(sys.argv) > 3 else None
        generate_clip_by_segments(st, et, out_name)
    else:
        # Default top highlight
        hl_file = os.path.join(BASE_DIR, "highlights.json")
        if os.path.exists(hl_file):
            with open(hl_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("highlights"):
                top = data["highlights"][0]
                generate_clip_by_segments(top["start_seconds"], top["end_seconds"], f"top_highlight_{top['id']}.mp4")
