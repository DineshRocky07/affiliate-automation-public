// ==============================================================================
// 🛍️ AJIO ALL-IN-ONE BROWSER SCRAPER & DIRECT SHEET PUSHER
// ==============================================================================
// How to use:
// 1. Open Chrome and go to: https://www.ajio.com
// 2. Press F12 -> Go to "Console" tab
// 3. Paste your Apps Script Web App URL into SHEET_WEBAPP_URL below (if you deployed it)
// 4. Paste this ENTIRE code into Console and press ENTER
//
// What it does:
// - Scrapes Men, Women, Kids, 50%+ Offers, Top Brands, New Arrivals
// - Deduplicates using localStorage (never scrapes yesterday's deals)
// - Directs all new deals straight to your Google Sheet (no copy-pasting needed!)
// - Also downloads a backup CSV automatically!
// ==============================================================================

(async function runAjioScraper() {
  // 🔗 Paste your deployed Google Apps Script Web App URL here:
  // (Leave empty "" if you only want to download CSV)
  const SHEET_WEBAPP_URL = ""; 

  // 🎯 Categories to scrape
  const SOURCES = [
    {
      label: "Offers 50%+ Off",
      url: "https://www.ajio.com/api/curated/min50percentoff-curated-437897?fields=SITE&format=json&curated=true&curatedid=min50percentoff-curated-437897&platform=Msite&store=ajio&gridColumns=2&advfilter=true"
    },
    {
      label: "Men - Shirts & Topwear",
      url: "https://www.ajio.com/api/category/830216001?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true"
    },
    {
      label: "Men - T-Shirts",
      url: "https://www.ajio.com/api/category/830216010?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true"
    },
    {
      label: "Women - Kurtas & Dresses",
      url: "https://www.ajio.com/api/category/830303011?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true"
    },
    {
      label: "Women - Westernwear Tops",
      url: "https://www.ajio.com/api/category/830303002?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true"
    },
    {
      label: "Kids Wear",
      url: "https://www.ajio.com/api/category/830401?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true"
    },
    {
      label: "Top Brands Sale",
      url: "https://www.ajio.com/api/curated/under-499-curated?fields=SITE&format=json&curated=true&platform=Msite&store=ajio&gridColumns=2&advfilter=true"
    }
  ];

  const MAX_PAGES_PER_CATEGORY = 4; // 4 pages * 45 = 180 products per category
  const STOP_AFTER_EMPTY_PAGES = 2; // stop category if 2 pages have no new deals
  const MIN_DISCOUNT_PCT = 40;      // only pick deals with >= 40% discount
  const SLEEP_MS = 1200;            // pause between requests

  const STORAGE_KEY = "ajio_seen_ids_v2";
  let seenOld = new Set();
  try {
    seenOld = new Set(JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]"));
  } catch (e) {}

  const seenNow = new Set();
  const allRows = [];
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const esc = v => '"' + String(v ?? "").replace(/"/g, '""') + '"';

  function buildUrl(base, page) {
    const u = new URL(base);
    u.searchParams.set("currentPage", page);
    u.searchParams.set("pageSize", 45);
    u.searchParams.set("sort", "newn"); // Sort by What's New
    u.searchParams.delete("visitorId");
    u.searchParams.delete("userEncryptedId");
    return u.toString();
  }

  console.log(`%c🚀 AJIO Scraper Started! (Known historical items: ${seenOld.size})`, "color: #00ff88; font-weight: bold; font-size: 14px;");

  for (const src of SOURCES) {
    console.log(`%c📂 Checking Category: ${src.label}`, "color: #38bdf8; font-weight: bold;");
    let emptyPages = 0;

    for (let page = 0; page < MAX_PAGES_PER_CATEGORY; page++) {
      try {
        const targetUrl = buildUrl(src.url, page);
        const resp = await fetch(targetUrl, { credentials: "include" });

        if (!resp.ok) {
          console.warn(`[${src.label}] Page ${page + 1} HTTP ${resp.status}`);
          break;
        }

        const data = await resp.json();
        const products = data.products || [];
        if (!products.length) break;

        let newOnPage = 0;
        for (const p of products) {
          const id = p.code || p.url;
          const url = p.url ? "https://www.ajio.com" + p.url : "";
          const price = Number(p.price?.value ?? 0);
          const mrp = Number(p.wasPriceData?.value ?? 0);
          const title = (p.name || "").trim();
          const img = p.images?.[0]?.url 
            ? (p.images[0].url.startsWith("http") ? p.images[0].url : "https://assets.ajio.com" + p.images[0].url)
            : (p.fnlColorVariantData?.outfitPictureURL || "");

          if (!id || !url || price <= 0 || mrp <= price) continue;

          const discount = Math.round(((mrp - price) / mrp) * 100);
          if (discount < MIN_DISCOUNT_PCT) continue;

          if (seenOld.has(id) || seenNow.has(id)) continue;

          seenNow.add(id);
          newOnPage++;
          allRows.push({
            id: id,
            title: title,
            url: url,
            price: price,
            mrp: mrp,
            discount: discount,
            image_url: img,
            platform: "ajio"
          });
        }

        console.log(`   Page ${page + 1}: Found ${newOnPage} new deals (${allRows.length} total collected)`);

        emptyPages = (newOnPage === 0) ? emptyPages + 1 : 0;
        if (emptyPages >= STOP_AFTER_EMPTY_PAGES) {
          console.log(`   ⏩ No more new items in ${src.label}, moving to next category...`);
          break;
        }

        await sleep(SLEEP_MS + Math.random() * 800);
      } catch (err) {
        console.error(`Error on page ${page}:`, err);
        break;
      }
    }
  }

  console.log(`%c✨ Scraping Complete! Total NEW high-discount deals found: ${allRows.length}`, "color: #10b981; font-weight: bold; font-size: 16px;");

  if (!allRows.length) {
    console.log("No new deals found right now (all items were already seen).");
    return;
  }

  // 1. Direct Push to Google Sheet (if URL provided)
  if (SHEET_WEBAPP_URL) {
    console.log("📤 Pushing deals directly to your Google Sheet...");
    try {
      const postResp = await fetch(SHEET_WEBAPP_URL, {
        method: "POST",
        body: JSON.stringify({
          products: allRows,
          source: "Chrome Scraper (" + new Date().toLocaleDateString() + ")"
        })
      });
      const resJson = await postResp.json();
      console.log("%c✅ Successfully pushed to Google Sheet!", "color: #10b981; font-weight: bold;", resJson);
    } catch (e) {
      console.warn("Could not push to Web App URL (CORS or network). Generating CSV as fallback...", e);
    }
  }

  // 2. Download Backup CSV
  const head = ["title", "url", "price", "mrp", "image_url", "platform"];
  const csvData = "\uFEFF" + [head.join(",")].concat(
    allRows.map(r => [
      esc(r.title),
      esc(r.url),
      r.price,
      r.mrp,
      esc(r.image_url),
      esc(r.platform)
    ].join(","))
  ).join("\n");

  const blob = new Blob([csvData], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `ajio_deals_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  console.log("📥 CSV downloaded as backup: " + a.download);

  // 3. Save seen items to localStorage
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...seenOld, ...seenNow]));
  } catch (e) {}

  console.log("%c🎉 ALL DONE! Your bot is ready to post these deals.", "color: #3b82f6; font-weight: bold;");
})();
