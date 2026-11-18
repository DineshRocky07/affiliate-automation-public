# 🚀 AJIO Scraping & Sheet Automation Guide

## Why did Apps Script give HTTP 403?
AJIO uses **Akamai bot protection**. It actively blocks all datacenter/cloud IP addresses (Google Cloud, AWS, etc.). 
That is why running `UrlFetchApp` directly inside Apps Script returned `HTTP 403 Forbidden`.

The **only place** that can bypass this is **your Chrome browser**, because Chrome has:
- Real human session cookies
- Akamai fingerprint tokens (`credentials: "include"`)
- Residential internet IP

---

## ⚡ The Solution: Browser Scraper + Direct Sheet Push

We created a 2-part setup:
1. **Google Apps Script** acts as a **Receiver Web App** (receives deals and appends to `deals` tab).
2. **Browser JS Scraper** runs in Chrome on `ajio.com`, finds deals across **Men, Women, Kids, 50%+ Offers, Top Brands**, and pushes them straight to your Google Sheet without any copy-paste!

---

### Step 1: Deploy Apps Script as a Web App (Takes 1 min)

1. Open your Google Sheet: https://docs.google.com/spreadsheets/d/YOUR_GOOGLE_SHEET_ID
2. Go to **Extensions -> Apps Script**.
3. Replace all code in `Code.gs` with the contents of [`apps_script/ajio_auto_scraper.gs`](ajio_auto_scraper.gs). Click **Save** (Ctrl+S).
4. In the top right, click **Deploy** -> **New deployment**.
5. Click the gear icon (⚙️) next to "Select type" and select **Web app**.
   - **Description**: `AJIO Deals Receiver`
   - **Execute as**: `Me`
   - **Who has access**: `Anyone` *(Crucial so your browser can send data to it)*
6. Click **Deploy**.
7. Grant permissions if prompted (Advanced -> Go to Untitled project).
8. Copy the **Web App URL** (looks like `https://script.google.com/macros/s/.../exec`).

---

### Step 2: Run Scraper in Chrome

1. Open [AJIO.com](https://www.ajio.com) in Chrome.
2. Press `F12` on your keyboard, then click the **Console** tab.
3. Open [`apps_script/ajio_browser_scraper.js`](ajio_browser_scraper.js).
4. At line 20, put your Web App URL between the quotes:
   ```javascript
   const SHEET_WEBAPP_URL = "https://script.google.com/macros/s/.../exec";
   ```
5. Copy the entire code, paste it into the Chrome Console, and press **Enter**.

---

### What Happens Automatically:
- ✅ Scrapes **7 categories**: Offers 50%+, Men Shirts & Tops, Men T-Shirts, Women Kurtas & Dresses, Women Tops, Kids Wear, Top Brands Sale.
- ✅ Filters only discounts **>= 40%**.
- ✅ Ignores products you already scraped before (`localStorage`).
- ✅ **Automatically writes new rows to your Google Sheet "deals" tab!**
- ✅ Downloads a backup CSV just in case.

---

### Step 3: Post the Deals to Telegram

Once rows appear in your Google Sheet, run your bot:
```powershell
cd "c:\Void\anitgravity\affliate market\affiliate-pro-course"
python -m app.main run-sheet
```
The bot will post them one by one to `@YourDealsChannel` with your **AJIO ACE affiliate tracking link** and price cards!
