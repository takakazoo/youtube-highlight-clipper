import os
import unittest
import tempfile
import shutil
import numpy as np
import soundfile as sf
from unittest.mock import patch, MagicMock
from analyze_audio import analyze_highlights, convert_to_wav

class TestAnalyzeAudio(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_wav = os.path.join(self.test_dir, "synthetic_test.wav")

        # Generate 120s synthetic audio with 2 distinct volume spikes
        sr = 16000
        duration = 120
        t = np.linspace(0, duration, int(sr * duration), endpoint=False)
        # Background quiet noise
        signal = 0.05 * np.sin(2 * np.pi * 440 * t)
        # Spike 1 at 30s-40s
        idx1 = (t >= 30) & (t <= 40)
        signal[idx1] += 0.8 * np.sin(2 * np.pi * 880 * t[idx1])
        # Spike 2 at 80s-90s
        idx2 = (t >= 80) & (t <= 90)
        signal[idx2] += 0.9 * np.sin(2 * np.pi * 1000 * t[idx2])

        sf.write(self.test_wav, signal, sr)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_analyze_highlights_progress_callback_and_peaks(self):
        """Tests that analyze_highlights accepts progress_callback and detects peaks."""
        progress_messages = []
        def on_progress(msg):
            progress_messages.append(msg)

        with patch('analyze_audio.HIGHLIGHTS_JSON', os.path.join(self.test_dir, "highlights.json")), \
             patch('transcriber.transcribe_audio_file', return_value={"segments": [{"start": 30.0, "end": 35.0, "text": "テスト発話"}]}), \
             patch('transcriber.save_video_transcripts'):

            results = analyze_highlights(
                self.test_wav,
                clip_duration=30,
                min_interval=20,
                top_k=5,
                video_url="https://test.url",
                progress_callback=on_progress
            )

            self.assertGreater(len(results), 0)
            self.assertGreater(len(progress_messages), 0)
            self.assertIn("盛り上がりシーンを自動解析中...", progress_messages)

            # Check peak items structure
            top_highlight = results[0]
            self.assertIn("start_seconds", top_highlight)
            self.assertIn("end_seconds", top_highlight)
            self.assertIn("score", top_highlight)
            self.assertIn("transcript", top_highlight)
            self.assertGreater(top_highlight["score"], 0)

if __name__ == '__main__':
    unittest.main()
