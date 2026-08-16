import json
import unittest

def match_live_subtitle(current_time, video_segments, tolerance=0.2, hold_time=1.5):
    """
    Python implementation of the frontend live subtitle matching logic in index.html:
    currentTime >= (s.start - 0.2) && currentTime <= (s.end + 1.5)
    """
    if not video_segments:
        return None
    for seg in video_segments:
        if (seg["start"] - tolerance) <= current_time <= (seg["end"] + hold_time):
            return seg["text"]
    
    # Check upcoming hint
    for seg in video_segments:
        if seg["start"] > current_time and (seg["start"] - current_time) <= 8.0:
            diff = round(seg["start"] - current_time, 1)
            return f"UPCOMING:{diff}:{seg['text']}"
    return None

def process_youtube_postmessage(raw_data_str, target_end_sec):
    """
    Python implementation of the frontend postMessage listener logic in index.html:
    Listens to infoDelivery, extracts currentTime, checks pause trigger.
    """
    try:
        data = json.loads(raw_data_str) if isinstance(raw_data_str, str) else raw_data_str
        if data and data.get("event") == "infoDelivery" and "info" in data:
            cur = data["info"].get("currentTime")
            if isinstance(cur, (int, float)):
                should_pause = (target_end_sec is not None and cur >= target_end_sec)
                return {
                    "currentTime": cur,
                    "should_pause": should_pause
                }
    except Exception:
        pass
    return None

class TestSubtitleSync(unittest.TestCase):
    def setUp(self):
        self.sample_segments = [
            {"start": 10.0, "end": 15.0, "text": "はじめまして、よろしくおねがいします。"},
            {"start": 16.0, "end": 20.0, "text": "今日はホラーゲームを実況します。"},
            {"start": 30.0, "end": 35.5, "text": "うわあああ！びっくりした！"}
        ]

    def test_live_subtitle_exact_hit(self):
        """Tests subtitle matches perfectly within utterance interval."""
        text = match_live_subtitle(12.5, self.sample_segments)
        self.assertEqual(text, "はじめまして、よろしくおねがいします。")

        text = match_live_subtitle(32.0, self.sample_segments)
        self.assertEqual(text, "うわあああ！びっくりした！")

    def test_live_subtitle_tolerance_hit(self):
        """Tests subtitle matches within ±0.2s tolerance buffer (smooth subtitle display)."""
        # Just before start (9.9s)
        text = match_live_subtitle(9.9, self.sample_segments, tolerance=0.2)
        self.assertEqual(text, "はじめまして、よろしくおねがいします。")

    def test_live_subtitle_lingering_hold_and_upcoming_hint(self):
        """Tests subtitle lingering hold time (1.5s after end) and upcoming speech hint."""
        # Lingering hold 1.0s after end (16.0s for 15.0s end) -> matches previous utterance smoothly
        text_held = match_live_subtitle(15.8, self.sample_segments)
        self.assertEqual(text_held, "はじめまして、よろしくおねがいします。")

        # Upcoming hint at 25.0s (next utterance starts at 30.0s, diff = 5.0s)
        hint = match_live_subtitle(25.0, self.sample_segments)
        self.assertEqual(hint, "UPCOMING:5.0:うわあああ！びっくりした！")

    def test_live_subtitle_no_speech_gap(self):
        """Tests returns None when current time falls into silence / BGM interval (beyond 8s to next speech)."""
        text = match_live_subtitle(50.0, self.sample_segments)
        self.assertIsNone(text)

    def test_postmessage_time_and_pause_trigger(self):
        """Tests parsing of YouTube iframe postMessage infoDelivery and auto-stop condition."""
        # Frame playing at 14.5s with targetEndSec = 20.0s -> No pause
        msg_payload = json.dumps({
            "event": "infoDelivery",
            "info": {"currentTime": 14.5, "playerState": 1}
        })
        res = process_youtube_postmessage(msg_payload, target_end_sec=20.0)
        self.assertIsNotNone(res)
        self.assertEqual(res["currentTime"], 14.5)
        self.assertFalse(res["should_pause"])

        # Frame playing at 20.1s with targetEndSec = 20.0s -> Must trigger pause!
        msg_payload_reached = json.dumps({
            "event": "infoDelivery",
            "info": {"currentTime": 20.1, "playerState": 1}
        })
        res_pause = process_youtube_postmessage(msg_payload_reached, target_end_sec=20.0)
        self.assertIsNotNone(res_pause)
        self.assertEqual(res_pause["currentTime"], 20.1)
        self.assertTrue(res_pause["should_pause"])

    def test_continuous_playback_timeline_progression(self):
        """Tests that subtitles dynamically change and progress continuously as playback time advances (no freezing on first speech)."""
        timeline_outputs = []
        # Simulate continuous 100ms ticker playback from 9.0s to 32.0s
        for t_int in range(90, 330, 5): # 9.0s to 32.5s with 0.5s step
            t = t_int / 10.0
            sub = match_live_subtitle(t, self.sample_segments)
            timeline_outputs.append((t, sub))

        # 1. At 10.0s, speech 1 is active
        self.assertEqual(match_live_subtitle(10.5, self.sample_segments), "はじめまして、よろしくおねがいします。")

        # 2. At 15.5s, speech 1 is held
        self.assertEqual(match_live_subtitle(15.5, self.sample_segments), "はじめまして、よろしくおねがいします。")

        # 3. At 17.0s, speech 2 is active (switched!)
        self.assertEqual(match_live_subtitle(17.0, self.sample_segments), "今日はホラーゲームを実況します。")

        # 4. At 25.0s, upcoming hint for speech 3 is shown
        self.assertIn("UPCOMING:5.0", match_live_subtitle(25.0, self.sample_segments))

        # 5. At 31.0s, speech 3 is active
        self.assertEqual(match_live_subtitle(31.0, self.sample_segments), "うわあああ！びっくりした！")

        # Verify that subtitle state evolved and did not remain stuck on speech 1
        distinct_subtitles = set(sub for _, sub in timeline_outputs if sub is not None)
        self.assertGreaterEqual(len(distinct_subtitles), 4)

if __name__ == '__main__':
    unittest.main()
