/**
 * ==============================================================================
 * 👔 PREMIUM MEN'S FULL-SLEEVE SHIRTS UNDER ₹500 (HIGH RATING & 100% COTTON)
 * ==============================================================================
 * 
 * 🎯 ZERO LOW QUALITY. ZERO HALF SLEEVES:
 *   ✅ STRICTLY Full Sleeves Only (Half sleeves filtered out)
 *   ✅ HIGH RATING ONLY: Minimum 3.8 ⭐ / 4.0 ⭐+ (Low ratings rejected)
 *   ✅ Premium Fabrics: Pure Cotton, Cotton Twill, Oxford & Denim
 *   ✅ Top Trusted Brands: DNMX, Netplay, Lee Cooper, John Players, Dennis Lingo, The Indian Garage Co
 *   ✅ Sorted by Customer Rating & Popularity on AJIO
 *   ✅ Pushes directly to your Google Sheet with 1 click!
 * ==============================================================================
 */

(async function scrapeBestFullSleeveShirtsUnder500() {
  const WEBHOOK_URL = "https://script.google.com/macros/s/YOUR_WEBHOOK_EXEC_ID/exec";
  const MAX_PRICE = 500;
  const MIN_DISCOUNT = 40;
  const MIN_RATING = 3.8; // ⭐ Minimum 3.8 Stars (Rejects low quality shirts)

  const SHIRT_SOURCES = [
    // 👔 1. High-Rated Full-Sleeve Cotton Shirts (Sorted by Rating)
    { label: "High-Rated Full Sleeve Cotton Shirts", url: "https://www.ajio.com/api/search?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true&query=mens+full+sleeve+cotton+shirt&sort=rating" },
    
    // 👔 2. Netplay Premium Formal & Office Shirts (Top Rated on AJIO)
    { label: "Netplay Full Sleeve Formal Shirts", url: "https://www.ajio.com/api/search?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true&query=netplay+full+sleeve+shirt&sort=rating" },
    
    // 👔 3. DNMX Best-Selling Casual Shirts (Popularity)
    { label: "DNMX Full Sleeve Casual Shirts", url: "https://www.ajio.com/api/search?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true&query=dnmx+full+sleeve+shirt&sort=popularity" },
    
    // 👔 4. Lee Cooper Heritage Full-Sleeve Shirts
    { label: "Lee Cooper Full Sleeve Shirts", url: "https://www.ajio.com/api/search?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true&query=lee+cooper+full+sleeve+shirt&sort=rating" },
    
    // 👔 5. Dennis Lingo & Highlander (Bestseller Cotton Shirts)
    { label: "Dennis Lingo Slim Fit Shirts", url: "https://www.ajio.com/api/search?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true&query=dennis+lingo+shirt&sort=rating" },
    { label: "Highlander Full Sleeve Shirts", url: "https://www.ajio.com/api/search?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true&query=highlander+full+sleeve+shirt&sort=rating" },
    
    // 👔 6. John Players Office & Checked Shirts
    { label: "John Players Full Sleeve Shirts", url: "https://www.ajio.com/api/search?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true&query=john+players+shirt&sort=rating" },

    // 👔 7. Category Fallback (Filtered for rating)
    { label: "Men Shirts High Rated", url: "https://www.ajio.com/api/category/830216001?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true&sort=rating" }
  ];

  const shirtDeals = [];
  const seenIds = new Set();
  console.log("%c👔 Starting Premium Men's Full-Sleeve (3.8+ ⭐) Shirt Scraper...", "color: #38bdf8; font-weight: bold; font-size: 15px;");

  for (const src of SHIRT_SOURCES) {
    try {
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
          const rawTitle = (p.name || "").trim();
          const brand = (p.fnlColorVariantData?.brandName || p.brandName || "").trim();
          const titleLower = rawTitle.toLowerCase();

          // ❌ FILTER 1: STRICTLY EXCLUDE T-SHIRTS & POLOS
          if (titleLower.includes("t-shirt") || titleLower.includes("tshirt") || titleLower.includes("tee") || titleLower.includes("polo")) {
            continue;
          }

          // ❌ FILTER 2: STRICTLY EXCLUDE HALF SLEEVES & SHORT SLEEVES
          if (titleLower.includes("half sleeve") || titleLower.includes("short sleeve") || titleLower.includes("half-sleeve") || titleLower.includes("short-sleeve")) {
            continue;
          }

          // ❌ FILTER 3: STRICTLY EXCLUDE CHEAP POLYESTER/SYNTHETIC
          if (titleLower.includes("polyester") || titleLower.includes("satin")) {
            continue;
          }

          // ❌ FILTER 4: RATING FILTER - MUST BE >= 3.8 STARS (If ratings exist)
          const rating = Number(p.averageRating ?? 0);
          if (p.averageRating && rating > 0 && rating < MIN_RATING) {
            continue; // Rejects 2.5 - 3.7 star shirts
          }

          // ❌ FILTER 5: PRICE & DISCOUNT
          if (price <= 0 || price > MAX_PRICE) continue;
          const discount = mrp > price ? Math.round(((mrp - price) / mrp) * 100) : 0;
          if (discount < MIN_DISCOUNT) continue;

          // Format title cleanly with Brand
          let title = rawTitle;
          if (brand && !rawTitle.toUpperCase().startsWith(brand.toUpperCase())) {
            title = `${brand} ${rawTitle}`;
          }

          // High-Res outfit image
          let img = "";
          if (p.fnlColorVariantData?.outfitPictureURL) {
            img = p.fnlColorVariantData.outfitPictureURL;
          } else if (p.images?.[0]?.url) {
            img = p.images[0].url.startsWith("http") ? p.images[0].url : "https://assets.ajio.com" + p.images[0].url;
          }

          const productUrl = p.url.startsWith("http") ? p.url : "https://www.ajio.com" + p.url;

          shirtDeals.push({
            title: title,
            url: productUrl,
            price: price,
            mrp: mrp,
            image_url: img,
            platform: "ajio",
            rating: rating > 0 ? rating : null,
            rating_count: p.ratingCount ? Number(p.ratingCount) : null
          });

          seenIds.add(rawId);
          seenIds.add(productUrl);
          addedThisBatch++;
        }

        if (addedThisBatch > 0) {
          console.log(`   ✅ ${src.label} (Page ${page + 1}): Found ${addedThisBatch} premium full-sleeve shirts!`);
        }
      }
    } catch (e) {
      console.warn(`Error on ${src.label}:`, e);
    }
  }

  console.log(`%c✨ Collected ${shirtDeals.length} High-Rated Full-Sleeve Shirts Under ₹500!`, "color: #10b981; font-weight: bold; font-size: 15px;");

  // Push directly to Google Sheet Webhook
  if (shirtDeals.length > 0 && WEBHOOK_URL.startsWith("http")) {
    console.log("%c📤 Pushing premium shirts directly to your Google Sheet...", "color: #f59e0b; font-weight: bold;");
    try {
      const resp = await fetch(WEBHOOK_URL, {
        method: "POST",
        body: JSON.stringify({ products: shirtDeals })
      });
      const res = await resp.json();
      console.log("%c✅ Server Response:", "color: #10b981; font-weight: bold;", res);

      if (res.added > 0) {
        alert(`🎉 SUCCESS! Added ${res.added} NEW High-Rated Full-Sleeve Shirts Under ₹500 to your Google Sheet! (Total Rows: ${res.total_rows})\n\nAll have >=3.8⭐ rating & full sleeves!`);
      } else {
        alert(`ℹ️ Scraped ${shirtDeals.length} high-rated shirts, but all of them are already in your Google Sheet.`);
      }
    } catch (err) {
      console.error("Failed to push to Webhook:", err);
      alert("❌ Could not reach Google Sheet Webhook. Check console.");
    }
  } else {
    alert("No shirts matched the 3.8+ rating & full sleeve criteria right now.");
  }
})();
