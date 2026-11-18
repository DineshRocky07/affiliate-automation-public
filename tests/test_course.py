"""Offline unit tests for affiliate-pro-course."""
import os
import tempfile
import unittest

from app.ajio_feed import fetch_feed_rows, merge_into_inventory, parse_feed
from app.ajio_provider import AjioProvider
from app.config import Settings
from app.content_checker import ContentRejected, check_caption_safety, enforce_caption_safety
from app.dashboard import _format_sheet_table
from app.deal_generator import make_safe_caption
from app.link_service import resolve_affiliate_link
from app.models import Product
from app.run_daily import acquire_lock, lock_is_active, release_lock
from app.shirts_publisher import build_shirt_caption, load_shirts, publish_shirts
from app.telegram_publisher import TelegramPublisher


class TestAffiliateCourse(unittest.TestCase):
    def setUp(self):
        self.ajio = AjioProvider(
            api_key="dummy",
            campaign_id=1,
            pub_id=16469,
            tracking_base="https://ajiotrk.vibconnect.in/click",
        )

    def test_ajio_link_generation(self):
        link = self.ajio.build_link("TEST1", "https://www.ajio.com/s/shoes")
        self.assertTrue(link.is_eligible)
        self.assertIn("pub_id=16469", link.tracking_url)
        self.assertIn("campaign_id=1", link.tracking_url)
        self.assertIn("p2=viodFallDeals", link.tracking_url)

    def test_ajio_requires_pub_id(self):
        provider = AjioProvider("dummy", 1, 0, "")
        link = provider.build_link("TEST1", "https://www.ajio.com/s/shoes")
        self.assertFalse(link.is_eligible)

    def test_non_ajio_rejected(self):
        link = self.ajio.build_link("TEST2", "https://www.flipkart.com/shoes")
        self.assertFalse(link.is_eligible)
        self.assertEqual(link.status, "rejected")

    def test_safe_caption_contains_disclosure(self):
        prod = Product("P1", "Test Shoes", "https://ajio.com/p", 999, 1999, "Shoes", price_verified=True)
        link = self.ajio.build_link("P1", "https://www.ajio.com/p")
        caption = make_safe_caption(prod, link)
        self.assertIn("Affiliate link", caption)
        self.assertIn("₹999", caption)

    def test_guardrails_detect_hype(self):
        prod = Product("P1", "Test Shoes", "https://ajio.com/p", 999, 1999)
        errors = check_caption_safety("Hurry loot lowest price", "Click now", prod)
        self.assertTrue(bool(errors))

    def test_enforce_caption_safety_raises(self):
        prod = Product("P1", "Test Shoes", "https://ajio.com/p", 999, 1999)
        with self.assertRaises(ContentRejected):
            enforce_caption_safety("Hurry loot", "No disclosure", prod)


class TestLinkService(unittest.TestCase):
    def _settings(self, **overrides):
        base = dict(
            ajio_pub_id=16469,
            ajio_campaign_id=1,
            ajio_tracking_base="https://ajiotrk.vibconnect.in/click",
            cuelinks_cid="12345",
        )
        base.update(overrides)
        return Settings(**base)

    def test_ajio_routed_to_ace(self):
        link = resolve_affiliate_link("P1", "https://www.ajio.com/x/p/123_blue", self._settings())
        self.assertTrue(link.is_eligible)
        self.assertEqual(link.provider, "ajio")
        self.assertIn("ajiotrk.vibconnect.in", link.tracking_url)
        self.assertIn("p1=deals_shirts", resolve_affiliate_link(
            "P1", "https://www.ajio.com/x/p/123_blue", self._settings(), subid="deals_shirts"
        ).tracking_url)

    def test_flipkart_blocked(self):
        link = resolve_affiliate_link("P1", "https://www.flipkart.com/x", self._settings())
        self.assertFalse(link.is_eligible)
        self.assertIn("Flipkart", link.reason)

    def test_cuelinks_needs_cid(self):
        ok = resolve_affiliate_link("P1", "https://www.amazon.in/dp/B0TEST", self._settings())
        self.assertTrue(ok.is_eligible)
        self.assertIn("cid=12345", ok.tracking_url)

        bad = resolve_affiliate_link("P1", "https://www.amazon.in/dp/B0TEST", self._settings(cuelinks_cid=""))
        self.assertFalse(bad.is_eligible)


class FakeDB:
    def __init__(self):
        self.posted = set()
        self.records = []

    def is_product_posted(self, product_id):
        return product_id in self.posted

    def record_post(self, **kwargs):
        self.records.append(kwargs)
        self.posted.add(kwargs["product_id"])
        return len(self.records)


class FakePublisher:
    def __init__(self):
        self.calls = []
        self.pinned = []

    def send_deal(self, caption, image_path=None, tracking_url=None):
        self.calls.append({"caption": caption, "image_path": image_path, "tracking_url": tracking_url})
        return {"ok": True, "message_id": len(self.calls)}

    def pin_message(self, message_id, disable_notification=True):
        self.pinned.append(message_id)
        return True


class TestShirtsPipeline(unittest.TestCase):
    def _write_csv(self, content):
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        self.addCleanup(os.remove, path)
        return path

    def test_load_shirts_validates(self):
        path = self._write_csv(
            "product_id,title,brand,category,price,mrp,image_url,url,price_verified\n"
            "P1,Test Shirt,Brand,Men Shirts,299,999,,https://www.ajio.com/t/p/P1_blue,true\n"
            "P2,Bad,Row,Men Shirts,abc,999,,https://www.ajio.com/t/p/P2,true\n"
            "P3,Other,Row,Men Shirts,299,999,,https://www.flipkart.com/t/p/P3,true\n"
        )
        rows, errors = load_shirts(path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(errors), 2)

    def test_publish_shirts_dedupes_and_posts(self):
        path = self._write_csv(
            "product_id,title,brand,category,price,mrp,image_url,url,price_verified\n"
            "P1,Test Shirt,Brand,Men Shirts,299,999,,https://www.ajio.com/t/p/P1_blue,true\n"
            "P1,Test Shirt,Brand,Men Shirts,299,999,,https://www.ajio.com/t/p/P1_blue,true\n"
        )
        settings = Settings(
            dry_run=False,
            ajio_pub_id=16469,
            ajio_campaign_id=1,
            ajio_tracking_base="https://ajiotrk.vibconnect.in/click",
            shirts_csv=path,
        )
        db = FakeDB()
        publisher = FakePublisher()
        result = publish_shirts(
            csv_path=path,
            max_posts=10,
            settings=settings,
            db=db,
            publisher=publisher,
            card_fn=lambda **kwargs: kwargs["output_path"],
            sleep_fn=lambda seconds: None,
        )
        self.assertEqual(result["posted"], 1)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(len(publisher.calls), 1)
        self.assertIn("ajiotrk.vibconnect.in", publisher.calls[0]["tracking_url"])
        self.assertIn("Affiliate link", publisher.calls[0]["caption"])
        self.assertEqual(len(db.records), 1)

    def test_shirt_caption_hides_unverified_price(self):
        product = Product("P1", "Test Shirt", "https://ajio.com/x", 299, 999, "Men Shirts", price_verified=False)
        caption = build_shirt_caption(product, "https://track.example")
        self.assertNotIn("Rs 299", caption)
        self.assertIn("Check the latest price", caption)

    def test_dry_run_does_not_write_db(self):
        path = self._write_csv(
            "product_id,title,brand,category,price,mrp,image_url,url,price_verified\n"
            "P1,Test Shirt,Brand,Men Shirts,299,999,,https://www.ajio.com/t/p/P1_blue,true\n"
        )
        settings = Settings(
            dry_run=True,
            ajio_pub_id=16469,
            ajio_campaign_id=1,
            ajio_tracking_base="https://ajiotrk.vibconnect.in/click",
            shirts_csv=path,
        )
        db = FakeDB()
        publisher = FakePublisher()
        result = publish_shirts(
            csv_path=path,
            max_posts=10,
            settings=settings,
            db=db,
            publisher=publisher,
            card_fn=lambda **kwargs: kwargs["output_path"],
            sleep_fn=lambda seconds: None,
        )
        self.assertEqual(result["posted"], 1)
        self.assertEqual(db.records, [])

    def test_top_brand_highlight_and_pinning(self):
        from app.shirts_publisher import extract_top_brand, publish_rows

        # 1. Brand detection
        self.assertEqual(extract_top_brand("DNMX Graphic Print T-Shirt"), "DNMX")
        self.assertEqual(
            extract_top_brand("Slim Fit Shirt", url="https://www.ajio.com/lee-cooper-men-shirt/p/123"),
            "LEE COOPER",
        )
        self.assertEqual(
            extract_top_brand("Running Shoes", url="https://www.ajio.com/campus-shoes/p/456"),
            "CAMPUS",
        )

        # 2. Caption highlighting (Regular discount < 70%)
        p = Product("P_DNMX", "DNMX Graphic Tee", "https://ajio.com/p1", 499, 999, "Men T-Shirts", price_verified=True)
        caption = build_shirt_caption(p, "https://track.example")
        self.assertIn("TOP BRAND: DNMX", caption)
        self.assertIn("Rs 499 ONLY", caption)
        self.assertIn("Affiliate link", caption)

        # 3. Mega clearance highlight for >=70% discount
        p_mega = Product("P_MEGA", "Lee Cooper Shirt", "https://ajio.com/lee-cooper/p2", 299, 1299, "Men Shirts", price_verified=True)
        mega_caption = build_shirt_caption(p_mega, "https://track.example")
        self.assertIn("LEE COOPER", mega_caption)
        self.assertIn("77% OFF", mega_caption)

        # 4. Auto-pinning hero deal
        settings = Settings(
            dry_run=False,
            ajio_pub_id=16469,
            ajio_campaign_id=1,
            ajio_tracking_base="https://ajiotrk.vibconnect.in/click",
        )
        db = FakeDB()
        publisher = FakePublisher()
        rows = [
            {
                "product_id": "AJIO-DNMX1",
                "title": "DNMX Crew Neck T-Shirt",
                "brand": "DNMX",
                "category": "Men T-Shirts",
                "price": 299,
                "mrp": 999,
                "image_url": "",
                "url": "https://www.ajio.com/dnmx-tshirt/p/DNMX1",
                "price_verified": True,
            }
        ]
        res = publish_rows(rows, max_posts=5, settings=settings, db=db, publisher=publisher, card_fn=lambda **kwargs: None, sleep_fn=lambda s: None)
        self.assertEqual(res["posted"], 1)
        self.assertEqual(res["pinned"], 1)
        self.assertEqual(len(publisher.pinned), 1)


class TestTelegramDryRun(unittest.TestCase):
    def test_dry_run_does_not_need_network(self):
        publisher = TelegramPublisher("dummy-token", "@test", dry_run=True)
        result = publisher.send_deal("Affiliate link test", tracking_url="https://example.com")
        self.assertTrue(result["dry_run"])


class FakeResponse:
    def __init__(self, text, content_type="application/json", status=200):
        self.text = text
        self.headers = {"Content-Type": content_type}
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


class TestAjioFeed(unittest.TestCase):
    def test_parse_json_feed_filters_and_normalizes(self):
        body = (
            '{"data":{"products":['
            '{"id":"111","name":"Men Shirt","brand":"DNMX","price":"Rs 499","mrp":"1,299",'
            '"image":"https://img/x.jpg","url":"https://www.ajio.com/a/p/111_blue"},'
            '{"id":"222","name":"Flipkart item","price":100,"mrp":200,"url":"https://www.flipkart.com/x"}'
            ']}}'
        )
        rows, errors = parse_feed(body)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["product_id"], "AJIO-111")
        self.assertEqual(rows[0]["price"], 499.0)
        self.assertEqual(rows[0]["mrp"], 1299.0)
        self.assertTrue(errors)

    def test_parse_csv_feed(self):
        text = (
            "title,url,price,mrp,brand,image_url,product_id\n"
            "Cotton Shirt,https://www.ajio.com/b/p/333_red,299,999,RIO,https://img/y.jpg,333\n"
        )
        rows, _ = parse_feed(text, content_type="text/csv")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["product_id"], "AJIO-333")

    def test_fetch_sends_api_key_and_merges_deduped(self):
        body = '{"items":[{"id":"9","title":"Shirt","price":199,"mrp":499,"url":"https://www.ajio.com/c/p/9_x"}]}'
        session = FakeSession(FakeResponse(body))
        rows, errors = fetch_feed_rows("https://feed.example/ajio", api_key="secret", session=session)
        self.assertEqual(len(rows), 1)
        self.assertFalse(errors)
        _, kwargs = session.calls[0]
        self.assertEqual(kwargs["headers"]["X-Api-Key"], "secret")
        self.assertEqual(kwargs["params"]["apiKey"], "secret")

        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        self.addCleanup(os.remove, path)
        self.assertEqual(merge_into_inventory(rows, path), 1)
        self.assertEqual(merge_into_inventory(rows, path), 0)

    def test_missing_feed_url_is_safe(self):
        rows, errors = fetch_feed_rows("", api_key="secret")
        self.assertEqual(rows, [])
        self.assertTrue(errors)


class TestDailyLock(unittest.TestCase):
    def test_lock_blocks_and_stale_lock_is_ignored(self):
        fd, path = tempfile.mkstemp(suffix=".lock")
        os.close(fd)
        os.remove(path)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))

        self.assertTrue(acquire_lock(path))
        self.assertTrue(lock_is_active(path))
        self.assertFalse(acquire_lock(path))
        release_lock(path)
        self.assertFalse(lock_is_active(path))

        with open(path, "w", encoding="utf-8") as f:
            f.write('{"started": 1}')
        self.assertFalse(lock_is_active(path, stale_seconds=60, now=10_000))


class TestDashboardHelpers(unittest.TestCase):
    def test_format_sheet_table_handles_verified_and_unverified_prices(self):
        rows = [
            {
                "product_id": "AJIO-1",
                "title": "Tee",
                "price": 300.0,
                "mrp": 1000.0,
                "price_verified": True,
                "image_url": "https://assets.ajio.com/a.jpg",
            },
            {
                "product_id": "AJIO-2",
                "title": "Shirt",
                "price": 0.0,
                "mrp": 0.0,
                "price_verified": False,
                "image_url": "",
            },
        ]
        table = _format_sheet_table(rows)
        self.assertEqual(table[0]["Deal Price"], "Rs 300")
        self.assertEqual(table[0]["Discount"], "70%")
        self.assertEqual(table[0]["Has Image"], "Yes")
        self.assertEqual(table[1]["Deal Price"], "Check Store")
        self.assertEqual(table[1]["Has Image"], "No")


if __name__ == "__main__":
    unittest.main()
