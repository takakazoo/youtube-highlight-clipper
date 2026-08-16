import os
import unittest
import tempfile
import shutil
from unittest.mock import patch, MagicMock
from segment_clipper import sanitize_title, get_unique_filepath

class TestSegmentClipper(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_sanitize_title_length_and_characters(self):
        """Tests that titles are sanitized and shortened according to Plan A (max 20 chars)."""
        raw_title = "【衝撃】パラノマサイト FILE38 本所七不思議 実況プレイ Part.1！ (超ネタバレあり)"
        sanitized = sanitize_title(raw_title, max_len=20)
        
        self.assertLessEqual(len(sanitized), 20)
        self.assertNotIn("【", sanitized)
        self.assertNotIn("】", sanitized)
        self.assertNotIn("！", sanitized)
        self.assertNotIn(" ", sanitized)
        self.assertNotIn("(", sanitized)
        self.assertNotIn(")", sanitized)
        self.assertTrue(len(sanitized) > 0)

    def test_sanitize_title_fallback_for_empty(self):
        """Tests fallback when title consists only of invalid characters."""
        self.assertEqual(sanitize_title("   ???///:::   "), "clip")
        self.assertEqual(sanitize_title("", max_len=20), "clip")

    def test_get_unique_filepath_no_collision(self):
        """Tests standard unique filepath generation when no collision exists."""
        filename = "test_00m20s-00m45s_123456.mp4"
        out_path = get_unique_filepath(self.test_dir, filename)
        expected_path = os.path.join(self.test_dir, filename)
        self.assertEqual(out_path, expected_path)

    def test_get_unique_filepath_with_collision(self):
        """Tests sequential numbering (_1, _2) when files with same name already exist."""
        filename = "test_00m20s-00m45s_123456.mp4"
        first_file = os.path.join(self.test_dir, filename)
        with open(first_file, "w", encoding="utf-8") as f:
            f.write("dummy")

        # Second file should get _1
        second_path = get_unique_filepath(self.test_dir, filename)
        self.assertEqual(os.path.basename(second_path), "test_00m20s-00m45s_123456_1.mp4")
        with open(second_path, "w", encoding="utf-8") as f:
            f.write("dummy")

        # Third file should get _2
        third_path = get_unique_filepath(self.test_dir, filename)
        self.assertEqual(os.path.basename(third_path), "test_00m20s-00m45s_123456_2.mp4")

    @patch('segment_clipper.get_manifest_info')
    @patch('segment_clipper.yt_dlp.YoutubeDL')
    def test_generate_clip_by_segments_naming_and_imports(self, mock_ydl_cls, mock_manifest):
        """Tests generate_clip_by_segments runs without NameError/ImportError and names clip properly."""
        from segment_clipper import generate_clip_by_segments
        mock_manifest.return_value = {
            'title': 'テスト動画タイトル'
        }
        mock_ydl = MagicMock()
        # When ydl.download is called, create the dummy file
        def fake_download(urls):
            # create the output file in temp_dir or clips_dir
            for f in os.listdir(self.test_dir):
                pass
        mock_ydl.download.side_effect = lambda urls: None
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl

        # Create dummy file beforehand so os.path.exists passes
        def side_effect_download(urls):
            for name in os.listdir(self.test_dir):
                pass
            # Write a dummy file to the first expected path
            with open(os.path.join(self.test_dir, "テスト動画タイトル_00m05s-00m12s_test.mp4"), "w") as f:
                f.write("dummy")

        mock_ydl.download.side_effect = side_effect_download

        with patch('segment_clipper.CLIPS_DIR', self.test_dir), \
             patch('segment_clipper.TEMP_DIR', self.test_dir):
            out_file = generate_clip_by_segments(
                start_sec=5.0,
                end_sec=12.0,
                output_filename="テスト動画タイトル_00m05s-00m12s_test.mp4",
                url="https://www.youtube.com/watch?v=sample",
                generate_srt=False,
                burn_subtitles=False
            )
            self.assertTrue(out_file.endswith(".mp4"))
            self.assertIn("テスト動画タイトル", os.path.basename(out_file))
            self.assertIn("00m05s-00m12s", os.path.basename(out_file))

if __name__ == '__main__':
    unittest.main()
