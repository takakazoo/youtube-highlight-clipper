import os
import json
import unittest
import tempfile
import shutil
from transcriber import format_srt_time, generate_srt, save_video_transcripts, search_transcripts

class TestTranscriber(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.orig_trans_json = "transcripts.json"

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_format_srt_time(self):
        """Tests that seconds are accurately formatted into SRT time (HH:MM:SS,mmm)."""
        self.assertEqual(format_srt_time(0.0), "00:00:00,000")
        self.assertEqual(format_srt_time(5.123), "00:00:05,123")
        self.assertEqual(format_srt_time(65.5), "00:01:05,500")
        self.assertEqual(format_srt_time(3661.045), "01:01:01,045")

    def test_generate_srt(self):
        """Tests that SRT files are generated with valid sequential numbering and timestamps."""
        segments = [
            {"start": 1.0, "end": 4.5, "text": "こんにちは！"},
            {"start": 5.0, "end": 8.2, "text": "本日の切り抜きです。"}
        ]
        out_srt = os.path.join(self.test_dir, "test.srt")
        result_path = generate_srt(segments, out_srt)

        self.assertTrue(os.path.exists(result_path))
        with open(result_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("1\n00:00:01,000 --> 00:00:04,500\nこんにちは！", content)
        self.assertIn("2\n00:00:05,000 --> 00:00:08,200\n本日の切り抜きです。", content)

    def test_search_transcripts(self):
        """Tests keyword search across video transcripts with context window."""
        segments = [
            {"start": 10.0, "end": 15.0, "text": "ここでパラノマサイトの謎解きが始まります。"},
            {"start": 40.0, "end": 45.0, "text": "全く別の話題です。"},
            {"start": 120.0, "end": 125.0, "text": "パラノマサイトをクリアしました！"}
        ]
        test_json = os.path.join(self.test_dir, "test_transcripts.json")
        with open(test_json, "w", encoding="utf-8") as f:
            json.dump({"video_url": "https://test.url", "segments": segments}, f, ensure_ascii=False)

        # Mock json load in transcriber search
        with unittest.mock.patch('transcriber.os.path.exists', return_value=True), \
             unittest.mock.patch('builtins.open', unittest.mock.mock_open(read_data=json.dumps({"video_url": "test", "segments": segments}))):
            results = search_transcripts("パラノマサイト")
            self.assertEqual(len(results), 2)
            self.assertIn("謎解き", results[0]["text"])
            self.assertIn("クリア", results[1]["text"])
            self.assertEqual(results[0]["start"], 10.0)
            self.assertEqual(results[0]["end"], 15.0)

    @unittest.mock.patch('transcriber.get_whisper_model')
    def test_transcribe_progress_callback_and_eta(self, mock_get_model):
        """Tests that transcribe_audio_file invokes progress_callback with percentages, ETA, and messages."""
        from transcriber import transcribe_audio_file
        
        # Create mock segment items
        class DummySegment:
            def __init__(self, start, end, text):
                self.start = start
                self.end = end
                self.text = text

        dummy_segments = [
            DummySegment(0.0, 30.0, "セグメント1"),
            DummySegment(30.0, 60.0, "セグメント2"),
            DummySegment(60.0, 100.0, "セグメント3")
        ]
        
        class DummyInfo:
            duration = 100.0
            language = "ja"

        mock_model = unittest.mock.MagicMock()
        mock_model.transcribe.return_value = (dummy_segments, DummyInfo())
        mock_get_model.return_value = mock_model

        progress_calls = []
        def my_callback(pct, eta, msg):
            progress_calls.append((pct, eta, msg))

        res = transcribe_audio_file("dummy.wav", progress_callback=my_callback)
        self.assertEqual(len(res["segments"]), 3)
        self.assertGreater(len(progress_calls), 0)
        
        # Check that progress reaches 100%
        final_call = progress_calls[-1]
        self.assertEqual(final_call[0], 100)
        self.assertIn("100%", final_call[2])

if __name__ == '__main__':
    unittest.main()
