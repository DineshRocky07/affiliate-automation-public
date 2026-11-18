/**
 * ==============================================================================
 * 🚀 AJIO AUTO-SCRAPER & DIRECT WEBHOOK RECEIVER (Google Apps Script)
 * ==============================================================================
 * 
 * This script does TWO things:
 * 1. WEBHOOK RECEIVER (doPost): Lets your Chrome browser push deals directly into
 *    the sheet with 1 click (NO CSV, NO COPY-PASTING!).
 * 2. CLOUD FETCHER (runDailyFetch): Scheduled fallback runner.
 * ==============================================================================
 */

const SHEET_ID   = "YOUR_GOOGLE_SHEET_ID";
const SHEET_TAB  = "deals";

// ==============================================================================
// 📥 1. WEBHOOK RECEIVER (doPost)
// Receives deals directly from your Chrome browser and writes to "deals" tab
// ==============================================================================
function doPost(e) {
  try {
    const raw = e.postData ? e.postData.contents : null;
    if (!raw) {
      return ContentService.createTextOutput(JSON.stringify({ status: "error", message: "No data" }))
        .setMimeType(ContentService.MimeType.JSON);
    }

    const payload = JSON.parse(raw);
    const products = payload.products || [];

    const ss = SpreadsheetApp.openById(SHEET_ID);
    const sheet = ss.getSheetByName(SHEET_TAB);
    if (!sheet) {
      return ContentService.createTextOutput(JSON.stringify({ status: "error", message: "Sheet not found" }))
        .setMimeType(ContentService.MimeType.JSON);
    }

    if (sheet.getLastRow() === 0) {
      sheet.appendRow(["title", "url", "price", "mrp", "image_url", "platform"]);
    }

    const existingIds = getExistingProductIds_(sheet);
    let added = 0;

    for (const p of products) {
      let url = String(p.url || "").trim();
      if (!url) continue;
      url = url.replace(/^http:\/\//i, "https://");

      // Extract product ID
      const match = url.match(/\/p\/([^?#/]+)/);
      const prodId = match ? match[1] : url;

      if (existingIds.has(url) || existingIds.has(prodId)) continue;

      sheet.appendRow([
        p.title || "",
        url,
        Number(p.price || 0),
        Number(p.mrp || 0),
        p.image_url || "",
        p.platform || "ajio",
        p.rating ? Number(p.rating) : "",
        p.rating_count ? Number(p.rating_count) : ""
      ]);

      existingIds.add(url);
      existingIds.add(prodId);
      added++;
    }

    return ContentService.createTextOutput(JSON.stringify({
      status: "success",
      added: added,
      total_rows: sheet.getLastRow()
    })).setMimeType(ContentService.MimeType.JSON);

  } catch(err) {
    return ContentService.createTextOutput(JSON.stringify({ status: "error", error: err.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function doGet(e) {
  return ContentService.createTextOutput(JSON.stringify({
    status: "online",
    message: "Google Sheet Webhook is active and ready to receive deals."
  })).setMimeType(ContentService.MimeType.JSON);
}

// ==============================================================================
// 🛡️ DEDUPLICATION HELPER
// ==============================================================================
function getExistingProductIds_(sheet) {
  const ids = new Set();
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return ids;

  const urls = sheet.getRange(2, 2, lastRow - 1, 1).getValues();
  for (const [u] of urls) {
    if (!u) continue;
    const s = String(u).trim();
    ids.add(s);
    const m = s.match(/\/p\/([^?#/]+)/);
    if (m) ids.add(m[1]);
  }
  return ids;
}


