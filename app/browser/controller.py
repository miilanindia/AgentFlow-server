import asyncio
from concurrent.futures import ThreadPoolExecutor
from playwright.sync_api import sync_playwright
import base64
from typing import Optional, Dict
from urllib.parse import urlparse, urlunparse, parse_qs, unquote
from loguru import logger


def normalize_url(url: str) -> str:
    """
    LLM kabhi-kabhi bare domain deta hai (jaise 'tryremotico.com/jobs').
    Yeh function scheme missing hone par 'https://' add karta hai,
    aur agar phir bhi valid URL nahi banta toh ValueError raise karta hai
    (taaki caller isko gracefully handle kar sake, crash na ho).
    """
    url = (url or "").strip()
    if not url:
        raise ValueError("Empty URL provided")

    parsed = urlparse(url)
    if not parsed.scheme:
        # Scheme missing hai -> https:// prepend karke dobara parse karo
        parsed = urlparse(f"https://{url}")

    if not parsed.netloc or "." not in parsed.netloc:
        raise ValueError(f"'{url}' is not a valid absolute URL")

    return urlunparse(parsed)

class BrowserController:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.page = None
        self.last_status_code = None  # Real HTTP status of last goto() (Level-2 dead-link detection)
        # Ek single thread lock kar diya, taaki greenlet error na aaye
        self.executor = ThreadPoolExecutor(max_workers=1)

    # --- Sync Methods (Sirf thread ke andar chalenge) ---
    def _start_sync(self):
        logger.info("[BROWSER] Launching Chromium browser with Playwright...")
        self.playwright = sync_playwright().start()
        # Stealth mode ke saath launch
        self.browser = self.playwright.chromium.launch(headless=True, args=["--start-maximized"])
        logger.info("[BROWSER] Browser launched. Creating new context...")
        context = self.browser.new_context(viewport={"width": 1280, "height": 800})
        
        # Real browser jaisa User-Agent set kar rahe hain
        context.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        
        self.page = context.new_page()
        logger.info("[BROWSER] New page created in context.")
        
        # STEALTH INITIALIZATION (Bot detection chupane ke liye)
        try:
            from playwright_stealth import Stealth
            logger.info("[BROWSER] Applying stealth v2 configurations...")
            Stealth().apply_stealth_sync(self.page)
            logger.info("[BROWSER] Stealth mode successfully initialized.")
        except ImportError:
            logger.warning("[BROWSER] playwright-stealth not installed. Bot detection might trigger.")

    def _dismiss_cookie_banners_sync(self):
        logger.info("[BROWSER] Checking for cookie consent banners...")
        try:
            # Common button texts for cookie consent (case-insensitive checks via has-text/lowercase combos)
            cookie_buttons = self.page.locator(
                'button:has-text("Accept"), button:has-text("accept"), '
                'button:has-text("Agree"), button:has-text("agree"), '
                'button:has-text("Allow"), button:has-text("allow"), '
                'button:has-text("Consent"), button:has-text("consent"), '
                'button:has-text("I accept"), button:has-text("I Accept"), '
                'button:has-text("OK"), button:has-text("ok"), '
                'a:has-text("Accept"), a:has-text("accept"), '
                'a:has-text("Agree"), a:has-text("agree"), '
                '[role="button"]:has-text("Accept"), [role="button"]:has-text("accept")'
            )
            
            count = cookie_buttons.count()
            if count > 0:
                logger.info(f"[BROWSER] Found {count} potential cookie banner buttons.")
                for i in range(count):
                    btn = cookie_buttons.nth(i)
                    if btn.is_visible() and btn.is_enabled():
                        text = btn.inner_text().strip().replace("\n", " ")
                        logger.info(f"[BROWSER] Clicking cookie consent button: '{text}'")
                        btn.click(timeout=2000)
                        self.page.wait_for_timeout(1000)  # Wait for animation/overlay to disappear
                        break
            else:
                logger.info("[BROWSER] No cookie banner buttons detected.")
        except Exception as e:
            logger.warning(f"[BROWSER] Cookie banner dismissal encountered a non-critical error: {e}")

    def _goto_sync(self, url: str):
        clean_url = normalize_url(url)
        logger.info(f"[BROWSER] Navigating to: {clean_url}")
        self.last_status_code = None
        try:
            response = self.page.goto(clean_url, wait_until="domcontentloaded", timeout=20000)
            self.last_status_code = response.status if response else None
            logger.info(f"[BROWSER] Successfully loaded: {clean_url} (HTTP {self.last_status_code})")
            self.page.wait_for_timeout(1000)
            self._dismiss_cookie_banners_sync()
        except Exception as e:
            logger.error(f"[BROWSER] Failed to load URL: {clean_url}. Error: {e}")
            # Clean, readable error - caller (tool) will feed this back to the LLM
            raise ValueError(f"Failed to load '{clean_url}': {e}")
        self.page.wait_for_timeout(2000)

    def _get_screenshot_sync(self) -> str:
        logger.info("[BROWSER] Capturing page screenshot...")
        try:
            screenshot_bytes = self.page.screenshot(timeout=5000)
            logger.info("[BROWSER] Screenshot captured successfully.")
            return base64.b64encode(screenshot_bytes).decode('utf-8')
        except Exception as e:
            logger.warning(f"[BROWSER] Screenshot capture failed: {e}")
            return ""  # Agar screenshot fail ho jaye, toh empty string return karo (non-critical)
    
    def _get_page_text_sync(self) -> str:
        logger.info("[BROWSER] Extracting page inner text...")
        # Page ka normal text lo
        text = self.page.inner_text("body")
        logger.info(f"[BROWSER] Extracted {len(text)} characters of body text.")
        
        # Links extract karo taaki LLM ko 'Apply' URL mile
        try:
            logger.info("[BROWSER] Extracting available links on page...")
            links = self.page.eval_on_selector_all(
                "a",
                "els => els.map(el => ({text: el.innerText, href: el.href})).filter(l => l.text && l.href)"
            )
            link_text = "\n\n--- AVAILABLE LINKS ON PAGE ---\n"
            for l in links[:50]: # Top 50 links
                link_text += f"{l['text'].strip()} -> {l['href']}\n"
            logger.info(f"[BROWSER] Found {len(links)} links, appended top {min(len(links), 50)} to text.")
            return text + link_text
        except Exception as e:
            logger.warning(f"[BROWSER] Failed to extract links: {e}")
            return text

    def _get_search_results_sync(self, max_results: int = 5):
        """
        DuckDuckGo HTML results page se REAL result links nikaalta hai
        (raw text ki jagah), taaki LLM ko guess/hallucinate na karna pade.
        """
        logger.info(f"[BROWSER] Extracting DuckDuckGo search results (max={max_results})...")
        try:
            raw_results = self.page.eval_on_selector_all(
                "a.result__a",
                "els => els.map(el => ({title: el.innerText, url: el.href}))",
            )
            logger.info(f"[BROWSER] Parsed {len(raw_results)} raw search result links from DuckDuckGo.")
            
            results = []
            for r in raw_results:
                url = r.get("url", "")
                if "duckduckgo.com/l/?uddg=" in url:
                    try:
                        parsed = urlparse(url)
                        qs = parse_qs(parsed.query)
                        real_url = qs.get("uddg", [None])[0]
                        if real_url:
                            url = unquote(real_url)
                    except Exception as parse_err:
                        logger.warning(f"[BROWSER] Failed to decode DuckDuckGo redirect URL '{url}': {parse_err}")
                
                results.append({
                    "title": r.get("title", "").strip(),
                    "url": url
                })
            
            logger.info(f"[BROWSER] Decoded {len(results)} clean search results.")
        except Exception as e:
            logger.error(f"[BROWSER] Failed to parse search results: {e}")
            results = []
        return results[:max_results]

    def _close_sync(self):
        logger.info("[BROWSER] Closing browser context and Playwright instance...")
        if self.browser:
            self.browser.close()
            logger.info("[BROWSER] Browser closed.")
        if self.playwright:
            self.playwright.stop()
            logger.info("[BROWSER] Playwright stopped.")

    # --- Async Wrappers (LangGraph inhe call karega) ---
    async def start(self):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self.executor, self._start_sync)

    async def goto(self, url: str):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self.executor, self._goto_sync, url)

    def get_last_status(self) -> Optional[int]:
        """Real HTTP status code of the last goto() call (set synchronously before goto() returns)."""
        return self.last_status_code

    async def get_screenshot(self) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, self._get_screenshot_sync)

    async def get_page_text(self) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, self._get_page_text_sync)

    async def get_search_results(self, max_results: int = 5):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, self._get_search_results_sync, max_results)

    async def close(self):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self.executor, self._close_sync)

class BrowserManager:
    """Per-task browser controller registry for safe concurrent execution."""
    def __init__(self):
        self._controllers: Dict[str, BrowserController] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(self, task_id: str) -> BrowserController:
        async with self._lock:
            if task_id not in self._controllers:
                logger.info(f"[BROWSER MANAGER] Creating dedicated BrowserController for Task {task_id}")
                controller = BrowserController()
                await controller.start()
                self._controllers[task_id] = controller
            return self._controllers[task_id]

    async def close_and_remove(self, task_id: str):
        async with self._lock:
            controller = self._controllers.pop(task_id, None)
            if controller:
                logger.info(f"[BROWSER MANAGER] Closing and removing BrowserController for Task {task_id}")
                try:
                    await controller.close()
                except Exception as e:
                    logger.error(f"[BROWSER MANAGER] Error closing browser for Task {task_id}: {e}")

browser_manager = BrowserManager()
browser_controller = BrowserController()