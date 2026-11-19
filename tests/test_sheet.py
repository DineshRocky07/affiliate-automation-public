"""Offline tests for the Google Sheet inbox and seen-products dedupe."""
import csv
import io
import os
import tempfile
import unittest

from app.config import Settings
from app.db import Database
from app.google_sheet_source import (
    append_sheet_row,
    clear_processed_rows,
    clear_processed_rows_api,
    fetch_sheet_rows,
    fetch_sheet_rows_api,
    load_sheet_rows,
    notify_sheet_clear,
    parse_sheet,
)
from app.shirts_publisher import publish_rows


class FakeResponse:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.response

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.response


class FakeDB:
    def __init__(self):
        self.posted = set()
        self.seen = {}
        self.records = []

    def is_product_posted(self, product_id):
        return product_id in self.posted

    def is_seen(self, product_id, include_dry_run=True):
        if product_id not in self.seen:
            return False
        return include_dry_run or not self.seen[product_id]

    def mark_seen(self, product_id, dry_run=False):
        self.seen[product_id] = dry_run

    def record_post(self, **kwargs):
        self.records.append(kwargs)
        self.posted.add(kwargs["product_id"])
        return len(self.records)


class FakePublisher:
    def __init__(self):
        self.calls = []

    def send_deal(self, caption, image_path=None, tracking_url=None):
        self.calls.append({"caption": caption, "image_path": image_path, "tracking_url": tracking_url})
        return {"ok": True, "message_id": len(self.calls)}


def _settings(dry_run=True):
    return Settings(
        dry_run=dry_run,
        ajio_pub_id=12345,
        ajio_campaign_id=1,
        ajio_tracking_base="https://ajiotrk.vibconnect.in/click",
    )


class TestSheetParsing(unittest.TestCase):
    def test_accepts_header_variants_and_optional_price(self):
        text = (
            "Title,Link,Price,MRP,Image\n"
            "Test Shirt,https://www.ajio.com/p/111_blue,299,999,https://assets.ajio.com/x.jpg\n"
            "No Price,https://www.ajio.com/p/222_red,,,\n"
        )
        rows, errors = parse_sheet(text)
        self.assertEqual(len(rows), 2)
        self.assertFalse(errors)
        self.assertTrue(rows[0]["price_verified"])
        self.assertEqual(rows[0]["price"], 299.0)
        self.assertFalse(rows[1]["price_verified"])
        self.assertEqual(rows[1]["price"], 0.0)
        self.assertEqual(rows[1]["product_id"], "AJIO-222_red")

    def test_strips_empty_trailing_question_mark_on_url(self):
        text = (
            "title,url,price,mrp\n"
            "Oversized Tee,https://www.ajio.com/x/p/703488518_black?,300,1999\n"
        )
        rows, errors = parse_sheet(text)
        self.assertFalse(errors)
        self.assertEqual(rows[0]["url"], "https://www.ajio.com/x/p/703488518_black")

    def test_rejects_flipkart_and_non_ajio(self):
        text = (
            "title,url,platform\n"
            "FK,https://www.flipkart.com/x,\n"
            "AMZ,https://www.amazon.in/dp/B0TEST,amazon\n"
            "Other,https://example.com/p/1,ajio\n"
        )
        rows, errors = parse_sheet(text)
        self.assertEqual(rows, [])
        self.assertEqual(len(errors), 3)
        self.assertIn("Flipkart", errors[0])
        self.assertIn("only AJIO", errors[1])
        self.assertIn("ajio.com", errors[2])

    def test_dedupes_product_id(self):
        text = (
            "title,url\n"
            "One,https://www.ajio.com/p/333_blue\n"
            "Two,https://www.ajio.com/p/333_blue\n"
        )
        rows, errors = parse_sheet(text)
        self.assertEqual(len(rows), 1)
        self.assertTrue(any("duplicate" in err for err in errors))

    def test_keeps_external_https_image(self):
        text = (
            "title,url,image_url\n"
            "One,https://www.ajio.com/p/444_blue,https://images.unsplash.com/x.jpg\n"
        )
        rows, _ = parse_sheet(text)
        self.assertEqual(rows[0]["image_url"], "https://images.unsplash.com/x.jpg")

    def test_accepts_human_readable_header_names(self):
        text = (
            "Product Name,Product Link,Selling Price,Original Price,Image URL,Brand Name,Product Category\n"
            "Test Shirt,https://www.ajio.com/p/333_blue,Rs 299,999,https://cdn.example.com/x.jpg,DNMX,Men Shirts\n"
        )
        rows, errors = parse_sheet(text)
        self.assertFalse(errors)
        row = rows[0]
        self.assertEqual(row["title"], "Test Shirt")
        self.assertEqual(row["price"], 299.0)
        self.assertEqual(row["mrp"], 999.0)
        self.assertTrue(row["price_verified"])
        self.assertEqual(row["image_url"], "https://cdn.example.com/x.jpg")
        self.assertEqual(row["brand"], "DNMX")
        self.assertEqual(row["category"], "Men Shirts")

    def test_extracts_google_sheets_image_formula(self):
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["title", "url", "image"])
        writer.writerow([
            "One",
            "https://www.ajio.com/p/444_blue",
            '=IMAGE("https://assets.ajio.com/x.jpg")',
        ])
        rows, errors = parse_sheet(buffer.getvalue())
        self.assertFalse(errors)
        self.assertEqual(rows[0]["image_url"], "https://assets.ajio.com/x.jpg")

    def test_fetch_sheet_rows_uses_session(self):
        session = FakeSession(FakeResponse("title,url\nOne,https://www.ajio.com/p/555_blue\n"))
        rows, errors = fetch_sheet_rows("https://docs.google.com/sheet.csv", session=session)
        self.assertEqual(len(rows), 1)
        self.assertFalse(errors)
        self.assertEqual(session.calls[0][1], "https://docs.google.com/sheet.csv")

    def test_missing_sheet_url_is_safe(self):
        rows, errors = fetch_sheet_rows("")
        self.assertEqual(rows, [])
        self.assertTrue(errors)


class TestSeenLedger(unittest.TestCase):
    def test_dry_run_marks_seen_but_not_posted(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(os.remove, path)

        db = Database(path)
        db.init()
        self.assertFalse(db.is_seen("AJIO-1"))
        db.mark_seen("AJIO-1", dry_run=True)
        self.assertTrue(db.is_seen("AJIO-1"))
        self.assertTrue(db.is_seen("AJIO-1", include_dry_run=True))
        self.assertFalse(db.is_seen("AJIO-1", include_dry_run=False))
        self.assertFalse(db.is_product_posted("AJIO-1"))

    def test_report_counts_posts_seen_and_top(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(os.remove, path)

        db = Database(path)
        db.init()
        db.record_post("AJIO-1", "ajio", "https://x/1", "Head", "Cap", 10)
        db.record_post("AJIO-1", "ajio", "https://x/1", "Head", "Cap", 11)
        db.record_post("AJIO-2", "ajio", "https://x/2", "Head", "Cap", 12)
        db.mark_seen("AJIO-3", dry_run=True)

        r = db.report(limit=5)
        self.assertEqual(r["posts"], 3)
        self.assertEqual(r["seen"], 1)
        self.assertEqual(r["dry_run_seen"], 1)
        self.assertEqual(len(r["recent"]), 3)
        self.assertEqual(r["top"][0]["product_id"], "AJIO-1")
        self.assertEqual(r["top"][0]["posts"], 2)
        self.assertEqual(r["metrics"]["rows"], 0)

    def test_reset_history_clears_posts_seen_and_metrics(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(os.remove, path)

        db = Database(path)
        db.init()
        post_id = db.record_post("AJIO-5", "ajio", "https://x/5", "Head", "Cap", 1)
        db.mark_seen("AJIO-6", dry_run=False)
        db.record_commission(post_id, 12.0)

        cleared = db.reset_history()

        self.assertEqual(cleared["posts"], 1)
        self.assertEqual(cleared["seen"], 1)
        self.assertEqual(cleared["metrics"], 1)
        report = db.report()
        self.assertEqual(report["posts"], 0)
        self.assertEqual(report["seen"], 0)
        self.assertEqual(report["metrics"]["rows"], 0)

    def test_commission_overwrites_and_counts_this_month(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(os.remove, path)

        db = Database(path)
        db.init()
        post_id = db.record_post("AJIO-9", "ajio", "https://x/9", "Head", "Cap", 1)
        self.assertTrue(db.post_exists(post_id))
        self.assertFalse(db.post_exists(999))

        db.record_commission(post_id, 45.5)
        self.assertAlmostEqual(db.commission_this_month(), 45.5)
        db.record_commission(post_id, 50.0)
        self.assertAlmostEqual(db.commission_this_month(), 50.0)
        self.assertAlmostEqual(db.report()["commission_month"], 50.0)
        self.assertEqual(db.report()["metrics"]["rows"], 1)


class TestPublishRows(unittest.TestCase):
    def test_dry_run_does_not_repeat_rows(self):
        rows, _ = parse_sheet(
            "title,url,price,mrp\n"
            "Test Shirt,https://www.ajio.com/p/666_blue,299,999\n"
        )
        db = FakeDB()
        publisher = FakePublisher()
        settings = _settings(dry_run=True)

        first = publish_rows(rows, settings=settings, db=db, publisher=publisher)
        second = publish_rows(rows, settings=settings, db=db, publisher=publisher)

        self.assertEqual(first["posted"], 1)
        self.assertEqual(second["posted"], 0)
        self.assertEqual(second["skipped"], 1)
        self.assertEqual(len(publisher.calls), 1)
        self.assertEqual(db.records, [])

    def test_live_run_ignores_dry_run_previews(self):
        rows, _ = parse_sheet(
            "title,url,price,mrp\n"
            "Test Shirt,https://www.ajio.com/p/778_blue,299,999\n"
        )
        db = FakeDB()
        publisher = FakePublisher()

        preview = publish_rows(rows, settings=_settings(dry_run=True), db=db, publisher=publisher)
        live = publish_rows(rows, settings=_settings(dry_run=False), db=db, publisher=publisher)

        self.assertEqual(preview["posted"], 1)
        self.assertEqual(live["posted"], 1)
        self.assertEqual(len(db.records), 1)

    def test_live_run_records_post(self):
        rows, _ = parse_sheet(
            "title,url,price,mrp\n"
            "Test Shirt,https://www.ajio.com/p/777_blue,299,999\n"
        )
        db = FakeDB()
        publisher = FakePublisher()
        result = publish_rows(rows, settings=_settings(dry_run=False), db=db, publisher=publisher)
        self.assertEqual(result["posted"], 1)
        self.assertEqual(len(db.records), 1)
        self.assertIn("ajiotrk.vibconnect.in", publisher.calls[0]["tracking_url"])

    def test_all_failures_mark_run_as_error(self):
        class FailingPublisher:
            def send_deal(self, caption, image_path=None, tracking_url=None):
                raise ValueError("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing")

        rows, _ = parse_sheet(
            "title,url,price,mrp\n"
            "Test Shirt,https://www.ajio.com/p/999_blue,299,999\n"
        )
        result = publish_rows(
            rows,
            settings=_settings(dry_run=False),
            db=FakeDB(),
            publisher=FailingPublisher(),
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["posted"], 0)
        self.assertTrue(any("TELEGRAM_BOT_TOKEN" in err for err in result["errors"]))

    def test_force_reposts_seen_row(self):
        rows, _ = parse_sheet(
            "title,url,price,mrp\n"
            "Test Shirt,https://www.ajio.com/p/888_blue,299,999\n"
        )
        db = FakeDB()
        publisher = FakePublisher()
        settings = _settings(dry_run=False)

        first = publish_rows(rows, settings=settings, db=db, publisher=publisher)
        second = publish_rows(rows, settings=settings, db=db, publisher=publisher)
        forced = publish_rows(rows, settings=settings, db=db, publisher=publisher, force=True)

        self.assertEqual(first["posted"], 1)
        self.assertEqual(second["posted"], 0)
        self.assertEqual(forced["posted"], 1)
        self.assertEqual(len(publisher.calls), 2)

    def test_zero_max_posts_means_post_whole_batch(self):
        rows, _ = parse_sheet(
            "title,url,price,mrp\n"
            "Shirt A,https://www.ajio.com/p/a_blue,299,999\n"
            "Shirt B,https://www.ajio.com/p/b_blue,399,999\n"
            "Shirt C,https://www.ajio.com/p/c_blue,499,999\n"
        )
        publisher = FakePublisher()
        result = publish_rows(
            rows,
            max_posts=0,
            settings=_settings(dry_run=True),
            db=FakeDB(),
            publisher=publisher,
        )
        self.assertEqual(result["posted"], 3)
        self.assertEqual(len(publisher.calls), 3)


class FakeWorksheet:
    def __init__(self, records=None, values=None):
        self.records = records or []
        self.values = values or []
        self.deleted = []
        self.appended = []

    def get_all_records(self):
        return self.records

    def get_all_values(self):
        return self.values

    def delete_rows(self, row_number):
        self.deleted.append(row_number)

    def append_row(self, row, value_input_option=None):
        self.appended.append((row, value_input_option))


class FakeSpreadsheet:
    def __init__(self, worksheet):
        self.worksheet_obj = worksheet

    def worksheet(self, name):
        return self.worksheet_obj


class FakeClient:
    def __init__(self, worksheet):
        self.worksheet_obj = worksheet

    def open_by_key(self, sheet_id):
        return FakeSpreadsheet(self.worksheet_obj)


class TestServiceAccountSheet(unittest.TestCase):
    def _credentials(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        self.addCleanup(os.remove, path)
        return path

    def test_fetch_rows_via_api(self):
        ws = FakeWorksheet(records=[
            {"title": "Shirt", "url": "https://www.ajio.com/p/888_blue", "price": "199", "mrp": "499"},
        ])
        rows, errors = fetch_sheet_rows_api(
            "sheet-id", "deals", self._credentials(),
            client_factory=lambda _path: FakeClient(ws),
        )
        self.assertEqual(len(rows), 1)
        self.assertFalse(errors)
        self.assertEqual(rows[0]["product_id"], "AJIO-888_blue")
        self.assertTrue(rows[0]["price_verified"])

    def test_clear_deletes_posted_rows_descending(self):
        ws = FakeWorksheet(values=[
            ["title", "url", "price"],
            ["A", "https://www.ajio.com/p/111_blue", "199"],
            ["B", "https://www.ajio.com/p/222_red", "299"],
            ["C", "https://www.ajio.com/p/333_blue", "399"],
        ])
        count = clear_processed_rows_api(
            "sheet-id", "deals", self._credentials(),
            ["AJIO-111_blue", "AJIO-333_blue"],
            client_factory=lambda _path: FakeClient(ws),
        )
        self.assertEqual(count, 2)
        self.assertEqual(ws.deleted, [4, 2])

    def test_load_sheet_rows_falls_back_to_csv_when_credentials_missing(self):
        session = FakeSession(FakeResponse("title,url\nOne,https://www.ajio.com/p/555_blue\n"))
        settings = Settings(
            google_sheet_id="sheet-id",
            google_worksheet="deals",
            google_credentials_file="missing-credentials.json",
            google_sheet_csv_url="https://docs.google.com/sheet.csv",
        )
        rows, errors = load_sheet_rows(settings, session=session)
        self.assertEqual(len(rows), 1)
        self.assertFalse(errors)
        self.assertEqual(session.calls[0][1], "https://docs.google.com/sheet.csv")

    def test_load_sheet_rows_explains_missing_credentials(self):
        settings = Settings(
            google_sheet_id="sheet-id",
            google_worksheet="deals",
            google_credentials_file="missing-credentials.json",
        )
        rows, errors = load_sheet_rows(settings)
        self.assertEqual(rows, [])
        self.assertIn("Credentials file not found", errors[0])

    def test_load_sheet_rows_prefers_service_account(self):
        ws = FakeWorksheet(records=[
            {"title": "Shirt", "url": "https://www.ajio.com/p/999_blue"},
        ])
        settings = Settings(
            google_sheet_id="sheet-id",
            google_worksheet="deals",
            google_credentials_file=self._credentials(),
            google_sheet_csv_url="https://example.com/should-not-be-used.csv",
        )
        rows, errors = load_sheet_rows(
            settings, client_factory=lambda _path: FakeClient(ws)
        )
        self.assertEqual(len(rows), 1)
        self.assertFalse(errors)

    def test_clear_processed_rows_uses_api(self):
        ws = FakeWorksheet(values=[
            ["title", "url"],
            ["A", "https://www.ajio.com/p/123_blue"],
        ])
        settings = Settings(
            google_sheet_id="sheet-id",
            google_worksheet="deals",
            google_credentials_file=self._credentials(),
        )
        count = clear_processed_rows(
            settings, ["AJIO-123_blue"], client_factory=lambda _path: FakeClient(ws)
        )
        self.assertEqual(count, 1)
        self.assertEqual(ws.deleted, [2])

    def test_missing_credentials_file_is_safe(self):
        rows, errors = fetch_sheet_rows_api("sheet-id", "deals", "missing.json")
        self.assertEqual(rows, [])
        self.assertTrue(errors)

    def test_append_sheet_row_validates_and_appends(self):
        ws = FakeWorksheet(values=[["title", "url", "price", "mrp", "image_url", "platform"]])
        settings = Settings(
            google_sheet_id="sheet-id",
            google_worksheet="deals",
            google_credentials_file=self._credentials(),
        )
        saved, err = append_sheet_row(
            settings,
            title="New AJIO Tee",
            url="https://www.ajio.com/x/p/999_black?",
            price="299",
            mrp="999",
            image_url="https://assets-jiocdn.ajio.com/img.jpg",
            client_factory=lambda _path: FakeClient(ws),
        )
        self.assertIsNone(err)
        self.assertEqual(saved["product_id"], "AJIO-999_black")
        self.assertEqual(saved["url"], "https://www.ajio.com/x/p/999_black")
        self.assertEqual(len(ws.appended), 1)
        self.assertEqual(ws.appended[0][0][0], "New AJIO Tee")

    def test_append_sheet_row_rejects_flipkart(self):
        ws = FakeWorksheet(values=[["title", "url"]])
        settings = Settings(
            google_sheet_id="sheet-id",
            google_worksheet="deals",
            google_credentials_file=self._credentials(),
        )
        saved, err = append_sheet_row(
            settings,
            title="Flipkart Item",
            url="https://www.flipkart.com/p/123",
            client_factory=lambda _path: FakeClient(ws),
        )
        self.assertIsNone(saved)
        self.assertIn("Flipkart", err)
        self.assertEqual(ws.appended, [])


class TestSheetClearWebhook(unittest.TestCase):
    def test_posts_processed_ids(self):
        session = FakeSession(FakeResponse("ok"))
        ok = notify_sheet_clear("https://script.google.com/macros/x", ["AJIO-1"], "secret", session=session)
        self.assertTrue(ok)
        method, url, kwargs = session.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(kwargs["json"]["action"], "clear")
        self.assertEqual(kwargs["json"]["product_ids"], ["AJIO-1"])

    def test_noop_without_ids(self):
        self.assertFalse(notify_sheet_clear("https://script.google.com/macros/x", []))


if __name__ == "__main__":
    unittest.main()
