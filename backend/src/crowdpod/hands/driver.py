"""Browser drivers. The agent only uses this small interface, so a Playwright MCP
driver could replace the direct Playwright one without changing the agent."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from ..models import HandsDecision, Observation

OBSERVE_JS = (Path(__file__).with_name("observe.js")).read_text(encoding="utf-8")

# device -> (width, height, is_mobile)
VIEWPORTS: dict[str, tuple[int, int, bool]] = {
    "budget-android": (360, 740, True),
    "mid-android": (393, 851, True),
    "smartwatch": (393, 851, True),  # people check the companion app on the phone
    "iphone": (390, 844, True),
    "shared-tablet": (800, 1280, True),
    "ipad": (820, 1180, True),
    "laptop": (1366, 768, False),
}


class BrowserDriver(ABC):
    @abstractmethod
    async def goto(self, url: str) -> None: ...

    @abstractmethod
    async def observe(self) -> Observation: ...

    @abstractmethod
    async def act(self, decision: HandsDecision) -> str:
        """Carry out the action. Returns an error message, or "" on success."""

    @abstractmethod
    async def screenshot(self, path: Path) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...


class PlaywrightBrowser:
    """One Chromium process shared by every session in a run."""

    def __init__(self, headless: bool = True, slow_mo: int = 0):
        self.headless = headless
        self.slow_mo = slow_mo
        self._pw: Playwright | None = None
        self._browser: Browser | None = None

    async def __aenter__(self) -> "PlaywrightBrowser":
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self.headless, slow_mo=self.slow_mo)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    async def driver(self, device: str) -> "PlaywrightDriver":
        assert self._browser, "use PlaywrightBrowser as an async context manager"
        w, h, mobile = VIEWPORTS.get(device, VIEWPORTS["mid-android"])
        context = await self._browser.new_context(
            viewport={"width": w, "height": h}, is_mobile=mobile, has_touch=mobile, locale="en-IN"
        )
        return PlaywrightDriver(context, await context.new_page())


class PlaywrightDriver(BrowserDriver):
    def __init__(self, context: BrowserContext, page: Page):
        self.context = context
        self.page = page

    async def _settle(self) -> None:
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=5000)
            await self.page.wait_for_load_state("networkidle", timeout=2000)
        except Exception:
            pass  # busy pages never go idle; carry on with what is there

    async def goto(self, url: str) -> None:
        await self.page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await self._settle()

    async def observe(self) -> Observation:
        return Observation.model_validate(await self.page.evaluate(OBSERVE_JS))

    async def act(self, d: HandsDecision) -> str:
        try:
            if d.action == "click":
                await self.page.click(f'[data-cp-id="{d.target}"]', timeout=5000)
            elif d.action == "type":
                await self.page.fill(f'[data-cp-id="{d.target}"]', d.text, timeout=5000)
            elif d.action == "scroll":
                h = self.page.viewport_size["height"] if self.page.viewport_size else 800
                await self.page.mouse.wheel(0, -0.8 * h if d.text == "up" else 0.8 * h)
                await self.page.wait_for_timeout(300)
            elif d.action == "back":
                await self.page.go_back(timeout=10000)
            else:
                return ""
            await self._settle()
            return ""
        except Exception as e:
            return f"{type(e).__name__}: {str(e).splitlines()[0][:200]}"

    async def screenshot(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        await self.page.screenshot(path=str(path))

    async def close(self) -> None:
        await self.context.close()
