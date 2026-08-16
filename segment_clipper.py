import os
import sys
import json
import urllib.request
import subprocess
import datetime
from datetime import datetime
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

def get_unique_filepath(directory, filename):
    """Generates unique file path by adding _1, _2 suffixes if file exists."""
    base_name, ext = os.path.splitext(filename)
    counter = 1
    current_name = filename
    while os.path.exists(os.path.join(directory, current_name)):
        current_name = f"{base_name}_{counter}{ext}"
        counter += 1
    return os.path.join(directory, current_name)

def ensure_ffmpeg_setup():
    """Ensures ffmpeg.exe exists in imageio_ffmpeg directory and PATH."""
    ffmpeg_dir = os.path.dirname(FFMPEG_EXE)
    ffmpeg_bin = os.path.join(ffmpeg_dir, "ffmpeg.exe")
    if not os.path.exists(ffmpeg_bin):
        try:
            import shutil
            shutil.copyfile(FFMPEG_EXE, ffmpeg_bin)
        except Exception:
            pass
    if ffmpeg_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
    return ffmpeg_dir

def generate_clip_by_segments(start_sec, end_sec, output_filename=None, quality="720p", url=None, title=None, generate_srt=False, burn_subtitles=False):
    if not url:
        hl_file = os.path.join(BASE_DIR, "highlights.json")
        if os.path.exists(hl_file):
            with open(hl_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                url = data.get("video_url")
        if not url:
            raise ValueError("Video URL must be provided.")
    
    ffmpeg_dir = ensure_ffmpeg_setup()
    info = get_manifest_info(url)
    video_title = title or info.get('title', 'clip')

    if not output_filename:
        # Plan A: {SanitizedTitle_Max20}_{Start}m{Starts}s-{End}m{Ends}s_{Time}.mp4
        s_title = sanitize_title(video_title, max_len=20)
        st_m = int(start_sec // 60)
        st_s = int(start_sec % 60)
        et_m = int(end_sec // 60)
        et_s = int(end_sec % 60)
        now_str = datetime.now().strftime("%H%M%S")
        output_filename = f"{s_title}_{st_m:02d}m{st_s:02d}s-{et_m:02d}m{et_s:02d}s_{now_str}.mp4"
    elif not output_filename.endswith(".mp4"):
        output_filename = f"{output_filename}.mp4"

    # Avoid collision if file exists
    output_path = get_unique_filepath(CLIPS_DIR, output_filename)
    output_filename = os.path.basename(output_path)
    base_name, ext = os.path.splitext(output_filename)

    print(f"\n[Clip Generator] Extracting {start_sec}s - {end_sec}s -> {output_filename}")

    temp_trimmed_mp4 = os.path.join(TEMP_DIR, f"trimmed_{output_filename}") if burn_subtitles else output_path
    if os.path.exists(temp_trimmed_mp4):
        os.remove(temp_trimmed_mp4)

    # 1. Download specific time section using yt-dlp's native partial downloader
    ydl_opts = {
        'ffmpeg_location': ffmpeg_dir,
        'download_ranges': yt_dlp.utils.download_range_func(None, [(start_sec, end_sec)]),
        'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best',
        'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'},
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
        'legacy_server_connect': True,
        'outtmpl': temp_trimmed_mp4,
        'merge_output_format': 'mp4',
        'force_keyframes_at_cuts': False,
        'quiet': True,
        'no_warnings': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        print("yt-dlp download error:", e)
        raise RuntimeError(f"Failed to download clip section: {e}")

    if not os.path.exists(temp_trimmed_mp4):
        raise RuntimeError(f"Clip file was not created: {temp_trimmed_mp4}")

    # 2. Transcription / SRT processing if requested
    srt_path = os.path.join(CLIPS_DIR, f"{base_name}.srt")
    if generate_srt or burn_subtitles:
        try:
            print("[Clip Generator] Transcribing audio for subtitles...")
            from transcriber import transcribe_audio_file, generate_srt as gen_srt, burn_subtitles_to_video
            trans_res = transcribe_audio_file(temp_trimmed_mp4)
            temp_srt = os.path.join(TEMP_DIR, f"{base_name}.srt")
            gen_srt(trans_res["segments"], temp_srt, offset_start=0.0)

            if generate_srt:
                import shutil
                shutil.copyfile(temp_srt, srt_path)
                print(f"[Success] SRT subtitle file saved: {srt_path}")

            if burn_subtitles:
                print("[Clip Generator] Burning subtitles into video...")
                burn_subtitles_to_video(temp_trimmed_mp4, temp_srt, output_path)
                if os.path.exists(temp_trimmed_mp4):
                    os.remove(temp_trimmed_mp4)
        except Exception as e:
            print("[Warning] Subtitle generation error:", e)
            if burn_subtitles and os.path.exists(temp_trimmed_mp4) and not os.path.exists(output_path):
                import shutil
                shutil.move(temp_trimmed_mp4, output_path)

    file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
    print(f"[Success] Clip generated successfully: {output_path} ({file_size} bytes)")
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
