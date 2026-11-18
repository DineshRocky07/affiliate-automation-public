"""Telegram publisher: photos/messages, inline buttons, dry-run and 429 backoff."""
import json
import logging
import os
import sys
import time

import requests

log = logging.getLogger(__name__)

PHOTO_CAPTION_LIMIT = 1024


def _safe_print(text: str) -> None:
    encoding = sys.stdout.encoding or "utf-8"
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode(encoding, errors="replace").decode(encoding, errors="replace"))


class TelegramPublisher:
    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        dry_run: bool = True,
        max_retries: int = 4,
        sleep_fn=time.sleep,
    ):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.dry_run = dry_run
        self.max_retries = max_retries
        self.sleep_fn = sleep_fn
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    def send_deal(self, caption: str, image_path: str = None, tracking_url: str = None) -> dict:
        """Send a deal as a photo (preferred) or text, with an optional buy button."""
        if self.dry_run:
            _safe_print("\n" + "=" * 62)
            _safe_print(f"[DRY-RUN PREVIEW] -> Target: {self.chat_id}")
            _safe_print(f"Attached Image    -> {image_path or 'No image'}")
            _safe_print("-" * 62)
            _safe_print(caption)
            if tracking_url:
                _safe_print(f"[INLINE BUTTON]: BUY NOW -> {tracking_url}")
            _safe_print("=" * 62 + "\n")
            return {"ok": True, "dry_run": True, "message_id": 99999}

        if not self.bot_token or not self.chat_id:
            raise ValueError("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing in .env")

        reply_markup = self._build_markup(tracking_url)

        if (
            image_path
            and os.path.exists(image_path)
            and len(caption) <= PHOTO_CAPTION_LIMIT
        ):
            try:
                return self._send_photo(caption, image_path, reply_markup)
            except Exception as exc:
                log.warning(
                    "sendPhoto failed for %s (%s). Falling back to a text post so the deal is not lost.",
                    image_path,
                    exc,
                )

        return self._send_message(caption, reply_markup)

    def pin_message(self, message_id: int, disable_notification: bool = True) -> bool:
        """Pin a message to the top of the Telegram channel."""
        if not message_id or message_id == 99999:
            return True
        if self.dry_run:
            _safe_print(f"[DRY-RUN] Pinned message ID: {message_id}")
            return True
        url = f"{self.base_url}/pinChatMessage"
        payload = {
            "chat_id": self.chat_id,
            "message_id": message_id,
            "disable_notification": disable_notification,
        }
        try:
            r = requests.post(url, json=payload, timeout=15)
            if r.status_code == 200:
                log.info("Successfully pinned deal message %s in %s", message_id, self.chat_id)
                return True
            log.warning("Could not pin message %s (HTTP %s): %s", message_id, r.status_code, r.text)
            return False
        except Exception as exc:
            log.warning("pinChatMessage error for message %s: %s", message_id, exc)
            return False

    def _build_markup(self, tracking_url):
        if not tracking_url:
            return None
        channel_url = (
            f"https://t.me/{self.chat_id.lstrip('@')}"
            if self.chat_id and self.chat_id.startswith("@")
            else "https://t.me/viodFallDeals"
        )
        return {
            "inline_keyboard": [
                [{"text": "ORDER NOW (OFFICIAL STORE)", "url": tracking_url}],
                [{"text": "More Top Deals", "url": channel_url}],
            ]
        }

    def _send_photo(self, caption, image_path, reply_markup):
        url = f"{self.base_url}/sendPhoto"
        data = {
            "chat_id": self.chat_id,
            "caption": caption,
            "parse_mode": "HTML",
        }
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup)

        last = None
        for attempt in range(self.max_retries):
            with open(image_path, "rb") as photo_file:
                last = requests.post(url, data=data, files={"photo": photo_file}, timeout=30)
            if self._should_retry(last, attempt):
                continue
            self._raise_for_telegram_error(last, "sendPhoto")
            return last.json()

        self._raise_for_telegram_error(last, "sendPhoto")
        return last.json()

    def _send_message(self, caption, reply_markup):
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": caption,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        last = None
        for attempt in range(self.max_retries):
            last = requests.post(url, json=payload, timeout=25)
            if self._should_retry(last, attempt):
                continue
            self._raise_for_telegram_error(last, "sendMessage")
            return last.json()

        self._raise_for_telegram_error(last, "sendMessage")
        return last.json()

    @staticmethod
    def _raise_for_telegram_error(response, method: str) -> None:
        """Log Telegram's own error description, then raise the HTTP error."""
        if response is None or response.status_code < 400:
            return
        description = ""
        try:
            description = str(response.json().get("description", ""))
        except Exception:
            description = ""
        log.error(
            "Telegram %s failed: HTTP %s%s",
            method,
            response.status_code,
            f" - {description}" if description else "",
        )
        response.raise_for_status()

    def _should_retry(self, response, attempt: int) -> bool:
        if attempt >= self.max_retries - 1:
            return False

        if response.status_code == 429:
            retry_after = 5
            try:
                retry_after = int(response.json().get("parameters", {}).get("retry_after", 5))
            except Exception:
                pass
            log.warning("Telegram flood control: retrying in %ss", retry_after)
            self.sleep_fn(retry_after + 1)
            return True

        if response.status_code >= 500:
            backoff = 2 ** attempt
            log.warning("Telegram server error %s: retrying in %ss", response.status_code, backoff)
            self.sleep_fn(backoff)
            return True

        return False
