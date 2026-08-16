import os
import sys
import json
import re
import subprocess
import imageio_ffmpeg
from faster_whisper import WhisperModel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
FFMPEG_DIR = os.path.dirname(FFMPEG_EXE)
if FFMPEG_DIR not in os.environ.get("PATH", ""):
    os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")

TRANSCRIPTS_JSON = os.path.join(BASE_DIR, "transcripts.json")
_MODEL = None

def get_whisper_model(model_size="base"):
    global _MODEL
    if _MODEL is None:
        print(f"[Transcriber] Loading faster-whisper model ({model_size}) on CPU...")
        _MODEL = WhisperModel(model_size, device="cpu", compute_type="int8")
    return _MODEL

def format_timestamp(seconds):
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        millis = 999
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"

format_srt_time = format_timestamp

def transcribe_audio_file(audio_path, language="ja", progress_callback=None):
    """Transcribes an entire audio file or segment and returns structured segments with realtime progress updates."""
    import time
    model = get_whisper_model()
    start_time = time.time()
    segments_result, info = model.transcribe(
        audio_path,
        language=language,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
        beam_size=5
    )

    total_duration = getattr(info, 'duration', 0) or 1.0

    items = []
    full_text_list = []
    for s in segments_result:
        text = s.text.strip()
        if text:
            items.append({
                "start": round(s.start, 2),
                "end": round(s.end, 2),
                "text": text
            })
            full_text_list.append(text)

        if progress_callback and total_duration > 0:
            cur_end = min(total_duration, s.end)
            ratio = cur_end / total_duration
            pct = int(min(99, max(1, ratio * 100)))
            elapsed = time.time() - start_time
            if ratio > 0.03 and elapsed > 0.5:
                est_total = elapsed / ratio
                eta_sec = max(1, int(est_total - elapsed))
                eta_str = f"{eta_sec // 60}分{eta_sec % 60}秒" if eta_sec >= 60 else f"{eta_sec}秒"
                msg = f"AIテロップ生成中... {pct}% (処理 {int(cur_end)}秒/{int(total_duration)}秒, 残り約{eta_str})"
            else:
                eta_sec = None
                msg = f"AIテロップ生成中... {pct}% (処理 {int(cur_end)}秒/{int(total_duration)}秒)"
            progress_callback(pct, eta_sec, msg)

    if progress_callback:
        progress_callback(100, 0, "AIテロップ生成完了 (100%)")

    return {
        "text": " ".join(full_text_list),
        "segments": items,
        "language": getattr(info, "language", language)
    }

def generate_srt(segments, srt_path, offset_start=0.0):
    """Generates an SRT subtitle file from segments. If offset_start is given, timestamps are relative to 0."""
    with open(srt_path, "w", encoding="utf-8") as f:
        for idx, seg in enumerate(segments, 1):
            st = max(0, seg["start"] - offset_start)
            et = max(0, seg["end"] - offset_start)
            st_str = format_timestamp(st)
            et_str = format_timestamp(et)
            text = seg["text"].strip()
            f.write(f"{idx}\n{st_str} --> {et_str}\n{text}\n\n")
    return srt_path

def burn_subtitles_to_video(video_path, srt_path, output_path):
    """Burns subtitles into video using FFmpeg with beautiful styling."""
    # Escape path for FFmpeg subtitles filter on Windows
    escaped_srt = srt_path.replace("\\", "/").replace(":", "\\:")
    
    # Subtitle style: Font size 18, yellow/white text, black outline / box
    style = "FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=3,Outline=2,Shadow=0,MarginV=25,Alignment=2"
    sub_filter = f"subtitles='{escaped_srt}':force_style='{style}'"

    cmd = [
        FFMPEG_EXE, "-y",
        "-i", video_path,
        "-vf", sub_filter,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "copy",
        output_path
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        print("FFmpeg subtitle burn error:", res.stderr)
        raise RuntimeError("Failed to burn subtitles into video.")
    return output_path

def save_video_transcripts(url, segments):
    data = {
        "video_url": url,
        "segments": segments
    }
    with open(TRANSCRIPTS_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return TRANSCRIPTS_JSON

def search_transcripts(query):
    if not os.path.exists(TRANSCRIPTS_JSON):
        return []
    with open(TRANSCRIPTS_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    query = query.strip().lower()
    if not query:
        return []

    results = []
    for s in data.get("segments", []):
        if query in s["text"].lower():
            results.append({
                "start": s["start"],
                "end": s["end"],
                "start_time_str": f"{int(s['start']//60):02d}:{int(s['start']%60):02d}",
                "end_time_str": f"{int(s['end']//60):02d}:{int(s['end']%60):02d}",
                "text": s["text"]
            })
    return results
