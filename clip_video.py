import os
import sys
import json
import yt_dlp
import imageio_ffmpeg
import subprocess

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
FFMPEG_DIR = os.path.dirname(FFMPEG_EXE)
if FFMPEG_DIR not in os.environ.get("PATH", ""):
    os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")
# Create ffmpeg.exe symlink or copy if needed so yt-dlp finds ffmpeg.exe
ffmpeg_target = os.path.join(FFMPEG_DIR, "ffmpeg.exe")
if not os.path.exists(ffmpeg_target):
    import shutil
    try:
        shutil.copyfile(FFMPEG_EXE, ffmpeg_target)
    except Exception:
        pass

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
CLIPS_DIR = os.path.join(OUTPUT_DIR, "clips")
os.makedirs(CLIPS_DIR, exist_ok=True)

def generate_clip(url, start_sec, end_sec, output_filename=None, title="clip"):
    if output_filename is None:
        start_m, start_s = int(start_sec // 60), int(start_sec % 60)
        end_m, end_s = int(end_sec // 60), int(end_sec % 60)
        output_filename = f"clip_{start_m:02d}m{start_s:02d}s_to_{end_m:02d}m{end_s:02d}s.mp4"

    output_path = os.path.join(CLIPS_DIR, output_filename)
    print(f"Generating clip: {output_path} ({start_sec}s - {end_sec}s)...")

    ydl_opts = {
        'format': 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_path,
        'overwrites': True,
        'quiet': False,
        'ffmpeg_location': FFMPEG_DIR,
        'download_ranges': yt_dlp.utils.download_range_func(None, [(start_sec, end_sec)]),
        'force_keyframes_at_cuts': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    print(f"Clip successfully created at: {output_path}")
    return output_path

if __name__ == "__main__":
    if len(sys.argv) >= 3:
        st = float(sys.argv[1])
        et = float(sys.argv[2])
        url = sys.argv[3] if len(sys.argv) > 3 else "https://www.youtube.com/watch?v=RJrGlRVA0-s"
        out_name = sys.argv[4] if len(sys.argv) > 4 else None
        generate_clip(url, st, et, out_name)
    else:
        # Load from highlights.json and generate top 1 clip by default
        hl_file = os.path.join(OUTPUT_DIR, "highlights.json")
        if os.path.exists(hl_file):
            with open(hl_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("highlights"):
                top_hl = max(data["highlights"], key=lambda x: x["score"])
                print(f"Generating top highlight: {top_hl['description']} ({top_hl['start_time_str']} - {top_hl['end_time_str']})")
                generate_clip(data["video_url"], top_hl["start_seconds"], top_hl["end_seconds"], f"top_highlight_{top_hl['id']}.mp4")
