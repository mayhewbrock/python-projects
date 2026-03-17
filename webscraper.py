#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║         PRICE HUNTER — Desktop Deal Finder with GUI          ║
║   Find cheaper alternatives with one click!                  ║
╚══════════════════════════════════════════════════════════════╝
"""

import re
import sys
import json
import time
import random
import urllib.parse
import concurrent.futures
import threading
from dataclasses import dataclass, field
from typing import Optional
import webbrowser

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Installing required packages...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "requests", "beautifulsoup4", "--break-system-packages", "-q"])
    import requests
    from bs4 import BeautifulSoup

# Tkinter imports
import tkinter as tk
from tkinter import ttk, messagebox


# ── Constants ────────────────────────────────────────────────────────────────

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
]

HEADERS_BASE = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}

PRICE_REGEX = re.compile(r"\$[\d,]+\.?\d{0,2}|\b[\d,]+\.?\d{0,2}\s*(?:USD|dollars?)\b", re.IGNORECASE)


# ── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class Product:
    title: str
    price: Optional[float]
    price_str: str
    url: str
    source: str
    rating: Optional[str] = None
    reviews: Optional[str] = None
    image: Optional[str] = None
    availability: str = "Unknown"
    savings: Optional[float] = field(default=None)
    savings_pct: Optional[float] = field(default=None)

    def to_dict(self):
        return {
            "title": self.title,
            "price": self.price,
            "price_str": self.price_str,
            "url": self.url,
            "source": self.source,
            "rating": self.rating,
            "reviews": self.reviews,
            "availability": self.availability,
            "savings": self.savings,
            "savings_pct": self.savings_pct,
        }


# ── HTTP Utilities ───────────────────────────────────────────────────────────

def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS_BASE)
    session.headers["User-Agent"] = random.choice(USER_AGENTS)
    return session


def safe_get(session: requests.Session, url: str, retries: int = 3, timeout: int = 15) -> Optional[requests.Response]:
    for attempt in range(retries):
        try:
            session.headers["User-Agent"] = random.choice(USER_AGENTS)
            resp = session.get(url, timeout=timeout, allow_redirects=True)
            if resp.status_code == 200:
                return resp
            elif resp.status_code == 429:
                wait = 2 ** attempt + random.uniform(1, 3)
                time.sleep(wait)
            elif resp.status_code in (403, 503):
                session.cookies.clear()
                time.sleep(random.uniform(2, 5))
        except (requests.RequestException, Exception):
            if attempt < retries - 1:
                time.sleep(random.uniform(1, 3))
    return None


def parse_price(text: str) -> Optional[float]:
    """Extract float price from a messy string."""
    if not text:
        return None
    text = text.replace(",", "").strip()
    matches = re.findall(r"[\$£€]?\s*([\d]+\.?\d{0,2})", text)
    for m in matches:
        try:
            val = float(m)
            if 0.01 < val < 100_000:
                return val
        except ValueError:
            continue
    return None


# ── Source Extractor: Original URL ──────────────────────────────────────────

class OriginalProductExtractor:
    def __init__(self, url: str, session: requests.Session):
        self.url = url
        self.session = session
        self.domain = urllib.parse.urlparse(url).netloc.lower()

    def extract(self) -> Optional[Product]:
        resp = safe_get(self.session, self.url)
        if not resp:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")

        # Detect source
        if "amazon" in self.domain:
            return self._parse_amazon(soup)
        elif "ebay" in self.domain:
            return self._parse_ebay(soup)
        elif "walmart" in self.domain:
            return self._parse_walmart(soup)
        elif "bestbuy" in self.domain:
            return self._parse_bestbuy(soup)
        elif "target" in self.domain:
            return self._parse_target(soup)
        else:
            return self._parse_generic(soup)

    def _parse_amazon(self, soup: BeautifulSoup) -> Optional[Product]:
        title_tag = soup.find("span", id="productTitle")
        title = title_tag.get_text(strip=True) if title_tag else ""

        price = None
        price_str = ""
        for sel in ["#priceblock_ourprice", "#priceblock_dealprice", ".a-price .a-offscreen",
                    "#corePrice_feature_div .a-price .a-offscreen", ".apexPriceToPay .a-offscreen"]:
            el = soup.select_one(sel)
            if el:
                price_str = el.get_text(strip=True)
                price = parse_price(price_str)
                if price:
                    break

        rating_el = soup.select_one("span[data-hook='rating-out-of-text'], .a-icon-alt")
        reviews_el = soup.select_one("#acrCustomerReviewText, span[data-hook='total-review-count']")

        return Product(
            title=title, price=price, price_str=price_str,
            url=self.url, source="Amazon",
            rating=rating_el.get_text(strip=True) if rating_el else None,
            reviews=reviews_el.get_text(strip=True) if reviews_el else None,
        )

    def _parse_ebay(self, soup: BeautifulSoup) -> Optional[Product]:
        title = (soup.find("h1", class_=re.compile("x-item-title")) or
                 soup.find("h1", itemprop="name"))
        title = title.get_text(strip=True) if title else ""

        price_el = soup.select_one(".x-price-primary span, #prcIsum, #mm-saleDscPrc")
        price_str = price_el.get_text(strip=True) if price_el else ""
        price = parse_price(price_str)

        return Product(title=title, price=price, price_str=price_str,
                       url=self.url, source="eBay")

    def _parse_walmart(self, soup: BeautifulSoup) -> Optional[Product]:
        title = soup.find("h1", itemprop="name") or soup.select_one('[itemprop="name"]')
        title = title.get_text(strip=True) if title else ""
        price_el = soup.select_one('[itemprop="price"], .price-characteristic')
        price_str = price_el.get_text(strip=True) if price_el else ""
        price = parse_price(price_str)
        return Product(title=title, price=price, price_str=price_str,
                       url=self.url, source="Walmart")

    def _parse_bestbuy(self, soup: BeautifulSoup) -> Optional[Product]:
        title = soup.select_one(".sku-title h1")
        title = title.get_text(strip=True) if title else ""
        price_el = soup.select_one(".priceView-hero-price span")
        price_str = price_el.get_text(strip=True) if price_el else ""
        price = parse_price(price_str)
        return Product(title=title, price=price, price_str=price_str,
                       url=self.url, source="Best Buy")

    def _parse_target(self, soup: BeautifulSoup) -> Optional[Product]:
        title = soup.select_one('[data-test="product-title"]')
        title = title.get_text(strip=True) if title else ""
        price_el = soup.select_one('[data-test="product-price"]')
        price_str = price_el.get_text(strip=True) if price_el else ""
        price = parse_price(price_str)
        return Product(title=title, price=price, price_str=price_str,
                       url=self.url, source="Target")

    def _parse_generic(self, soup: BeautifulSoup) -> Optional[Product]:
        # Try Open Graph / meta tags first
        og_title = soup.find("meta", property="og:title")
        title = str(og_title.get("content", "") or "") if og_title else ""
        if not title:
            h1 = soup.find("h1")
            title = h1.get_text(strip=True) if h1 else "Unknown Product"

        # Find price via meta or common patterns
        og_price = soup.find("meta", property="product:price:amount") or \
                   soup.find("meta", itemprop="price")
        price_str = ""
        price = None
        if og_price:
            price_str = str(og_price.get("content", "") or "")
            price = parse_price(price_str)
        if not price:
            # Scan page text for prices
            for el in soup.select('[class*="price"], [id*="price"], [itemprop="price"]'):
                text = el.get_text(strip=True)
                p = parse_price(text)
                if p:
                    price = p
                    price_str = text
                    break

        return Product(title=title, price=price, price_str=price_str,
                       url=self.url, source=self.domain)


# ── Scrapers ─────────────────────────────────────────────────────────────────

class GoogleShoppingScraper:
    NAME = "Google Shopping"

    def search(self, query: str, session: requests.Session) -> list[Product]:
        products = []
        encoded = urllib.parse.quote_plus(query)
        url = f"https://www.google.com/search?q={encoded}&tbm=shop&num=20&hl=en&gl=us"

        resp = safe_get(session, url)
        if not resp:
            return products

        soup = BeautifulSoup(resp.text, "html.parser")

        # Google Shopping result cards
        cards = soup.select(".sh-dgr__content, .sh-np__click-target, .Qlx7of")
        if not cards:
            cards = soup.select("[class*='sh-pr'], [data-sh-gr]")

        for card in cards[:10]:
            try:
                title_el = card.select_one("h3, .tAxDx, .Xjkr3b, [class*='title']")
                price_el = card.select_one(".a8Pemb, .OFFNJ, [class*='price']")
                source_el = card.select_one(".aULzUe, .zPEcBd, [class*='merchant'], [class*='store']")
                link_el = card.select_one("a[href]")

                title = title_el.get_text(strip=True) if title_el else ""
                price_str = price_el.get_text(strip=True) if price_el else ""
                source_name = source_el.get_text(strip=True) if source_el else "Google Shopping"
                href = link_el.get("href", "") if link_el else ""
                href = str(href or "")

                if isinstance(href, str) and href.startswith("/"):
                    href = "https://www.google.com" + href

                price = parse_price(price_str)
                if title and price:
                    products.append(Product(
                        title=title, price=price, price_str=price_str,
                        url=href, source=source_name or "Google Shopping"
                    ))
            except Exception:
                continue

        return products


class AmazonScraper:
    NAME = "Amazon"
    BASE = "https://www.amazon.com"

    def search(self, query: str, session: requests.Session) -> list[Product]:
        products = []
        encoded = urllib.parse.quote_plus(query)
        url = f"{self.BASE}/s?k={encoded}&ref=nb_sb_noss"

        resp = safe_get(session, url)
        if not resp:
            return products

        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.select('[data-component-type="s-search-result"]')

        for item in items[:10]:
            try:
                title_el = item.select_one("h2 a span, h2 span")
                price_whole = item.select_one(".a-price-whole")
                price_frac = item.select_one(".a-price-fraction")
                link_el = item.select_one("h2 a")
                rating_el = item.select_one(".a-icon-alt")
                reviews_el = item.select_one(".a-size-base.s-underline-text")

                title = title_el.get_text(strip=True) if title_el else ""
                href = link_el.get("href", "") if link_el else ""
                href = str(href or "")
                if href and not href.startswith("http"):
                    href = self.BASE + href

                price_str = ""
                price = None
                if price_whole:
                    whole = price_whole.get_text(strip=True).replace(",", "").rstrip(".")
                    frac = price_frac.get_text(strip=True) if price_frac else "00"
                    price_str = f"${whole}.{frac}"
                    price = parse_price(price_str)

                if title and price:
                    products.append(Product(
                        title=title, price=price, price_str=price_str,
                        url=href, source="Amazon",
                        rating=rating_el.get_text(strip=True) if rating_el else None,
                        reviews=reviews_el.get_text(strip=True) if reviews_el else None,
                    ))
            except Exception:
                continue

        return products


class EbayScraper:
    NAME = "eBay"
    BASE = "https://www.ebay.com"

    def search(self, query: str, session: requests.Session) -> list[Product]:
        products = []
        encoded = urllib.parse.quote_plus(query)
        url = f"{self.BASE}/sch/i.html?_nkw={encoded}&_sop=15&LH_BIN=1&LH_ItemCondition=3"
        # _sop=15 = Best Match, LH_BIN=1 = Buy It Now, Condition=3 = Used (to find cheaper)

        resp = safe_get(session, url)
        if not resp:
            return products

        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.select(".s-item")

        for item in items[:12]:
            try:
                title_el = item.select_one(".s-item__title")
                price_el = item.select_one(".s-item__price")
                link_el = item.select_one(".s-item__link")
                condition_el = item.select_one(".SECONDARY_INFO")

                title = title_el.get_text(strip=True) if title_el else ""
                if title.lower() == "shop on ebay":
                    continue
                price_str = price_el.get_text(strip=True) if price_el else ""
                # Skip price ranges (auctions)
                if "to" in price_str.lower():
                    continue
                href = link_el["href"] if link_el else ""
                price = parse_price(price_str)
                availability = condition_el.get_text(strip=True) if condition_el else "Available"

                if title and price:
                    products.append(Product(
                        title=title, price=price, price_str=price_str,
                        url=href, source="eBay",
                        availability=availability
                    ))
            except Exception:
                continue

        return products


class WalmartScraper:
    NAME = "Walmart"
    BASE = "https://www.walmart.com"

    def search(self, query: str, session: requests.Session) -> list[Product]:
        products = []
        encoded = urllib.parse.quote_plus(query)
        url = f"{self.BASE}/search?q={encoded}&sort=price_low"

        resp = safe_get(session, url)
        if not resp:
            return products

        # Try JSON embedded in page
        json_match = re.search(r'__NEXT_DATA__\s*=\s*(\{.+?\});\s*</script>', resp.text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                items = (data.get("props", {}).get("pageProps", {})
                            .get("initialData", {}).get("searchResult", {})
                            .get("itemStacks", [{}])[0].get("items", []))
                for item in items[:10]:
                    try:
                        title = item.get("name", "")
                        price = item.get("priceInfo", {}).get("currentPrice", {}).get("price")
                        price_str = f"${price:.2f}" if price else ""
                        url_path = item.get("canonicalUrl", "")
                        href = self.BASE + url_path if url_path else ""
                        if title and price:
                            products.append(Product(
                                title=title, price=float(price), price_str=price_str,
                                url=href, source="Walmart"
                            ))
                    except Exception:
                        continue
                return products
            except Exception:
                pass

        # Fallback: HTML parse
        soup = BeautifulSoup(resp.text, "html.parser")
        for item in soup.select('[data-item-id], [data-automation-id="product-price"]')[:10]:
            try:
                title_el = item.select_one('[data-automation-id="product-title"]')
                price_el = item.select_one('[data-automation-id="product-price"] span')
                link_el = item.select_one("a")
                title = title_el.get_text(strip=True) if title_el else ""
                price_str = price_el.get_text(strip=True) if price_el else ""
                href_raw = link_el.get("href", "") if link_el else ""
                href_raw = str(href_raw or "")
                href = self.BASE + href_raw if href_raw.startswith("/") else ""
                price = parse_price(price_str)
                if title and price:
                    products.append(Product(title=title, price=price, price_str=price_str,
                                            url=href, source="Walmart"))
            except Exception:
                continue

        return products


class BingShoppingScraper:
    NAME = "Bing Shopping"

    def search(self, query: str, session: requests.Session) -> list[Product]:
        products = []
        encoded = urllib.parse.quote_plus(query)
        url = f"https://www.bing.com/shop?q={encoded}&filters=ex1%3a%22ez1%22"

        resp = safe_get(session, url)
        if not resp:
            return products

        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.select(".br-item, .dr-sp, [class*='item']")

        for item in items[:10]:
            try:
                title_el = item.select_one(".br-title, [class*='title'], h3")
                price_el = item.select_one(".br-price, [class*='price']")
                link_el = item.select_one("a[href]")
                seller_el = item.select_one(".br-seller, [class*='seller'], [class*='merchant']")

                title = title_el.get_text(strip=True) if title_el else ""
                price_str = price_el.get_text(strip=True) if price_el else ""
                href = link_el["href"] if link_el else ""
                seller = seller_el.get_text(strip=True) if seller_el else "Bing Shopping"

                price = parse_price(price_str)
                if title and price:
                    products.append(Product(
                        title=title, price=price, price_str=price_str,
                        url=href, source=seller
                    ))
            except Exception:
                continue

        return products


class PriceSpyScraper:
    """PriceSpy / PriceRunner style scraper"""
    NAME = "PriceRunner"

    def search(self, query: str, session: requests.Session) -> list[Product]:
        products = []
        encoded = urllib.parse.quote_plus(query)
        url = f"https://www.pricerunner.com/search?q={encoded}"

        resp = safe_get(session, url)
        if not resp:
            return products

        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.select("[class*='ProductCard'], [class*='product-card']")

        for item in items[:8]:
            try:
                title_el = item.select_one("[class*='title'], h2, h3")
                price_el = item.select_one("[class*='price']")
                link_el = item.select_one("a[href]")

                title = title_el.get_text(strip=True) if title_el else ""
                price_str = price_el.get_text(strip=True) if price_el else ""
                href = link_el.get("href", "") if link_el else ""
                href = str(href or "")
                if isinstance(href, str) and href.startswith("/"):
                    href = "https://www.pricerunner.com" + href

                price = parse_price(price_str)
                if title and price:
                    products.append(Product(title=title, price=price, price_str=price_str,
                                            url=href, source="PriceRunner"))
            except Exception:
                continue

        return products


# ── Query Builder ────────────────────────────────────────────────────────────

def build_search_query(product: Optional[Product], url: str) -> str:
    """Build a smart search query from the product or URL."""
    if product and product.title:
        title = product.title
        # Strip common noise
        title = re.sub(r'\(.*?\)', '', title)  # remove parentheticals
        title = re.sub(r'\[.*?\]', '', title)
        # Keep first ~60 chars to avoid over-specific queries
        words = title.split()
        return " ".join(words[:8])
    else:
        # Extract from URL
        parsed = urllib.parse.urlparse(url)
        path = parsed.path
        slug = path.split("/")[-1] or path.split("/")[-2]
        slug = re.sub(r'[-_]', ' ', slug)
        slug = re.sub(r'[^a-zA-Z0-9 ]', '', slug)
        return slug[:80]


# ── Results Engine ───────────────────────────────────────────────────────────

def compute_savings(results: list[Product], reference_price: Optional[float]) -> list[Product]:
    """Add savings info to each result."""
    if not reference_price:
        return results
    for p in results:
        if p.price and p.price < reference_price:
            p.savings = round(reference_price - p.price, 2)
            p.savings_pct = round((p.savings / reference_price) * 100, 1)
    return results


def deduplicate(products: list[Product]) -> list[Product]:
    """Remove near-duplicate products (same source + very similar price)."""
    seen = set()
    unique = []
    for p in products:
        key = (p.source.lower(), round(p.price or 0, 0))
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def run_scrapers_parallel(query: str, session: requests.Session, callback=None) -> list[Product]:
    scrapers = [
        GoogleShoppingScraper(),
        AmazonScraper(),
        EbayScraper(),
        WalmartScraper(),
        BingShoppingScraper(),
        PriceSpyScraper(),
    ]

    all_results = []
    completed = 0

    def scrape(scraper):
        nonlocal completed
        try:
            if callback:
                callback(f"🔍 Searching {scraper.NAME}...", "info")
            results = scraper.search(query, session)
            if callback:
                callback(f"✅ {scraper.NAME}: {len(results)} results", "success")
            completed += 1
            return results
        except Exception as e:
            if callback:
                callback(f"⚠️ {scraper.NAME} failed: {str(e)[:50]}", "error")
            completed += 1
            return []

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(scrape, s): s for s in scrapers}
        for future in concurrent.futures.as_completed(futures):
            all_results.extend(future.result())

    return all_results


# ── GUI Application ──────────────────────────────────────────────────────────

class PriceHunterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("💰 Price Hunter — Smart Deal Finder")
        self.root.geometry("1100x750")
        self.root.minsize(900, 600)
        
        # Set icon and style
        self.setup_styles()
        
        # Variables
        self.original_product = None
        self.results = []
        self.original_price = None
        self.search_query = ""
        self.session = get_session()
        self.searching = False
        
        # Create UI
        self.create_widgets()
        
        # Center window
        self.center_window()
        
    def setup_styles(self):
        """Configure ttk styles for a modern look"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Colors
        self.bg_color = "#2b2b2b"
        self.fg_color = "#ffffff"
        self.accent_color = "#4CAF50"
        self.warning_color = "#ff9800"
        self.error_color = "#f44336"
        self.info_color = "#2196F3"
        
        # Configure root window
        self.root.configure(bg=self.bg_color)
        
        # Configure styles
        style.configure("Title.TLabel", 
                       font=("Segoe UI", 16, "bold"),
                       background=self.bg_color,
                       foreground=self.fg_color)
        
        style.configure("Header.TLabel",
                       font=("Segoe UI", 12, "bold"),
                       background=self.bg_color,
                       foreground=self.fg_color)
        
        style.configure("Normal.TLabel",
                       font=("Segoe UI", 10),
                       background=self.bg_color,
                       foreground=self.fg_color)
        
        style.configure("Success.TLabel",
                       font=("Segoe UI", 10),
                       background=self.bg_color,
                       foreground=self.accent_color)
        
        style.configure("Error.TLabel",
                       font=("Segoe UI", 10),
                       background=self.bg_color,
                       foreground=self.error_color)
        
        style.configure("Price.TLabel",
                       font=("Segoe UI", 14, "bold"),
                       background=self.bg_color,
                       foreground=self.accent_color)
        
        style.configure("Savings.TLabel",
                       font=("Segoe UI", 10, "bold"),
                       background=self.bg_color,
                       foreground=self.warning_color)
        
        style.configure("TButton",
                       font=("Segoe UI", 10),
                       padding=5)
        
        style.configure("Search.TButton",
                       font=("Segoe UI", 10, "bold"),
                       padding=8)
        
        style.configure("TEntry",
                       font=("Segoe UI", 10),
                       padding=5)
        
        style.configure("TFrame", background=self.bg_color)
        style.configure("TLabel", background=self.bg_color, foreground=self.fg_color)
        
    def center_window(self):
        """Center the window on screen"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
        
    def create_widgets(self):
        """Create all GUI widgets"""
        # Main container
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 20))
        
        title_label = ttk.Label(header_frame, 
                               text="💰 PRICE HUNTER — Find Cheaper Alternatives", 
                               style="Title.TLabel")
        title_label.pack()
        
        subtitle_label = ttk.Label(header_frame,
                                  text="Search across Google Shopping, Amazon, eBay, Walmart, and more",
                                  style="Normal.TLabel")
        subtitle_label.pack()
        
        # Separator
        separator = ttk.Separator(main_frame, orient='horizontal')
        separator.pack(fill=tk.X, pady=10)
        
        # Input section
        input_frame = ttk.Frame(main_frame)
        input_frame.pack(fill=tk.X, pady=10)
        
        # URL input
        url_frame = ttk.Frame(input_frame)
        url_frame.pack(fill=tk.X, pady=5)
        
        url_label = ttk.Label(url_frame, text="Product URL:", style="Header.TLabel", width=12)
        url_label.pack(side=tk.LEFT)
        
        self.url_entry = ttk.Entry(url_frame)
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 10))
        self.url_entry.bind("<Return>", lambda _: self.start_search())
        
        # Query input
        query_frame = ttk.Frame(input_frame)
        query_frame.pack(fill=tk.X, pady=5)
        
        query_label = ttk.Label(query_frame, text="Or search:", style="Header.TLabel", width=12)
        query_label.pack(side=tk.LEFT)
        
        self.query_entry = ttk.Entry(query_frame)
        self.query_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 10))
        self.query_entry.bind("<Return>", lambda _: self.start_search())
        
        # Search button
        button_frame = ttk.Frame(input_frame)
        button_frame.pack(fill=tk.X, pady=10)
        
        self.search_button = ttk.Button(button_frame, 
                                       text="🔍 Find Cheaper Alternatives", 
                                       command=self.start_search,
                                       style="Search.TButton")
        self.search_button.pack(pady=5)
        
        # Progress section
        self.progress_frame = ttk.Frame(main_frame)
        self.progress_frame.pack(fill=tk.X, pady=10)
        
        self.progress_bar = ttk.Progressbar(self.progress_frame, mode='indeterminate')
        self.status_label = ttk.Label(self.progress_frame, text="Ready to search", style="Normal.TLabel")
        self.status_label.pack()
        
        # Notebook for tabs
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Results tab
        self.results_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.results_frame, text="📊 Search Results")
        
        # Original product tab
        self.original_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.original_frame, text="📦 Original Product")
        
        # Create results view with scrollbar
        self.create_results_view()
        
        # Create original product view
        self.create_original_view()
        
        # Export button
        export_frame = ttk.Frame(main_frame)
        export_frame.pack(fill=tk.X, pady=10)
        
        self.export_button = ttk.Button(export_frame, 
                                       text="💾 Export Results", 
                                       command=self.export_results,
                                       state=tk.DISABLED)
        self.export_button.pack(side=tk.RIGHT)
        
    def create_results_view(self):
        """Create the scrollable results view"""
        # Canvas for scrolling
        canvas = tk.Canvas(self.results_frame, bg=self.bg_color, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.results_frame, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda _: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Bind mousewheel
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        canvas.bind_all("<MouseWheel>", on_mousewheel)
        
        # Store references to result frames for updating
        self.result_frames = []
        
    def create_original_view(self):
        """Create the original product view"""
        # Canvas for scrolling
        canvas = tk.Canvas(self.original_frame, bg=self.bg_color, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.original_frame, orient="vertical", command=canvas.yview)
        self.original_scrollable = ttk.Frame(canvas)
        
        self.original_scrollable.bind(
            "<Configure>",
            lambda _: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.original_scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Original product info will be added here dynamically
        self.original_info_frame = ttk.Frame(self.original_scrollable)
        self.original_info_frame.pack(fill=tk.X, padx=20, pady=20)
        
    def update_status(self, message, status_type="info"):
        """Update status label with color-coded message"""
        colors = {
            "info": self.info_color,
            "success": self.accent_color,
            "error": self.error_color,
            "warning": self.warning_color
        }
        color = colors.get(status_type, self.fg_color)
        
        self.status_label.config(text=message, foreground=color)
        self.root.update_idletasks()
        
    def clear_results(self):
        """Clear all results from the view"""
        for frame in self.result_frames:
            frame.destroy()
        self.result_frames.clear()
        
    def display_original_product(self, product):
        """Display original product information"""
        # Clear previous
        for widget in self.original_info_frame.winfo_children():
            widget.destroy()
        
        if not product:
            ttk.Label(self.original_info_frame, 
                     text="Could not extract product information from URL",
                     style="Error.TLabel").pack(pady=20)
            return
        
        # Title
        title_frame = ttk.Frame(self.original_info_frame)
        title_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(title_frame, text="Product:", style="Header.TLabel").pack(side=tk.LEFT)
        ttk.Label(title_frame, text=product.title[:100], 
                 style="Normal.TLabel", wraplength=600).pack(side=tk.LEFT, padx=(10, 0))
        
        # Source
        source_frame = ttk.Frame(self.original_info_frame)
        source_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(source_frame, text="Source:", style="Header.TLabel").pack(side=tk.LEFT)
        ttk.Label(source_frame, text=product.source, 
                 style="Normal.TLabel").pack(side=tk.LEFT, padx=(10, 0))
        
        # Price
        if product.price:
            price_frame = ttk.Frame(self.original_info_frame)
            price_frame.pack(fill=tk.X, pady=5)
            
            ttk.Label(price_frame, text="Price:", style="Header.TLabel").pack(side=tk.LEFT)
            ttk.Label(price_frame, text=f"${product.price:.2f}", 
                     style="Price.TLabel").pack(side=tk.LEFT, padx=(10, 0))
        
        # Rating
        if product.rating:
            rating_frame = ttk.Frame(self.original_info_frame)
            rating_frame.pack(fill=tk.X, pady=5)
            
            ttk.Label(rating_frame, text="Rating:", style="Header.TLabel").pack(side=tk.LEFT)
            ttk.Label(rating_frame, text=product.rating, 
                     style="Normal.TLabel").pack(side=tk.LEFT, padx=(10, 0))
        
        # URL with clickable link
        url_frame = ttk.Frame(self.original_info_frame)
        url_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(url_frame, text="URL:", style="Header.TLabel").pack(side=tk.LEFT)
        
        url_link = tk.Label(url_frame, text=product.url[:80] + "...", 
                           fg=self.info_color, bg=self.bg_color,
                           font=("Segoe UI", 9, "underline"),
                           cursor="hand2")
        url_link.pack(side=tk.LEFT, padx=(10, 0))
        url_link.bind("<Button-1>", lambda _: webbrowser.open(product.url))
        
    def display_results(self, results, original_price):
        """Display search results with clickable links"""
        self.clear_results()
        
        if not results:
            no_results = ttk.Frame(self.scrollable_frame)
            no_results.pack(fill=tk.X, pady=20)
            ttk.Label(no_results, text="❌ No cheaper alternatives found", 
                     style="Error.TLabel").pack()
            return
        
        # Separate cheaper and other results
        cheaper = [r for r in results if r.price and (not original_price or r.price < original_price)]
        other = [r for r in results if r not in cheaper]
        
        # Sort cheaper by savings percentage
        cheaper.sort(key=lambda x: x.savings_pct if x.savings_pct else 0, reverse=True)
        
        # Display cheaper alternatives
        if cheaper:
            header = ttk.Frame(self.scrollable_frame)
            header.pack(fill=tk.X, pady=(10, 5))
            
            ttk.Label(header, text=f"🏆 CHEAPER ALTERNATIVES ({len(cheaper)} found)", 
                     style="Header.TLabel", font=("Segoe UI", 14, "bold")).pack(anchor=tk.W)
            
            ttk.Separator(self.scrollable_frame, orient='horizontal').pack(fill=tk.X, pady=5)
            
            for i, product in enumerate(cheaper[:20], 1):
                self.create_result_card(product, i, is_cheaper=True)
        
        # Display other results
        if other and not original_price:
            header = ttk.Frame(self.scrollable_frame)
            header.pack(fill=tk.X, pady=(20, 5))
            
            ttk.Label(header, text=f"📋 OTHER RESULTS ({len(other)})", 
                     style="Header.TLabel", font=("Segoe UI", 14, "bold")).pack(anchor=tk.W)
            
            ttk.Separator(self.scrollable_frame, orient='horizontal').pack(fill=tk.X, pady=5)
            
            for i, product in enumerate(other[:10], 1):
                self.create_result_card(product, i, is_cheaper=False)
        
        # Update export button
        self.export_button.config(state=tk.NORMAL)
        
    def create_result_card(self, product, index, is_cheaper=True):
        """Create a card for a single result with clickable link"""
        card = ttk.Frame(self.scrollable_frame, relief=tk.RAISED, borderwidth=1)
        card.pack(fill=tk.X, pady=5, padx=5)
        
        # Title with rank
        title_frame = ttk.Frame(card)
        title_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        rank_label = ttk.Label(title_frame, text=f"#{index}", 
                              font=("Segoe UI", 12, "bold"))
        rank_label.pack(side=tk.LEFT, padx=(0, 10))
        
        title_text = product.title[:80] + "..." if len(product.title) > 80 else product.title
        title_label = ttk.Label(title_frame, text=title_text, 
                               font=("Segoe UI", 11, "bold"),
                               wraplength=600)
        title_label.pack(side=tk.LEFT)
        
        # Price and source
        info_frame = ttk.Frame(card)
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Price
        price_label = ttk.Label(info_frame, text=f"${product.price:.2f}", 
                               style="Price.TLabel")
        price_label.pack(side=tk.LEFT, padx=(30, 20))
        
        # Savings if applicable
        if is_cheaper and product.savings:
            savings_text = f"Save ${product.savings:.2f} ({product.savings_pct:.0f}%)"
            savings_label = ttk.Label(info_frame, text=savings_text, 
                                     style="Savings.TLabel")
            savings_label.pack(side=tk.LEFT, padx=(0, 20))
        
        # Source
        source_label = ttk.Label(info_frame, text=f"from {product.source}", 
                                style="Normal.TLabel")
        source_label.pack(side=tk.LEFT)
        
        # Rating if available
        if product.rating:
            rating_frame = ttk.Frame(card)
            rating_frame.pack(fill=tk.X, padx=10, pady=2)
            ttk.Label(rating_frame, text=f"⭐ {product.rating}", 
                     style="Normal.TLabel").pack(side=tk.LEFT, padx=(30, 0))
        
        # Clickable link
        link_frame = ttk.Frame(card)
        link_frame.pack(fill=tk.X, padx=10, pady=(5, 10))
        
        ttk.Label(link_frame, text="🔗", font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(30, 5))
        
        link_text = product.url[:70] + "..." if len(product.url) > 70 else product.url
        link_label = tk.Label(link_frame, text=link_text, 
                            fg=self.info_color, bg=self.bg_color,
                            font=("Segoe UI", 9, "underline"),
                            cursor="hand2")
        link_label.pack(side=tk.LEFT)
        link_label.bind("<Button-1>", lambda *_, url=product.url: webbrowser.open(url))
        
        # Store reference
        self.result_frames.append(card)
        
    def start_search(self):
        """Start the search process in a separate thread"""
        if self.searching:
            return
            
        url = self.url_entry.get().strip()
        query = self.query_entry.get().strip()
        
        if not url and not query:
            messagebox.showwarning("Input Required", 
                                  "Please enter a product URL or search query")
            return
        
        self.searching = True
        self.search_button.config(state=tk.DISABLED)
        self.progress_bar.pack(fill=tk.X, pady=5)
        self.progress_bar.start(10)
        self.clear_results()
        self.export_button.config(state=tk.DISABLED)
        
        # Start search in thread
        thread = threading.Thread(target=self.perform_search, args=(url, query))
        thread.daemon = True
        thread.start()
        
    def perform_search(self, url, query):
        """Perform the actual search (runs in thread)"""
        try:
            self.update_status("Initializing search...", "info")
            
            original_product = None
            search_query = query
            
            # Extract original product if URL provided
            if url:
                self.update_status("Extracting product information...", "info")
                extractor = OriginalProductExtractor(url, self.session)
                original_product = extractor.extract()
                
                self.root.after(0, self.display_original_product, original_product)
                
                if not search_query:
                    search_query = build_search_query(original_product, url)
                    self.update_status(f"Search query: {search_query}", "info")
            
            if not search_query or len(search_query) < 3:
                self.root.after(0, lambda: messagebox.showerror("Error", 
                    "Could not determine what to search for"))
                return
            
            # Run scrapers
            self.update_status("Searching across all stores...", "info")
            
            def status_callback(msg, msg_type):
                self.root.after(0, self.update_status, msg, msg_type)
            
            all_results = run_scrapers_parallel(search_query, self.session, status_callback)
            
            # Process results
            all_results = deduplicate(all_results)
            original_price = original_product.price if original_product else None
            all_results = compute_savings(all_results, original_price)
            
            # Sort by price
            all_results.sort(key=lambda p: p.price or float("inf"))
            
            # Store results
            self.original_product = original_product
            self.results = all_results
            self.original_price = original_price
            
            # Update GUI
            self.root.after(0, self.display_results, all_results, original_price)
            self.update_status(f"Found {len(all_results)} unique results", "success")
            
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Search Error", str(e)))
            self.update_status(f"Error: {str(e)}", "error")
        finally:
            self.searching = False
            self.root.after(0, self.search_complete)
            
    def search_complete(self):
        """Clean up after search completes"""
        self.progress_bar.stop()
        self.progress_bar.pack_forget()
        self.search_button.config(state=tk.NORMAL)
        
    def export_results(self):
        """Export results to JSON file"""
        if not self.results:
            return
            
        from tkinter import filedialog
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Save Results As"
        )
        
        if filename:
            data = {
                "original": self.original_product.to_dict() if self.original_product else None,
                "alternatives": [p.to_dict() for p in self.results],
                "total_found": len(self.results),
                "cheapest": self.results[0].to_dict() if self.results else None,
            }
            
            with open(filename, "w") as f:
                json.dump(data, f, indent=2)
            
            messagebox.showinfo("Export Complete", f"Results exported to {filename}")


def main():
    """Main entry point"""
    root = tk.Tk()
    app = PriceHunterGUI(root)
    
    # Handle command line arguments
    if len(sys.argv) > 1:
        url = sys.argv[1]
        if url.startswith(("http://", "https://")):
            app.url_entry.insert(0, url)
            # Auto-start search after a short delay
            root.after(500, app.start_search)
    
    root.mainloop()


if __name__ == "__main__":
    main()
