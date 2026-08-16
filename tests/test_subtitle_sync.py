import json
import unittest

def match_live_subtitle(current_time, video_segments, tolerance=0.2):
    """
    Python implementation of the frontend live subtitle matching logic in index.html:
    currentTime >= (s.start - 0.2) && currentTime <= (s.end + 0.2)
    """
    if not video_segments:
        return None
    for seg in video_segments:
        if (seg["start"] - tolerance) <= current_time <= (seg["end"] + tolerance):
            return seg["text"]
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

        # Just after end (15.15s)
        text = match_live_subtitle(15.15, self.sample_segments, tolerance=0.2)
        self.assertEqual(text, "はじめまして、よろしくおねがいします。")

    def test_live_subtitle_no_speech_gap(self):
        """Tests returns None when current time falls into silence / BGM interval."""
        text = match_live_subtitle(25.0, self.sample_segments)
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
        self.assertTrue(res_pause["should_pause"])

if __name__ == '__main__':
    unittest.main()
