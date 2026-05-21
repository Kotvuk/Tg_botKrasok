import aiohttp
from bs4 import BeautifulSoup
from typing import Optional
from config import SITE_URL

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

TIMEOUT = aiohttp.ClientTimeout(total=20)


def _abs(url: str) -> str:
    if not url:
        return ""
    if url.startswith("http"):
        return url
    if url.startswith("//"):
        return "https:" + url
    return SITE_URL + (url if url.startswith("/") else "/" + url)


async def _fetch(url: str, session: aiohttp.ClientSession) -> Optional[str]:
    try:
        async with session.get(url, headers=HEADERS, timeout=TIMEOUT, ssl=False) as resp:
            if resp.status == 200:
                return await resp.text(encoding="utf-8", errors="replace")
    except Exception:
        pass
    return None


def _find_price(soup_el) -> str:
    for sel in [
        ".catalog-element-offer-price",
        ".price",
        "[class*='price']",
        ".cost",
    ]:
        el = soup_el.select_one(sel)
        if el:
            text = el.get_text(" ", strip=True)
            if any(c.isdigit() for c in text):
                return text
    return "По запросу"


def _find_img(soup_el, *, attribute: bool = False) -> str:
    img = soup_el.find("img")
    if not img:
        return ""
    # Prefer high-res variants
    for attr in ("data-src", "data-lazy-src", "data-original", "src"):
        src = img.get(attr, "")
        if src and not src.endswith(".gif") and "placeholder" not in src:
            return _abs(src)
    return ""


async def get_categories() -> list[dict]:
    async with aiohttp.ClientSession() as session:
        html = await _fetch(f"{SITE_URL}/catalog/", session)
        if not html:
            return []

        soup = BeautifulSoup(html, "lxml")
        categories: list[dict] = []

        # Bitrix24 typical selectors for catalog sections
        for selector in [
            ".catalog-section-item",
            ".section-item",
            ".catalog-section",
            ".catalog-section-list li",
            ".bx-catalog-section",
            "div[class*='section']",
        ]:
            items = soup.select(selector)
            if len(items) >= 3:
                for item in items[:20]:
                    link = item.find("a", href=True)
                    if not link:
                        continue
                    href = link.get("href", "")
                    if "/catalog/" not in href:
                        continue
                    name_el = (
                        item.find("h2")
                        or item.find("h3")
                        or item.find(class_=lambda x: x and "name" in str(x).lower())
                        or link
                    )
                    name = name_el.get_text(strip=True)
                    if not name or len(name) < 3:
                        continue
                    categories.append({
                        "name": name,
                        "url": _abs(href),
                        "image": _find_img(item),
                    })
                if categories:
                    break

        # Fallback: grab all /catalog/xxx/ nav links
        if not categories:
            seen: set[str] = set()
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                if (
                    href.startswith("/catalog/")
                    and href.count("/") == 3
                    and href not in seen
                    and href != "/catalog/"
                ):
                    seen.add(href)
                    categories.append({
                        "name": a.get_text(strip=True) or href,
                        "url": _abs(href),
                        "image": "",
                    })
        return categories


async def get_products(category_url: str, page: int = 1) -> dict:
    url = _abs(category_url)
    if page > 1:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}PAGEN_1={page}"

    async with aiohttp.ClientSession() as session:
        html = await _fetch(url, session)
        if not html:
            return {"products": [], "has_next": False, "page": page}

        soup = BeautifulSoup(html, "lxml")
        products: list[dict] = []
        items: list = []

        for selector in [
            ".catalog-element-item",
            ".catalog-item-block",
            ".product-item",
            "[data-entity='product']",
            ".bx-catalog-element",
            "div[class*='catalog-element']",
            "div[class*='product']",
        ]:
            items = soup.select(selector)
            if len(items) >= 2:
                break

        for item in items[:8]:
            link = item.find("a", href=True)
            if not link:
                continue
            href = link.get("href", "")
            if "/catalog/" not in href:
                continue

            name_el = (
                item.find("h2")
                or item.find("h3")
                or item.find(class_=lambda x: x and "name" in str(x).lower())
                or item.find(class_=lambda x: x and "title" in str(x).lower())
            )
            name = name_el.get_text(strip=True) if name_el else link.get_text(strip=True)
            if not name or len(name) < 3:
                continue

            products.append({
                "name": name,
                "url": _abs(href),
                "price": _find_price(item),
                "image": _find_img(item),
            })

        # Next page detection
        has_next = bool(
            soup.select_one(".bx-pag-next, .pager-next, a[title*='Следующая'], a[class*='next']")
        ) or len(products) >= 8

        return {"products": products, "has_next": has_next, "page": page}


async def get_product_detail(product_url: str) -> Optional[dict]:
    url = _abs(product_url)

    async with aiohttp.ClientSession() as session:
        html = await _fetch(url, session)
        if not html:
            return None

        soup = BeautifulSoup(html, "lxml")

        # Name
        name = ""
        for sel in ["h1", ".catalog-element-name h1", ".product-name"]:
            el = soup.select_one(sel)
            if el:
                name = el.get_text(strip=True)
                break
        if not name:
            name = "Без названия"

        # Price
        price = _find_price(soup)

        # Image — prefer detail/gallery images
        image = ""
        for sel in [
            ".catalog-element-big-picture img",
            ".product-image-big img",
            ".swiper-slide img",
            ".detail-picture img",
            ".product-detail-gallery img",
            "img[class*='detail']",
        ]:
            el = soup.select_one(sel)
            if el:
                for attr in ("data-src", "data-original", "src"):
                    src = el.get(attr, "")
                    if src and "placeholder" not in src:
                        image = _abs(src)
                        break
            if image:
                break

        # Description
        description = ""
        for sel in [
            ".catalog-element-description",
            ".product-detail-tab-description",
            ".detail-text",
            "[class*='description']",
        ]:
            el = soup.select_one(sel)
            if el:
                description = el.get_text(" ", strip=True)[:600]
                break

        # Brand
        brand = ""
        for sel in [".brand-name", "[class*='brand']", "[itemprop='brand']"]:
            el = soup.select_one(sel)
            if el:
                brand = el.get_text(strip=True)
                break

        # Properties table
        properties: dict[str, str] = {}
        for table in soup.select("table[class*='prop'], table[class*='char'], .props_main table"):
            for row in table.find_all("tr"):
                cols = row.find_all("td")
                if len(cols) >= 2:
                    k = cols[0].get_text(strip=True)
                    v = cols[1].get_text(strip=True)
                    if k and v:
                        properties[k] = v
            if properties:
                break

        # Fallback: look for dl/dt/dd pairs
        if not properties:
            for dl in soup.find_all("dl"):
                keys = [dt.get_text(strip=True) for dt in dl.find_all("dt")]
                vals = [dd.get_text(strip=True) for dd in dl.find_all("dd")]
                for k, v in zip(keys, vals):
                    if k and v:
                        properties[k] = v

        return {
            "name": name,
            "price": price,
            "image": image,
            "description": description,
            "brand": brand,
            "properties": properties,
            "url": url,
        }


async def search_products(query: str) -> list[dict]:
    encoded = query.replace(" ", "+")
    # Try common Bitrix24 search URLs
    search_urls = [
        f"{SITE_URL}/search/?q={encoded}",
        f"{SITE_URL}/catalog/?q={encoded}",
        f"{SITE_URL}/?s={encoded}",
    ]

    async with aiohttp.ClientSession() as session:
        for search_url in search_urls:
            html = await _fetch(search_url, session)
            if not html:
                continue

            soup = BeautifulSoup(html, "lxml")
            products: list[dict] = []
            items: list = []

            for selector in [
                ".catalog-element-item",
                ".catalog-item-block",
                ".product-item",
                ".search-result-item",
                "[data-entity='product']",
                "div[class*='catalog-element']",
            ]:
                items = soup.select(selector)
                if items:
                    break

            for item in items[:10]:
                link = item.find("a", href=True)
                if not link:
                    continue
                href = link.get("href", "")
                if "/catalog/" not in href:
                    continue

                name_el = (
                    item.find("h2")
                    or item.find("h3")
                    or item.find(class_=lambda x: x and "name" in str(x).lower())
                )
                name = name_el.get_text(strip=True) if name_el else link.get_text(strip=True)
                if not name:
                    continue

                products.append({
                    "name": name,
                    "url": _abs(href),
                    "price": _find_price(item),
                    "image": _find_img(item),
                })

            if products:
                return products

    return []
