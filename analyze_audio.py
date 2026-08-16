import os
import sys
import json
import subprocess
import yt_dlp
import numpy as np
import librosa
import soundfile as sf
import imageio_ffmpeg

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
VIDEO_URL = "https://www.youtube.com/watch?v=RJrGlRVA0-s"
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_PATH = os.path.join(OUTPUT_DIR, "audio.m4a")
WAV_PATH = os.path.join(OUTPUT_DIR, "audio_16k.wav")
HIGHLIGHTS_JSON = os.path.join(OUTPUT_DIR, "highlights.json")

def download_audio(url, output_path):
    print("Downloading audio stream...")
    ydl_opts = {
        'format': 'ba/b[ext=m4a]/bestaudio',
        'outtmpl': output_path,
        'overwrites': True,
        'quiet': False,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    print(f"Audio downloaded to: {output_path}")

def convert_to_wav(input_path, output_path):
    print("Converting audio to 16kHz mono WAV for analysis...")
    cmd = [FFMPEG_PATH, "-y", "-i", input_path, "-ar", "16000", "-ac", "1", output_path]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print("FFmpeg stderr:", res.stderr)
        raise RuntimeError("FFmpeg audio conversion failed.")
    print("Converted successfully.")

def analyze_highlights(wav_path, clip_duration=45, min_interval=60, top_k=10, video_url=VIDEO_URL):
    print("Analyzing audio volume and energy spikes...")
    y, sr = librosa.load(wav_path, sr=16000)
    total_duration = len(y) / sr
    print(f"Total audio duration: {total_duration:.1f}s ({int(total_duration//60)}m {int(total_duration%60)}s)")

    # Frame-wise RMS energy
    hop_length = 8000 # 0.5s per hop
    frame_length = 16000 # 1s frame
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
    times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)

    # Calculate rolling delta (sudden volume increase = scream / surprise reaction)
    rms_db = librosa.amplitude_to_db(rms, ref=np.max)
    
    # Moving average baseline to detect spikes relative to surrounding background
    window_size = int(60 / 0.5) # 60-second background window
    baseline = np.convolve(rms_db, np.ones(window_size)/window_size, mode='same')
    relative_spike = rms_db - baseline

    # Combined score: RMS energy + sudden burst
    score = (rms_db - np.min(rms_db)) / (np.max(rms_db) - np.min(rms_db) + 1e-6) * 0.6 + \
            np.maximum(0, relative_spike) / (np.max(relative_spike) + 1e-6) * 0.4

    # Search for peak segments
    peaks = []
    step = int(clip_duration / 0.5)
    
    for i in range(0, len(score) - step, int(5 / 0.5)): # 5-second slide
        segment_score = np.mean(score[i : i + step]) + np.max(score[i : i + step]) * 0.5
        t_start = times[i]
        peaks.append((segment_score, t_start))

    # Sort peaks and apply non-maximum suppression (avoid overlapping clips)
    peaks.sort(key=lambda x: x[0], reverse=True)
    
    selected_clips = []
    for sc, t in peaks:
        overlap = False
        for _, sel_t, _ in selected_clips:
            if abs(t - sel_t) < min_interval:
                overlap = True
                break
        if not overlap:
            t_start = max(0, t - 5) # 5 seconds pre-roll for context
            t_end = min(total_duration, t_start + clip_duration)
            selected_clips.append((float(sc), float(t_start), float(t_end)))
        if len(selected_clips) >= top_k:
            break

    selected_clips.sort(key=lambda x: x[1]) # Sort by chronological order

    def format_time(sec):
        m = int(sec // 60)
        s = int(sec % 60)
        return f"{m:02d}:{s:02d}"

    results = []
    for idx, (sc, st, et) in enumerate(selected_clips, 1):
        item = {
            "id": idx,
            "start_seconds": round(st, 1),
            "end_seconds": round(et, 1),
            "duration": round(et - st, 1),
            "start_time_str": format_time(st),
            "end_time_str": format_time(et),
            "score": round(sc * 100, 1),
            "description": f"ハイライト候補 #{idx} (盛り上がり度: {round(sc * 100, 1)}点)"
        }
        results.append(item)
        print(f"[{idx}] {item['start_time_str']} - {item['end_time_str']} (スコア: {item['score']}点)")

    with open(HIGHLIGHTS_JSON, "w", encoding="utf-8") as f:
        json.dump({
            "video_url": video_url,
            "total_duration": total_duration,
            "highlights": results
        }, f, ensure_ascii=False, indent=2)

    print(f"\nAnalysis complete! Saved highlights to {HIGHLIGHTS_JSON}")
    return results

if __name__ == "__main__":
    if not os.path.exists(AUDIO_PATH):
        download_audio(VIDEO_URL, AUDIO_PATH)
    if not os.path.exists(WAV_PATH):
        convert_to_wav(AUDIO_PATH, WAV_PATH)
    analyze_highlights(WAV_PATH)
