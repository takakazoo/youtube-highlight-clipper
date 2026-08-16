import os
import json
import re
import threading
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
    "url": "",
    "title": "URLを入力して動画を読み込んでください",
    "video_id": "",
    "is_analyzing": False,
    "progress_msg": "URLを入力してください",
    "error_msg": None
}

def extract_youtube_id(url):
    # Regex to match youtube video ID from various URL formats
    patterns = [
        r'(?:v=|\/v\/|embed\/|youtu\.be\/|shorts\/|\/e\/|watch\?v=)([^#\&\?]{11})',
        r'([0-9A-Za-z_-]{11})'
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return ""

@app.route("/")
def index():
    return send_file(os.path.join(BASE_DIR, "index.html"))

@app.route("/api/info", methods=["GET"])
def get_info():
    return jsonify(CURRENT_DATA)

@app.route("/api/highlights", methods=["GET"])
def get_highlights():
    current_url = CURRENT_DATA.get("url", "").strip()
    if not current_url:
        return jsonify({"highlights": []})

    if os.path.exists(HIGHLIGHTS_JSON):
        try:
            with open(HIGHLIGHTS_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("video_url") == current_url:
                return jsonify(data)
        except Exception:
            pass
    return jsonify({"highlights": []})

def process_analysis_task(url, video_id):
    CURRENT_DATA["is_analyzing"] = True
    CURRENT_DATA["error_msg"] = None
    CURRENT_DATA["progress_msg"] = "動画のタイトルと情報を取得中..."

    import yt_dlp
    from analyze_audio import download_audio, convert_to_wav, analyze_highlights

    audio_path = os.path.join(BASE_DIR, "audio.m4a")
    wav_path = os.path.join(BASE_DIR, "audio_16k.wav")

    try:
        ydl_opts = {'quiet': True, 'no_warnings': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            CURRENT_DATA["title"] = info.get('title', 'YouTube Video')

        CURRENT_DATA["progress_msg"] = "音声ストリームをダウンロード中..."
        if os.path.exists(audio_path): os.remove(audio_path)
        if os.path.exists(wav_path): os.remove(wav_path)
        
        download_audio(url, audio_path)

        CURRENT_DATA["progress_msg"] = "音声をWAV形式に変換中..."
        convert_to_wav(audio_path, wav_path)

        CURRENT_DATA["progress_msg"] = "盛り上がりシーンを自動解析中..."
        analyze_highlights(wav_path, video_url=url)

        CURRENT_DATA["progress_msg"] = "解析完了"
        CURRENT_DATA["is_analyzing"] = False
    except Exception as e:
        print("Analysis error:", e)
        CURRENT_DATA["error_msg"] = str(e)
        CURRENT_DATA["progress_msg"] = f"解析エラー: {e}"
        CURRENT_DATA["is_analyzing"] = False

@app.route("/api/analyze_new", methods=["POST"])
def analyze_new():
    data = request.get_json(force=True) if request.is_json else request.form
    new_url = data.get("url", "").strip()
    if not new_url:
        return jsonify({"status": "error", "message": "URLが入力されていません"}), 400

    v_id = extract_youtube_id(new_url)
    CURRENT_DATA["url"] = new_url
    CURRENT_DATA["video_id"] = v_id
    CURRENT_DATA["title"] = "読み込み中..."
    CURRENT_DATA["is_analyzing"] = True
    CURRENT_DATA["progress_msg"] = "解析タスクを開始しました..."
    CURRENT_DATA["error_msg"] = None

    # Clear previous highlights while analyzing
    if os.path.exists(HIGHLIGHTS_JSON):
        try:
            with open(HIGHLIGHTS_JSON, "w", encoding="utf-8") as f:
                json.dump({"video_url": new_url, "highlights": []}, f)
        except Exception:
            pass

    threading.Thread(target=process_analysis_task, args=(new_url, v_id), daemon=True).start()

    return jsonify({
        "status": "started",
        "video_id": v_id,
        "message": "解析タスクを開始しました"
    })

@app.route("/api/transcripts", methods=["GET"])
def get_transcripts_endpoint():
    current_url = CURRENT_DATA.get("url", "").strip()
    if not current_url:
        return jsonify({"segments": []})
    trans_file = os.path.join(BASE_DIR, "transcripts.json")
    if os.path.exists(trans_file):
        with open(trans_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return jsonify(data)
    return jsonify({"segments": []})

@app.route("/api/transcript_search", methods=["GET"])
def search_transcripts_endpoint():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"results": []})
    from transcriber import search_transcripts
    results = search_transcripts(query)
    return jsonify({"query": query, "results": results})

@app.route("/api/clips", methods=["GET"])
def get_clips():
    current_url = CURRENT_DATA.get("url", "").strip()
    if not current_url:
        return jsonify({"clips": []})
    clips = [f for f in os.listdir(CLIPS_DIR) if f.endswith(".mp4")]
    return jsonify({"clips": clips})

@app.route("/clips/<path:filename>", methods=["GET"])
def download_clip(filename):
    return send_from_directory(CLIPS_DIR, filename)

@app.route("/api/generate_clip", methods=["POST"])
def generate_clip():
    data = request.get_json(force=True) if request.is_json else request.form
    start_sec = float(data.get("start_sec", 0))
    end_sec = float(data.get("end_sec", 30))
    url = data.get("url") or CURRENT_DATA.get("url", "").strip()
    generate_srt = bool(data.get("generate_srt", False))
    burn_subtitles = bool(data.get("burn_subtitles", False))

    if not url:
        return jsonify({"status": "error", "message": "動画URLが指定されていません。先に動画を解析してください。"}), 400

    try:
        output_path = generate_clip_by_segments(
            start_sec, end_sec,
            quality="720p",
            url=url,
            title=CURRENT_DATA.get("title"),
            generate_srt=generate_srt,
            burn_subtitles=burn_subtitles
        )
        filename = os.path.basename(output_path)
        base_name, _ = os.path.splitext(filename)
        srt_name = f"{base_name}.srt" if generate_srt else None

        return jsonify({
            "status": "success",
            "filename": filename,
            "download_url": f"/clips/{filename}",
            "srt_filename": srt_name,
            "srt_download_url": f"/clips/{srt_name}" if srt_name else None
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=False)
