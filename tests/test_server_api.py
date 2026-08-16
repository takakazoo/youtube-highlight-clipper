import os
import json
import unittest
import tempfile
import shutil
from unittest.mock import patch, MagicMock
import urllib.parse
from server import app, CURRENT_DATA

class TestServerAPI(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        self.test_clips_dir = tempfile.mkdtemp()
        self.patcher = patch('server.CLIPS_DIR', self.test_clips_dir)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        shutil.rmtree(self.test_clips_dir, ignore_errors=True)

    def test_get_info(self):
        """Tests /api/info endpoint response structure."""
        res = self.client.get('/api/info')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("url", data)
        self.assertIn("is_analyzing", data)
        self.assertIn("progress_msg", data)

    def test_get_highlights_error_propagation(self):
        """Tests that error_msg is accurately propagated in /api/highlights."""
        CURRENT_DATA["url"] = "https://youtube.com/watch?v=err123"
        CURRENT_DATA["error_msg"] = "動画が非公開です"
        CURRENT_DATA["is_analyzing"] = False

        res = self.client.get('/api/highlights')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get("error_msg"), "動画が非公開です")
        self.assertEqual(data.get("highlights"), [])

        # Reset
        CURRENT_DATA["error_msg"] = None

    def test_clips_list_sorting_and_details(self):
        """Tests /api/clips endpoint returns clips sorted by newest first with SRT flags."""
        # Create clip 1 (older)
        f1 = os.path.join(self.test_clips_dir, "clip_1.mp4")
        with open(f1, "w") as f: f.write("1")
        os.utime(f1, (1000, 1000))

        # Create clip 2 (newer) + srt
        f2 = os.path.join(self.test_clips_dir, "clip_2.mp4")
        with open(f2, "w") as f: f.write("2")
        os.utime(f2, (2000, 2000))
        with open(os.path.join(self.test_clips_dir, "clip_2.srt"), "w") as f: f.write("srt")

        res = self.client.get('/api/clips')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("clips", data)
        self.assertIn("details", data)
        self.assertEqual(data["clips"][0], "clip_2.mp4") # Newest first!

        details_map = {d["filename"]: d for d in data["details"]}
        self.assertTrue(details_map["clip_2.mp4"]["has_srt"])
        self.assertEqual(details_map["clip_2.mp4"]["srt_filename"], "clip_2.srt")
        self.assertFalse(details_map["clip_1.mp4"]["has_srt"])

    def test_delete_clip_and_associated_srt(self):
        """Tests DELETE /api/clips/<filename> removes both MP4 and SRT files."""
        mp4_path = os.path.join(self.test_clips_dir, "パラノマ_00m20s.mp4")
        srt_path = os.path.join(self.test_clips_dir, "パラノマ_00m20s.srt")
        with open(mp4_path, "w", encoding="utf-8") as f: f.write("video")
        with open(srt_path, "w", encoding="utf-8") as f: f.write("sub")

        # Call DELETE with URL encoded filename
        encoded_name = urllib.parse.quote("パラノマ_00m20s.mp4")
        res = self.client.delete(f'/api/clips/{encoded_name}')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "success")

        # Assert both files deleted
        self.assertFalse(os.path.exists(mp4_path))
        self.assertFalse(os.path.exists(srt_path))

    def test_delete_clip_nonexistent_returns_404(self):
        """Tests DELETE nonexistent clip returns 404 error."""
        res = self.client.delete('/api/clips/non_existent.mp4')
        self.assertEqual(res.status_code, 404)

    def test_security_path_traversal_prevention(self):
        """Tests path traversal attempt ../../secret.txt is safely sanitized to basename."""
        res = self.client.delete('/api/clips/..%2F..%2Fsecret.txt')
        self.assertEqual(res.status_code, 404)

if __name__ == '__main__':
    unittest.main()
