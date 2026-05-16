import asyncio
import os
from pathlib import Path
import subprocess
import sys
import urllib.parse
from dataclasses import dataclass

from playwright.async_api import async_playwright

from app.services.utils import extract_email


@dataclass
class ScrapedLead:
    business_name: str
    category: str | None
    address: str | None
    phone: str | None
    email: str | None
    website: str | None
    google_maps_url: str | None


@dataclass
class ScrapeResult:
    leads: list[ScrapedLead]
    consumed_count: int
    start_index: int


class GoogleMapsScraper:
    """
    IMPORTANT: This scraper depends on Google Maps front-end selectors,
    which can change anytime. Treat this as best-effort ingestion.
    """

    async def scrape(self, query: str, max_results: int = 20, start_index: int = 0) -> ScrapeResult:
        try:
            return await self._scrape_once(query=query, max_results=max_results, start_index=start_index)
        except Exception as exc:
            # Optional self-heal when browser binary cache is missing.
            # Disabled by default because runtime installs can be heavy on small instances.
            message = str(exc)
            allow_runtime_install = os.environ.get('ALLOW_RUNTIME_PLAYWRIGHT_INSTALL', '').lower() == 'true'
            if (
                allow_runtime_install
                and 'Executable does' in message
                and ('ms-playwright' in message or '.playwright-browsers' in message)
            ):
                self._install_playwright_chromium()
                return await self._scrape_once(query=query, max_results=max_results, start_index=start_index)
            raise

    async def _scrape_once(self, query: str, max_results: int = 20, start_index: int = 0) -> ScrapeResult:
        if not os.environ.get('PLAYWRIGHT_BROWSERS_PATH'):
            local_path = Path(__file__).resolve().parents[2] / '.playwright-browsers'
            local_path.mkdir(parents=True, exist_ok=True)
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(local_path)

        encoded = urllib.parse.quote_plus(query)
        search_url = f'https://www.google.com/maps/search/{encoded}'

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                ],
            )
            page = await browser.new_page()
            await page.goto(search_url, wait_until='domcontentloaded', timeout=90000)
            await page.wait_for_timeout(4000)

            target_links_count = max_results + max(0, start_index)

            # Scroll result feed to load more businesses.
            feed = page.locator('div[role="feed"]')
            if await feed.count() > 0:
                for _ in range(25):
                    await feed.evaluate("el => el.scrollBy(0, el.scrollHeight)")
                    await page.wait_for_timeout(900)
                    current_count = await page.locator('a[href*="/maps/place/"]').count()
                    if current_count >= target_links_count:
                        break

            links = page.locator('a[href*="/maps/place/"]')
            hrefs = []
            seen = set()
            count = await links.count()
            for i in range(count):
                href = await links.nth(i).get_attribute('href')
                if not href or href in seen:
                    continue
                seen.add(href)
                hrefs.append(href)
                if len(hrefs) >= target_links_count:
                    break

            selected_hrefs = hrefs[start_index:start_index + max_results]
            leads: list[ScrapedLead] = []
            detail = await browser.new_page()
            try:
                for href in selected_hrefs:
                    await detail.goto(href, wait_until='domcontentloaded', timeout=90000)
                    await detail.wait_for_timeout(1500)

                    name = await self._text_or_none(detail, 'h1.DUwDvf')
                    category = await self._text_or_none(detail, 'button.DkEaL')
                    address = await self._text_or_none(detail, 'button[data-item-id="address"] .fontBodyMedium')
                    phone = await self._text_or_none(detail, 'button[data-item-id^="phone:tel:"] .fontBodyMedium')
                    website = await self._attr_or_none(detail, 'a[data-item-id="authority"]', 'href')

                    # Sometimes email appears in panel text (rare).
                    panel_text = await detail.locator('body').inner_text()
                    email = extract_email(panel_text)

                    if not name:
                        continue

                    leads.append(
                        ScrapedLead(
                            business_name=name,
                            category=category,
                            address=address,
                            phone=phone,
                            email=email,
                            website=website,
                            google_maps_url=href,
                        )
                    )
            finally:
                await detail.close()

            await browser.close()
            return ScrapeResult(
                leads=leads,
                consumed_count=len(selected_hrefs),
                start_index=start_index,
            )

    def _install_playwright_chromium(self) -> None:
        # Keep browser binaries in project path when env is not explicitly set.
        if not os.environ.get('PLAYWRIGHT_BROWSERS_PATH'):
            local_path = Path(__file__).resolve().parents[2] / '.playwright-browsers'
            local_path.mkdir(parents=True, exist_ok=True)
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(local_path)

        subprocess.run(
            [sys.executable, '-m', 'playwright', 'install', '--only-shell', 'chromium'],
            check=True,
        )

    async def _text_or_none(self, page, selector: str) -> str | None:
        el = page.locator(selector).first
        try:
            if await el.count() == 0:
                return None
            text = await el.text_content(timeout=1500)
            if not text:
                return None
            cleaned = text.strip()
            return cleaned if cleaned else None
        except Exception:
            return None

    async def _attr_or_none(self, page, selector: str, attr_name: str) -> str | None:
        el = page.locator(selector).first
        try:
            if await el.count() == 0:
                return None
            value = await el.get_attribute(attr_name, timeout=1500)
            return value.strip() if value else None
        except Exception:
            return None


def scrape_google_maps_sync(query: str, max_results: int = 20, start_index: int = 0) -> ScrapeResult:
    return asyncio.run(
        GoogleMapsScraper().scrape(query=query, max_results=max_results, start_index=start_index)
    )
