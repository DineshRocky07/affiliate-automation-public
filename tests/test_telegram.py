"""Offline tests for Telegram photo/text fallback behaviour."""
import os
import tempfile
import unittest
from unittest.mock import patch

from app.telegram_publisher import TelegramPublisher


class FakeTelegramResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(
                f"HTTP {self.status_code}: {self._payload.get('description', '')}"
            )


def _temp_jpg(test_case):
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    test_case.addCleanup(os.remove, path)
    return path


class TestTelegramPhotoFallback(unittest.TestCase):
    def test_photo_failure_falls_back_to_text(self):
        calls = []

        def fake_post(url, **kwargs):
            calls.append(url)
            if url.endswith("/sendPhoto"):
                return FakeTelegramResponse(
                    400, {"ok": False, "description": "Bad Request: IMAGE_PROCESS_FAILED"}
                )
            return FakeTelegramResponse(200, {"ok": True, "result": {"message_id": 7}})

        publisher = TelegramPublisher(
            "dummy-token", "@test", dry_run=False, max_retries=1, sleep_fn=lambda _s: None
        )
        image_path = _temp_jpg(self)

        with patch("app.telegram_publisher.requests.post", side_effect=fake_post):
            result = publisher.send_deal(
                "Deal caption", image_path=image_path, tracking_url="https://example.com"
            )

        self.assertEqual(result["result"]["message_id"], 7)
        self.assertTrue(any(url.endswith("/sendPhoto") for url in calls))
        self.assertTrue(any(url.endswith("/sendMessage") for url in calls))

    def test_photo_is_used_when_telegram_accepts_it(self):
        calls = []

        def fake_post(url, **kwargs):
            calls.append(url)
            return FakeTelegramResponse(200, {"ok": True, "result": {"message_id": 8}})

        publisher = TelegramPublisher(
            "dummy-token", "@test", dry_run=False, max_retries=1, sleep_fn=lambda _s: None
        )
        image_path = _temp_jpg(self)

        with patch("app.telegram_publisher.requests.post", side_effect=fake_post):
            result = publisher.send_deal("Deal caption", image_path=image_path)

        self.assertEqual(result["result"]["message_id"], 8)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].endswith("/sendPhoto"))

    def test_long_caption_skips_photo(self):
        calls = []

        def fake_post(url, **kwargs):
            calls.append(url)
            return FakeTelegramResponse(200, {"ok": True, "result": {"message_id": 9}})

        publisher = TelegramPublisher(
            "dummy-token", "@test", dry_run=False, max_retries=1, sleep_fn=lambda _s: None
        )
        image_path = _temp_jpg(self)

        with patch("app.telegram_publisher.requests.post", side_effect=fake_post):
            publisher.send_deal("x" * 1500, image_path=image_path)

        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].endswith("/sendMessage"))

    def test_dry_run_never_calls_telegram(self):
        publisher = TelegramPublisher("dummy-token", "@test", dry_run=True)
        with patch("app.telegram_publisher.requests.post") as mocked:
            result = publisher.send_deal("Deal caption", tracking_url="https://example.com")
        mocked.assert_not_called()
        self.assertTrue(result["dry_run"])


if __name__ == "__main__":
    unittest.main()
