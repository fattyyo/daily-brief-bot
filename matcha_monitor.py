"""監控丸久小山園（Marukyu Koyamaen）抹茶粉補貨狀態。

網站有 Cloudflare 防護，一般 requests/curl 會被 403 擋下，
所以改用 Playwright 開真的 headless Chromium 過 JS challenge 後再解析 HTML。
"""

import asyncio
import json
import logging
import time
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

import config

log = logging.getLogger(__name__)

CATALOG_URL = "https://www.marukyu-koyamaen.co.jp/english/shop/products/catalog/matcha/principal"
STATE_PATH = Path(__file__).parent / "matcha_state.json"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# 常駐一個 headless Chromium instance 重複使用，避免每次檢查（預設每 10 分鐘一次）
# 都要重新啟動整個瀏覽器行程；只有每次檢查用的 context/page 是用完即丟。
_playwright = None
_browser = None
_browser_lock = asyncio.Lock()


async def _get_browser():
    global _playwright, _browser
    async with _browser_lock:
        if _browser is None or not _browser.is_connected():
            if _playwright is None:
                _playwright = await async_playwright().start()
            _browser = await _playwright.chromium.launch(headless=True)
        return _browser


async def _reset_browser():
    """瀏覽器疑似壞掉時強制丟棄，下次呼叫 _get_browser() 會重新啟動一個。"""
    global _browser
    if _browser is not None:
        try:
            await _browser.close()
        except Exception:
            pass
        _browser = None


def _load_state() -> dict:
    """回傳 {"products": {id: status}, "last_report_at": epoch|None}。

    舊版狀態檔是扁平的 {id: status}，這裡自動升級成新格式，不用手動刪檔。
    """
    empty = {"products": {}, "last_report_at": None}
    if not STATE_PATH.exists():
        return empty
    try:
        raw = json.loads(STATE_PATH.read_text())
    except Exception:
        log.warning("讀取抹茶庫存狀態檔失敗，視為初次執行")
        return empty
    if not isinstance(raw, dict):
        return empty
    if "products" in raw:
        return {
            "products": raw.get("products") or {},
            "last_report_at": raw.get("last_report_at"),
        }
    return {"products": raw, "last_report_at": None}


def _save_state(state: dict):
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2))


async def fetch_products(retries: int = 3) -> list[dict]:
    """抓取抹茶目錄頁，回傳每項商品的 id / 名稱 / 連結 / 庫存狀態。"""
    last_err = None
    for attempt in range(1, retries + 1):
        context = None
        try:
            browser = await _get_browser()
            context = await browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 900},
                locale="en-US",
            )
            page = await context.new_page()
            await page.goto(CATALOG_URL, wait_until="domcontentloaded", timeout=30000)
            # 直接等商品清單出現，比固定 sleep 更能撐過 Cloudflare 的 JS 驗證頁
            await page.wait_for_selector("ul.products li.product", timeout=25000)
            html = await page.content()

            products = _parse_products(html)
            if products:
                return products
            last_err = RuntimeError("頁面已載入但找不到任何商品，網站結構可能改版了")
        except Exception as e:
            last_err = e
            log.warning("抓取抹茶庫存第 %d/%d 次嘗試失敗：%s", attempt, retries, e)
            # 瀏覽器可能已經處於壞掉的狀態（崩潰、被 Cloudflare 卡死等），
            # 強制重開，避免後續每次呼叫都用同一個壞掉的 instance 一直失敗
            await _reset_browser()
            if attempt < retries:
                await asyncio.sleep(3)
        finally:
            if context:
                await context.close()
    raise last_err or RuntimeError("抓取抹茶庫存失敗")


def _parse_products(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    products = []
    for li in soup.select("ul.products li.product"):
        item_id = (li.get("id") or "").replace("item-", "")
        classes = li.get("class") or []
        if "outofstock" in classes:
            status = "outofstock"
        elif "instock" in classes:
            status = "instock"
        else:
            status = "unknown"

        link = li.select_one("a.woocommerce-loop-product__link")
        name_tag = li.select_one(".product-name h4")
        if not item_id or not link:
            continue

        products.append({
            "id": item_id,
            "name": name_tag.get_text(strip=True) if name_tag else link.get("title", "未知商品"),
            "url": link.get("href", CATALOG_URL),
            "status": status,
        })
    return products


async def check() -> dict:
    """比對這次與上次的庫存狀態，回傳這次要通知使用者的內容，並更新狀態檔。

    回傳 {"products": 全部商品, "restocked": 剛變成有貨的商品, "quiet_hours": float|None}。
    `quiet_hours` 有值代表已經連續這麼多小時沒有任何補貨，該回報一次「還是沒貨」。

    第一次執行（沒有舊狀態檔）只會建立基準值、不會發通知，避免開機時整包炸出來。
    """
    products = await fetch_products()
    state = _load_state()
    old_products = state["products"]
    is_first_run = not old_products
    now = time.time()

    new_products = {}
    restocked = []
    for p in products:
        new_products[p["id"]] = p["status"]
        if is_first_run:
            continue
        if p["status"] == "instock" and old_products.get(p["id"]) != "instock":
            restocked.append(p)

    # last_report_at = 上次「跟使用者說過話」的時間（補貨通知或無補貨回報）。
    # 沒有值（初次執行、或從舊版狀態檔升級）就從現在起算，不會一上線就回報。
    last_report_at = state["last_report_at"] or now
    idle_seconds = config.MATCHA_IDLE_REPORT_HOURS * 3600
    quiet_hours = None

    if restocked:
        last_report_at = now
    elif idle_seconds > 0 and now - last_report_at >= idle_seconds:
        quiet_hours = (now - last_report_at) / 3600
        last_report_at = now

    _save_state({"products": new_products, "last_report_at": last_report_at})
    return {"products": products, "restocked": restocked, "quiet_hours": quiet_hours}
