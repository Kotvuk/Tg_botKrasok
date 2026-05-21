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


def _site_img(soup_el) -> str:
    """Ищем изображения по реальному пути сайта /upload/iblock/"""
    # Приоритет — картинки из /upload/ (реальные фото товаров)
    for img in soup_el.find_all("img"):
        for attr in ("src", "data-src", "data-lazy-src", "data-original"):
            src = img.get(attr, "")
            if src and "/upload/" in src and not src.endswith(".gif"):
                return _abs(src)
    return ""


def _find_price(soup_el) -> str:
    for sel in [".catalog-element-offer-price", ".price", "[class*='price']", ".cost", "strong"]:
        for el in soup_el.select(sel):
            text = el.get_text(" ", strip=True)
            if any(c.isdigit() for c in text) and ("KZT" in text or "₸" in text or "тг" in text.lower() or any(c.isdigit() for c in text)):
                # Проверяем что это цена (есть цифры и похоже на деньги)
                if len(text) < 30:
                    return text
    # Fallback — ищем просто числа с "тенге"-контекстом
    for el in soup_el.find_all(string=lambda t: t and "KZT" in t):
        text = el.strip()
        if len(text) < 40:
            return text
    return "По запросу"


async def _fetch(url: str, session: aiohttp.ClientSession) -> Optional[str]:
    try:
        async with session.get(url, headers=HEADERS, timeout=TIMEOUT, ssl=False) as resp:
            if resp.status == 200:
                return await resp.text(encoding="utf-8", errors="replace")
    except Exception:
        pass
    return None


async def get_categories() -> list[dict]:
    async with aiohttp.ClientSession() as session:
        html = await _fetch(f"{SITE_URL}/catalog/", session)
        if not html:
            return []

        soup = BeautifulSoup(html, "lxml")
        categories: list[dict] = []

        for selector in [
            ".catalog-section-item",
            ".section-item",
            ".catalog-section",
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
                    if "/catalog/" not in href or href.count("/") < 2:
                        continue
                    name_el = (
                        item.find("h2") or item.find("h3")
                        or item.find(class_=lambda x: x and "name" in str(x).lower())
                        or link
                    )
                    name = name_el.get_text(strip=True)
                    if not name or len(name) < 3:
                        continue
                    categories.append({
                        "name": name,
                        "url": _abs(href),
                        "image": _site_img(item),
                    })
                if categories:
                    break

        # Fallback: все ссылки /catalog/xxx/
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
                    name = a.get_text(strip=True)
                    if name and len(name) > 2:
                        categories.append({"name": name, "url": _abs(href), "image": ""})

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
            "div[class*='catalog-element']",
            "div[class*='product']",
        ]:
            items = soup.select(selector)
            if len(items) >= 2:
                break

        # Fallback: ищем блоки с ссылками на товары и ценами
        if not items:
            candidates = []
            for div in soup.find_all("div"):
                a = div.find("a", href=True)
                img = div.find("img", src=lambda s: s and "/upload/" in s)
                if a and img and "/catalog/" in a.get("href", ""):
                    candidates.append(div)
            items = candidates[:8]

        seen_urls: set[str] = set()
        for item in items[:8]:
            link = item.find("a", href=True)
            if not link:
                continue
            href = link.get("href", "")
            if "/catalog/" not in href or href in seen_urls:
                continue
            seen_urls.add(href)

            name_el = (
                item.find("h2") or item.find("h3")
                or item.find(class_=lambda x: x and "name" in str(x).lower())
                or item.find(class_=lambda x: x and "title" in str(x).lower())
            )
            name = name_el.get_text(strip=True) if name_el else link.get_text(strip=True)
            if not name or len(name) < 3:
                continue

            image = _site_img(item)

            products.append({
                "name": name,
                "url": _abs(href),
                "price": _find_price(item),
                "image": image,
            })

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

        # Название
        name = ""
        for sel in ["h1", ".catalog-element-name", ".product-name"]:
            el = soup.select_one(sel)
            if el:
                name = el.get_text(strip=True)
                break
        if not name:
            name = "Без названия"

        # Цена
        price = _find_price(soup)

        # Изображение — ищем самый большой /upload/ img на странице
        image = ""
        # Сначала ищем в типичных блоках детальной страницы
        for sel in [
            ".catalog-element-big-picture img",
            ".product-image-big img",
            ".detail-picture img",
            ".swiper-slide img",
            "[class*='gallery'] img",
            "[class*='detail'] img",
        ]:
            el = soup.select_one(sel)
            if el:
                for attr in ("src", "data-src", "data-original"):
                    src = el.get(attr, "")
                    if src and "/upload/" in src:
                        image = _abs(src)
                        break
            if image:
                break

        # Fallback — любое /upload/ изображение на странице (кроме иконок)
        if not image:
            for img in soup.find_all("img"):
                src = img.get("src", "") or img.get("data-src", "")
                if src and "/upload/iblock/" in src and not src.endswith(".gif"):
                    # Берём первое — обычно главное фото товара
                    image = _abs(src)
                    break

        # Описание
        description = ""
        for sel in [
            ".catalog-element-description",
            ".detail-text",
            "[class*='description']",
            ".tabs-content",
        ]:
            el = soup.select_one(sel)
            if el:
                description = el.get_text(" ", strip=True)[:600]
                break

        # Бренд
        brand = ""
        for sel in [".brand-name", "[class*='brand']", "[itemprop='brand']"]:
            el = soup.select_one(sel)
            if el:
                brand = el.get_text(strip=True)
                break

        # Характеристики
        properties: dict[str, str] = {}
        for table in soup.select("table"):
            for row in table.find_all("tr"):
                cols = row.find_all("td")
                if len(cols) >= 2:
                    k = cols[0].get_text(strip=True)
                    v = cols[1].get_text(strip=True)
                    if k and v and len(k) < 60:
                        properties[k] = v
            if properties:
                break

        # Fallback: dl/dt/dd
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
    search_urls = [
        f"{SITE_URL}/search/?q={encoded}",
        f"{SITE_URL}/catalog/?q={encoded}",
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

            seen_urls: set[str] = set()
            for item in items[:10]:
                link = item.find("a", href=True)
                if not link:
                    continue
                href = link.get("href", "")
                if "/catalog/" not in href or href in seen_urls:
                    continue
                seen_urls.add(href)

                name_el = (
                    item.find("h2") or item.find("h3")
                    or item.find(class_=lambda x: x and "name" in str(x).lower())
                )
                name = name_el.get_text(strip=True) if name_el else link.get_text(strip=True)
                if not name:
                    continue

                products.append({
                    "name": name,
                    "url": _abs(href),
                    "price": _find_price(item),
                    "image": _site_img(item),
                })

            if products:
                return products

    return []
