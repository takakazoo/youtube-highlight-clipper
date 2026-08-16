import os
import json
from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
import imageio_ffmpeg
from segment_clipper import generate_clip_by_segments

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLIPS_DIR = os.path.join(BASE_DIR, "clips")
HIGHLIGHTS_JSON = os.path.join(BASE_DIR, "highlights.json")

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
FFMPEG_DIR = os.path.dirname(FFMPEG_EXE)
if FFMPEG_DIR not in os.environ.get("PATH", ""):
    os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")

os.makedirs(CLIPS_DIR, exist_ok=True)

app = Flask(__name__, static_folder=BASE_DIR)
CORS(app)

CURRENT_DATA = {
    "url": "https://www.youtube.com/watch?v=RJrGlRVA0-s",
    "title": "【パラノマサイト FILE38 伊勢人魚物語】初代過ぎるおじさんが初見実況【switch】",
    "video_id": "RJrGlRVA0-s"
}

@app.route("/")
def index():
    return send_file(os.path.join(BASE_DIR, "index.html"))

@app.route("/api/info", methods=["GET"])
def get_info():
    return jsonify(CURRENT_DATA)

@app.route("/api/highlights", methods=["GET"])
def get_highlights():
    if os.path.exists(HIGHLIGHTS_JSON):
        with open(HIGHLIGHTS_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)
    return jsonify({"highlights": []})

@app.route("/api/analyze_new", methods=["POST"])
def analyze_new():
    data = request.get_json(force=True)
    new_url = data.get("url", "").strip()
    if not new_url:
        return jsonify({"status": "error", "message": "URLが入力されていません"}), 400

    import yt_dlp
    import re
    # Extract video id
    match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', new_url)
    v_id = match.group(1) if match else "video"

    ydl_opts = {'quiet': True, 'no_warnings': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(new_url, download=False)
        title = info.get('title', 'YouTube Video')

    CURRENT_DATA["url"] = new_url
    CURRENT_DATA["title"] = title
    CURRENT_DATA["video_id"] = v_id

    # Run analysis in background
    from analyze_audio import download_audio, convert_to_wav, analyze_highlights
    audio_path = os.path.join(BASE_DIR, "audio.m4a")
    wav_path = os.path.join(BASE_DIR, "audio_16k.wav")
    
    def run_proc():
        if os.path.exists(audio_path): os.remove(audio_path)
        if os.path.exists(wav_path): os.remove(wav_path)
        download_audio(new_url, audio_path)
        convert_to_wav(audio_path, wav_path)
        analyze_highlights(wav_path)

    import threading
    threading.Thread(target=run_proc, daemon=True).start()

    return jsonify({
        "status": "started",
        "title": title,
        "video_id": v_id,
        "message": "動画の解析を開始しました"
    })

@app.route("/api/clips", methods=["GET"])
def get_clips():
    clips = [f for f in os.listdir(CLIPS_DIR) if f.endswith(".mp4")]
    return jsonify({"clips": clips})

@app.route("/clips/<path:filename>", methods=["GET"])
def download_clip(filename):
    return send_from_directory(CLIPS_DIR, filename)

@app.route("/api/generate_clip", methods=["POST"])
def generate_clip():
    data = request.get_json(force=True)
    start_sec = float(data.get("start_sec", 0))
    end_sec = float(data.get("end_sec", 30))

    start_m, start_s = int(start_sec // 60), int(start_sec % 60)
    end_m, end_s = int(end_sec // 60), int(end_sec % 60)
    filename = f"clip_{start_m:02d}m{start_s:02d}s_to_{end_m:02d}m{end_s:02d}s.mp4"

    try:
        generate_clip_by_segments(start_sec, end_sec, filename, quality="720p", url=CURRENT_DATA.get("url", VIDEO_URL))
        return jsonify({
            "status": "success",
            "filename": filename,
            "download_url": f"/clips/{filename}"
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=False)
