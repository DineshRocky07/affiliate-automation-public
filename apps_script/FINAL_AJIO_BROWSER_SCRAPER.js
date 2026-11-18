/**
 * ==============================================================================
 * 🌟 ADVANCED AJIO TOP BRANDS & UNDER-₹500 DEAL SCRAPER (v2.0)
 * ==============================================================================
 * 
 * 🎯 TARGETS ALL TOP BRANDS & HIGH-CONVERTING CATEGORIES:
 *   ✅ DNMX (T-Shirts, Shirts, Jeans)
 *   ✅ Lee Cooper (T-Shirts, Shirts, Footwear)
 *   ✅ Netplay (Casual & Formal Shirts)
 *   ✅ Teamspirit (Polos & T-Shirts)
 *   ✅ Red Tape (Shoes, Sliders, Shirts)
 *   ✅ Campus & Sparx (Footwear & Slippers Under ₹500)
 *   ✅ Puma, Levi's, Flying Machine, USPA
 *   ✅ Women Kurtas (Avaasa, Fusion, Rangriti)
 *   ✅ Under-₹499 & 50%+ OFF Curated Stores
 * 
 * 🚀 FEATURES:
 *   - Automatic Brand Extraction & Title Normalization
 *   - Filters: Price <= ₹500 & Discount >= 40% OFF
 *   - Auto-pushes directly into your Google Sheet via Webhook (No CSV needed!)
 *   - In-memory duplicate protection + Google Sheet duplicate shield
 * ==============================================================================
 */

(async function advancedAjioTopBrandScraper() {
  const WEBHOOK_URL = "https://script.google.com/macros/s/YOUR_WEBHOOK_EXEC_ID/exec";
  const MAX_PRICE = 500;
  const MIN_DISCOUNT = 40;

  // Curated categories and Brand-specific targets
  const SOURCES = [
    // 🌟 Top Brand Specific Searches & Filters
    { label: "DNMX T-Shirts & Tops", url: "https://www.ajio.com/api/category/830216010?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true&query=:relevance:brand:DNMX" },
    { label: "DNMX Shirts", url: "https://www.ajio.com/api/category/830216001?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true&query=:relevance:brand:DNMX" },
    { label: "Lee Cooper T-Shirts", url: "https://www.ajio.com/api/category/830216010?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true&query=:relevance:brand:LEE%20COOPER" },
    { label: "Lee Cooper Shirts", url: "https://www.ajio.com/api/category/830216001?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true&query=:relevance:brand:LEE%20COOPER" },
    { label: "Netplay Shirts & Tops", url: "https://www.ajio.com/api/category/830216001?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true&query=:relevance:brand:NETPLAY" },
    { label: "Teamspirit T-Shirts", url: "https://www.ajio.com/api/category/830216010?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true&query=:relevance:brand:TEAMSPIRIT" },
    { label: "Red Tape Deals", url: "https://www.ajio.com/api/search?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true&query=red+tape" },
    { label: "Campus Footwear Under ₹500", url: "https://www.ajio.com/api/category/830207?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true&query=:relevance:brand:CAMPUS" },
    { label: "Sparx Slippers & Sandals", url: "https://www.ajio.com/api/category/830207001?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true&query=:relevance:brand:SPARX" },
    { label: "Puma & Sports Deals", url: "https://www.ajio.com/api/search?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true&query=puma" },
    { label: "Flying Machine Deals", url: "https://www.ajio.com/api/search?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true&query=flying+machine" },
    { label: "USPA Deals", url: "https://www.ajio.com/api/search?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true&query=uspa" },

    // 🏷️ High-Discount Clearance Categories
    { label: "Curated 50%+ OFF Deals", url: "https://www.ajio.com/api/curated/min50percentoff-curated-437897?fields=SITE&format=json&curated=true&curatedid=min50percentoff-curated-437897&platform=Msite&store=ajio&gridColumns=2&advfilter=true" },
    { label: "Under-499 Store", url: "https://www.ajio.com/api/curated/under-499-curated?fields=SITE&format=json&curated=true&platform=Msite&store=ajio&gridColumns=2&advfilter=true" },
    { label: "Men T-Shirts (All Brands)", url: "https://www.ajio.com/api/category/830216010?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true" },
    { label: "Men Shirts (All Brands)", url: "https://www.ajio.com/api/category/830216001?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true" },
    { label: "Women Kurtas & Kurtis", url: "https://www.ajio.com/api/category/830303011?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true" },
    { label: "Women Western Tops", url: "https://www.ajio.com/api/category/830303002?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true" },
    { label: "Kids Wear Clearance", url: "https://www.ajio.com/api/category/830401?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true" }
  ];

  const deals = [];
  const seenIds = new Set();
  console.log("%c🚀 Starting Advanced AJIO Top Brands & Deals Scraper...", "color: #38bdf8; font-weight: bold; font-size: 15px;");

  for (const src of SOURCES) {
    try {
      // Fetch 2 pages per source (45 items/page = up to 90 items per category)
      for (let page = 0; page < 2; page++) {
        const u = new URL(src.url);
        u.searchParams.set("currentPage", page);
        u.searchParams.set("pageSize", 45);

        const r = await fetch(u.toString(), { credentials: "include" });
        if (!r.ok) break;

        const data = await r.json();
        const products = data.products || [];
        if (!products.length) break;

        let addedThisBatch = 0;
        for (const p of products) {
          const rawId = p.code || p.url || "";
          if (seenIds.has(rawId)) continue;

          const price = Number(p.price?.value ?? 0);
          const mrp = Number(p.wasPriceData?.value ?? 0);
          let rawTitle = (p.name || "").trim();
          const brand = (p.fnlColorVariantData?.brandName || p.brandName || "").trim();

          // 1. Price check: Must be <= MAX_PRICE
          if (price <= 0 || price > MAX_PRICE) continue;

          // 2. Discount check: Must be >= MIN_DISCOUNT
          const discount = mrp > price ? Math.round(((mrp - price) / mrp) * 100) : 0;
          if (discount < MIN_DISCOUNT) continue;

          // Clean and format Title with Brand if missing
          let title = rawTitle;
          if (brand && !rawTitle.toUpperCase().startsWith(brand.toUpperCase())) {
            title = `${brand} ${rawTitle}`;
          }

          // Extract best image
          let img = "";
          if (p.fnlColorVariantData?.outfitPictureURL) {
            img = p.fnlColorVariantData.outfitPictureURL;
          } else if (p.images?.[0]?.url) {
            img = p.images[0].url.startsWith("http") ? p.images[0].url : "https://assets.ajio.com" + p.images[0].url;
          }

          const productUrl = p.url.startsWith("http") ? p.url : "https://www.ajio.com" + p.url;

          deals.push({
            title: title,
            url: productUrl,
            price: price,
            mrp: mrp,
            image_url: img,
            platform: "ajio"
          });

          seenIds.add(rawId);
          seenIds.add(productUrl);
          addedThisBatch++;
        }
        if (addedThisBatch > 0) {
          console.log(`   ✅ ${src.label} (Page ${page + 1}): Found ${addedThisBatch} deals`);
        }
      }
    } catch (e) {
      console.warn(`Error scraping ${src.label}:`, e);
    }
  }

  console.log(`%c✨ Collected ${deals.length} qualified Top Brand & Under-₹500 deals!`, "color: #10b981; font-weight: bold; font-size: 15px;");

  // Push directly to Google Sheet
  if (deals.length > 0 && WEBHOOK_URL.startsWith("http")) {
    console.log("%c📤 Pushing directly to your Google Sheet...", "color: #f59e0b; font-weight: bold;");
    try {
      const resp = await fetch(WEBHOOK_URL, {
        method: "POST",
        body: JSON.stringify({ products: deals })
      });
      const res = await resp.json();
      console.log("%c✅ Server Response:", "color: #10b981; font-weight: bold;", res);

      if (res.added > 0) {
        alert(`🎉 SUCCESS! Added ${res.added} NEW Top Brand & Under-₹500 Deals to your Google Sheet! (Total Rows: ${res.total_rows})`);
      } else {
        alert(`ℹ️ Scraped ${deals.length} deals, but all of them are already in your Google Sheet! (No duplicates added).`);
      }
    } catch (err) {
      console.error("Failed to push to Webhook:", err);
      alert("❌ Could not reach Google Sheet Webhook. Check console.");
    }
  } else {
    alert("No new deals matched the criteria right now.");
  }
})();
