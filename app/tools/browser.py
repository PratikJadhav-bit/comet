from typing import Dict, Any, List, Optional
from app.tools.registry import BaseTool, ToolSchema, ToolParameter, ToolResult, ToolCategory
from app.security.risk import assess_risk
from app.security.permissions import ActionType
from app.config import settings
import asyncio
import os
import base64


class BrowserManager:
    _instance = None
    _browser = None
    _context = None
    _page = None
    _pages: List[Any] = []

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def initialize(self):
        if self._browser is None:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=settings.browser_headless,
                args=["--disable-blink-features=AutomationControlled"]
            )
            self._context = await self._browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                accept_downloads=True
            )
            self._page = await self._context.new_page()
            self._pages = [self._page]
            self._page.set_default_timeout(settings.browser_timeout)

    async def get_page(self):
        if self._page is None:
            await self.initialize()
        return self._page

    async def new_page(self, url: str = None):
        """Create a new tab/page"""
        page = await self._context.new_page()
        page.set_default_timeout(settings.browser_timeout)
        self._pages.append(page)
        self._page = page
        if url:
            await page.goto(url, wait_until="networkidle")
        return page

    async def switch_page(self, index: int):
        """Switch to a specific tab by index"""
        if 0 <= index < len(self._pages):
            self._page = self._pages[index]
            await self._page.bring_to_front()
            return self._page
        return None

    async def close_page(self, index: int = None):
        """Close a specific tab"""
        if index is None:
            index = len(self._pages) - 1
        if 0 <= index < len(self._pages):
            page = self._pages.pop(index)
            await page.close()
            if self._pages:
                self._page = self._pages[-1]
            return True
        return False

    async def get_pages(self):
        """Get list of all open pages"""
        return self._pages

    async def close(self):
        if self._page:
            await self._page.close()
            self._page = None
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if hasattr(self, '_playwright'):
            await self._playwright.stop()


browser_manager = BrowserManager()


class NavigateTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="browser.navigate",
            description="Navigate to a URL in the browser",
            category=ToolCategory.BROWSER,
            parameters=[
                ToolParameter(name="url", type="string", description="URL to navigate to", required=True),
                ToolParameter(name="wait_until", type="string", description="Wait condition", required=False, default="networkidle", enum=["load", "domcontentloaded", "networkidle"]),
                ToolParameter(name="timeout", type="integer", description="Timeout in milliseconds", required=False, default=30000),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{"url": "https://example.com"}]
        )

    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        url = arguments["url"]
        wait_until = arguments.get("wait_until", "networkidle")
        timeout = arguments.get("timeout", 30000)

        try:
            page = await browser_manager.get_page()
            response = await page.goto(url, wait_until=wait_until, timeout=timeout)
            
            return ToolResult(success=True, data={
                "url": page.url,
                "title": await page.title(),
                "status": response.status if response else None
            })
        except Exception as e:
            return ToolResult(success=False, error=f"Navigation failed: {str(e)}")


class NewTabTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="browser.new_tab",
            description="Open a new browser tab",
            category=ToolCategory.BROWSER,
            parameters=[
                ToolParameter(name="url", type="string", description="Optional URL to navigate to in new tab", required=False),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{"url": "https://example.com"}]
        )

    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        url = arguments.get("url")

        try:
            page = await browser_manager.new_page(url)
            return ToolResult(success=True, data={
                "tab_index": len(browser_manager._pages) - 1,
                "url": page.url if not url else url,
                "title": await page.title()
            })
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to create new tab: {str(e)}")


class SwitchTabTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="browser.switch_tab",
            description="Switch to a specific browser tab by index",
            category=ToolCategory.BROWSER,
            parameters=[
                ToolParameter(name="index", type="integer", description="Tab index (0-based)", required=True),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{"index": 0}]
        )

    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        index = arguments["index"]

        try:
            page = await browser_manager.switch_page(index)
            if not page:
                return ToolResult(success=False, error=f"Tab index {index} not found")
            
            return ToolResult(success=True, data={
                "tab_index": index,
                "url": page.url,
                "title": await page.title()
            })
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to switch tab: {str(e)}")


class CloseTabTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="browser.close_tab",
            description="Close a browser tab",
            category=ToolCategory.BROWSER,
            parameters=[
                ToolParameter(name="index", type="integer", description="Tab index to close (default: current)", required=False),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{"index": 1}]
        )

    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        index = arguments.get("index")

        try:
            success = await browser_manager.close_page(index)
            if not success:
                return ToolResult(success=False, error=f"Tab index {index} not found")
            
            return ToolResult(success=True, data={"closed": True, "remaining_tabs": len(browser_manager._pages)})
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to close tab: {str(e)}")


class ListTabsTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="browser.list_tabs",
            description="List all open browser tabs",
            category=ToolCategory.BROWSER,
            parameters=[],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{}]
        )

    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        try:
            pages = await browser_manager.get_pages()
            tabs = []
            for i, page in enumerate(pages):
                tabs.append({
                    "index": i,
                    "url": page.url,
                    "title": await page.title(),
                    "is_current": page == browser_manager._page
                })
            
            return ToolResult(success=True, data={"tabs": tabs, "count": len(tabs)})
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to list tabs: {str(e)}")


class ReadPageTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="browser.read_page",
            description="Read the visible text content of the current page",
            category=ToolCategory.BROWSER,
            parameters=[
                ToolParameter(name="selector", type="string", description="CSS selector to extract specific element", required=False),
                ToolParameter(name="max_chars", type="integer", description="Maximum characters to return", required=False, default=10000),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{}]
        )

    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        selector = arguments.get("selector")
        max_chars = arguments.get("max_chars", 10000)

        try:
            page = await browser_manager.get_page()
            
            if selector:
                element = await page.query_selector(selector)
                if not element:
                    return ToolResult(success=False, error=f"Element not found: {selector}")
                text = await element.inner_text()
            else:
                text = await page.inner_text("body")
            
            if len(text) > max_chars:
                text = text[:max_chars] + "... [truncated]"
            
            return ToolResult(success=True, data={
                "text": text,
                "url": page.url,
                "title": await page.title()
            })
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to read page: {str(e)}")


class ClickTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="browser.click",
            description="Click an element on the page",
            category=ToolCategory.BROWSER,
            parameters=[
                ToolParameter(name="selector", type="string", description="CSS selector of element to click", required=True),
                ToolParameter(name="wait_after", type="boolean", description="Wait for navigation after click", required=False, default=True),
                ToolParameter(name="button", type="string", description="Mouse button (left, right, middle)", required=False, default="left"),
                ToolParameter(name="modifiers", type="array", items={"type": "string"}, description="Keyboard modifiers (Shift, Control, Alt, Meta)", required=False),
            ],
            risk_level="MODERATE",
            requires_approval=True,
            idempotent=False,
            examples=[{"selector": "button[type='submit']"}]
        )

    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        selector = arguments["selector"]
        wait_after = arguments.get("wait_after", True)
        button = arguments.get("button", "left")
        modifiers = arguments.get("modifiers", [])

        try:
            page = await browser_manager.get_page()
            element = await page.query_selector(selector)
            if not element:
                return ToolResult(success=False, error=f"Element not found: {selector}")
            
            if wait_after:
                async with page.expect_navigation():
                    await element.click(button=button, modifiers=modifiers)
            else:
                await element.click(button=button, modifiers=modifiers)
            
            return ToolResult(success=True, data={
                "url": page.url,
                "title": await page.title()
            })
        except Exception as e:
            return ToolResult(success=False, error=f"Click failed: {str(e)}")


class FillTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="browser.fill",
            description="Fill an input field on the page",
            category=ToolCategory.BROWSER,
            parameters=[
                ToolParameter(name="selector", type="string", description="CSS selector of input element", required=True),
                ToolParameter(name="value", type="string", description="Value to fill", required=True),
                ToolParameter(name="clear_first", type="boolean", description="Clear field before filling", required=False, default=True),
            ],
            risk_level="MODERATE",
            requires_approval=True,
            idempotent=False,
            examples=[{"selector": "input[name='email']", "value": "user@example.com"}]
        )

    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        selector = arguments["selector"]
        value = arguments["value"]
        clear_first = arguments.get("clear_first", True)

        try:
            page = await browser_manager.get_page()
            element = await page.query_selector(selector)
            if not element:
                return ToolResult(success=False, error=f"Element not found: {selector}")
            
            if clear_first:
                await element.fill("")
            await element.fill(value)
            
            return ToolResult(success=True, data={"selector": selector, "value": value})
        except Exception as e:
            return ToolResult(success=False, error=f"Fill failed: {str(e)}")


class SelectOptionTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="browser.select_option",
            description="Select an option from a dropdown/select element",
            category=ToolCategory.BROWSER,
            parameters=[
                ToolParameter(name="selector", type="string", description="CSS selector of select element", required=True),
                ToolParameter(name="value", type="string", description="Option value to select", required=False),
                ToolParameter(name="label", type="string", description="Option label/text to select", required=False),
                ToolParameter(name="index", type="integer", description="Option index to select", required=False),
            ],
            risk_level="MODERATE",
            requires_approval=True,
            idempotent=False,
            examples=[{"selector": "select[name='country']", "value": "US"}]
        )

    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        selector = arguments["selector"]
        value = arguments.get("value")
        label = arguments.get("label")
        index = arguments.get("index")

        try:
            page = await browser_manager.get_page()
            element = await page.query_selector(selector)
            if not element:
                return ToolResult(success=False, error=f"Element not found: {selector}")
            
            if value:
                await element.select_option(value=value)
            elif label:
                await element.select_option(label=label)
            elif index is not None:
                await element.select_option(index=index)
            else:
                return ToolResult(success=False, error="Must provide value, label, or index")
            
            return ToolResult(success=True, data={"selector": selector, "selected": True})
        except Exception as e:
            return ToolResult(success=False, error=f"Select option failed: {str(e)}")


class PressKeyTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="browser.press_key",
            description="Press a key or key combination on the page",
            category=ToolCategory.BROWSER,
            parameters=[
                ToolParameter(name="key", type="string", description="Key to press (e.g., 'Enter', 'Tab', 'Escape', 'ArrowDown')", required=True),
                ToolParameter(name="modifiers", type="array", items={"type": "string"}, description="Modifiers (Shift, Control, Alt, Meta)", required=False),
            ],
            risk_level="MODERATE",
            requires_approval=True,
            idempotent=False,
            examples=[{"key": "Enter"}, {"key": "Tab", "modifiers": ["Shift"]}]
        )

    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        key = arguments["key"]
        modifiers = arguments.get("modifiers", [])

        try:
            page = await browser_manager.get_page()
            await page.keyboard.press(key, modifiers=modifiers)
            await asyncio.sleep(0.2)
            
            return ToolResult(success=True, data={"key": key, "modifiers": modifiers, "url": page.url})
        except Exception as e:
            return ToolResult(success=False, error=f"Press key failed: {str(e)}")


class WaitForTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="browser.wait_for",
            description="Wait for a condition (element, navigation, network idle, etc.)",
            category=ToolCategory.BROWSER,
            parameters=[
                ToolParameter(name="condition", type="string", description="Condition to wait for", required=True, enum=["element", "navigation", "networkidle", "load", "function"]),
                ToolParameter(name="selector", type="string", description="CSS selector (for element condition)", required=False),
                ToolParameter(name="timeout", type="integer", description="Timeout in milliseconds", required=False, default=30000),
                ToolParameter(name="state", type="string", description="Element state (for element condition)", required=False, default="visible", enum=["visible", "hidden", "attached", "detached"]),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{"condition": "element", "selector": ".loading", "state": "hidden"}]
        )

    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        condition = arguments["condition"]
        selector = arguments.get("selector")
        timeout = arguments.get("timeout", 30000)
        state = arguments.get("state", "visible")

        try:
            page = await browser_manager.get_page()
            
            if condition == "element":
                if not selector:
                    return ToolResult(success=False, error="Selector required for element condition")
                await page.wait_for_selector(selector, state=state, timeout=timeout)
            elif condition == "navigation":
                await page.wait_for_load_state("networkidle", timeout=timeout)
            elif condition == "networkidle":
                await page.wait_for_load_state("networkidle", timeout=timeout)
            elif condition == "load":
                await page.wait_for_load_state("load", timeout=timeout)
            elif condition == "function":
                # Not implemented for security
                return ToolResult(success=False, error="Function condition not supported for security")
            else:
                return ToolResult(success=False, error=f"Unknown condition: {condition}")
            
            return ToolResult(success=True, data={"condition": condition, "waited": True})
        except Exception as e:
            return ToolResult(success=False, error=f"Wait failed: {str(e)}")


class ScreenshotTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="browser.screenshot",
            description="Take a screenshot of the current page",
            category=ToolCategory.BROWSER,
            parameters=[
                ToolParameter(name="path", type="string", description="Path to save screenshot", required=False),
                ToolParameter(name="full_page", type="boolean", description="Capture full page", required=False, default=True),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{"path": "./data/reports/screenshot.png", "full_page": True}]
        )

    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        path = arguments.get("path")
        full_page = arguments.get("full_page", True)

        try:
            page = await browser_manager.get_page()
            
            if path:
                from app.security.path_policy import path_policy
                resolved = path_policy.validate_write(path)
                await page.screenshot(path=resolved, full_page=full_page)
                return ToolResult(success=True, data={"path": resolved})
            else:
                screenshot = await page.screenshot(full_page=full_page)
                return ToolResult(success=True, data={
                    "screenshot_base64": base64.b64encode(screenshot).decode()
                })
        except Exception as e:
            return ToolResult(success=False, error=f"Screenshot failed: {str(e)}")


class ExtractTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="browser.extract",
            description="Extract structured data from page using selectors",
            category=ToolCategory.BROWSER,
            parameters=[
                ToolParameter(name="selectors", type="object", description="Mapping of field names to CSS selectors", required=True),
                ToolParameter(name="attribute", type="string", description="Attribute to extract (default: textContent)", required=False, default="textContent"),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{"selectors": {"title": "h1", "price": ".price"}, "attribute": "textContent"}]
        )

    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        selectors = arguments["selectors"]
        attribute = arguments.get("attribute", "textContent")

        try:
            page = await browser_manager.get_page()
            results = {}
            
            for field, selector in selectors.items():
                elements = await page.query_selector_all(selector)
                if len(elements) == 1:
                    if attribute == "textContent":
                        results[field] = await elements[0].inner_text()
                    else:
                        results[field] = await elements[0].get_attribute(attribute)
                elif len(elements) > 1:
                    values = []
                    for el in elements:
                        if attribute == "textContent":
                            values.append(await el.inner_text())
                        else:
                            values.append(await el.get_attribute(attribute))
                    results[field] = values
                else:
                    results[field] = None
            
            return ToolResult(success=True, data={"extracted": results, "url": page.url})
        except Exception as e:
            return ToolResult(success=False, error=f"Extraction failed: {str(e)}")


class DownloadTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="browser.download",
            description="Trigger and wait for a file download",
            category=ToolCategory.BROWSER,
            parameters=[
                ToolParameter(name="selector", type="string", description="CSS selector of download link/button", required=True),
                ToolParameter(name="save_path", type="string", description="Path to save downloaded file", required=False),
            ],
            risk_level="MODERATE",
            requires_approval=True,
            idempotent=False,
            examples=[{"selector": "a.download-link", "save_path": "./data/workspace/download.pdf"}]
        )

    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        selector = arguments["selector"]
        save_path = arguments.get("save_path")

        try:
            page = await browser_manager.get_page()
            element = await page.query_selector(selector)
            if not element:
                return ToolResult(success=False, error=f"Element not found: {selector}")
            
            # Wait for download to start
            async with page.expect_download() as download_info:
                await element.click()
            
            download = await download_info.value
            
            if save_path:
                from app.security.path_policy import path_policy
                resolved = path_policy.validate_write(save_path)
                await download.save_as(resolved)
                return ToolResult(success=True, data={
                    "path": resolved,
                    "suggested_filename": download.suggested_filename
                })
            else:
                # Save to temp and return base64
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False) as tmp:
                    await download.save_as(tmp.name)
                    with open(tmp.name, "rb") as f:
                        content = f.read()
                    os.unlink(tmp.name)
                
                return ToolResult(success=True, data={
                    "file_base64": base64.b64encode(content).decode(),
                    "suggested_filename": download.suggested_filename,
                    "size": len(content)
                })
        except Exception as e:
            return ToolResult(success=False, error=f"Download failed: {str(e)}")


def register_browser_tools(registry):
    registry.register(NavigateTool())
    registry.register(NewTabTool())
    registry.register(SwitchTabTool())
    registry.register(CloseTabTool())
    registry.register(ListTabsTool())
    registry.register(ReadPageTool())
    registry.register(ClickTool())
    registry.register(FillTool())
    registry.register(SelectOptionTool())
    registry.register(PressKeyTool())
    registry.register(WaitForTool())
    registry.register(ScreenshotTool())
    registry.register(ExtractTool())
    registry.register(DownloadTool())