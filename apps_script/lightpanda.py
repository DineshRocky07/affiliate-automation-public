import asyncio
from playwright.async_api import async_playwright

async def scrape_with_lightpanda():
    async with async_playwright() as p:
        # Connect to Lightpanda CDP instead of opening heavy Chrome!
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = await browser.new_page()

        # Ultra-fast page load (no heavy graphics)
        await page.goto("https://www.ajio.com/s/under-500-4824-64461")
        
        # Extract title and deal details
        deals = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('.item')).map(el => ({
                title: el.querySelector('.name')?.innerText,
                price: el.querySelector('.price')?.innerText
            }));
        }""")
        
        print(f"Scraped {len(deals)} deals in milliseconds!")
        await browser.close()

asyncio.run(scrape_with_lightpanda())