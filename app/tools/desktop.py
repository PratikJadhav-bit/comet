"""Windows Desktop Automation Tools using pywinauto/UIA"""
import asyncio
import os
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from app.tools.registry import BaseTool, ToolSchema, ToolParameter, ToolResult, ToolCategory
from app.security.risk import assess_risk
from app.security.permissions import ActionType


@dataclass
class WindowInfo:
    handle: int
    title: str
    class_name: str
    process_id: int
    rect: Dict[str, int]
    is_visible: bool
    is_enabled: bool


class DesktopManager:
    """Manages desktop automation state"""
    _instance = None
    _app_cache: Dict[str, Any] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_windows(self) -> List[WindowInfo]:
        """Get list of all visible windows"""
        try:
            import pywinauto
            from pywinauto import Desktop
            
            windows = []
            desktop = Desktop(backend="uia")
            
            for win in desktop.windows():
                try:
                    if win.is_visible():
                        rect = win.rectangle()
                        windows.append(WindowInfo(
                            handle=win.handle,
                            title=win.window_text() or "",
                            class_name=win.class_name() or "",
                            process_id=win.process_id(),
                            rect={"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom},
                            is_visible=win.is_visible(),
                            is_enabled=win.is_enabled()
                        ))
                except Exception:
                    continue
            
            return windows
        except Exception as e:
            return []
    
    def find_window(self, title: str = None, class_name: str = None, process_id: int = None) -> Optional[Any]:
        """Find a window by various criteria"""
        try:
            import pywinauto
            from pywinauto import Desktop
            
            desktop = Desktop(backend="uia")
            
            if title:
                windows = desktop.windows(title=title)
            elif class_name:
                windows = desktop.windows(class_name=class_name)
            elif process_id:
                windows = [w for w in desktop.windows() if w.process_id() == process_id]
            else:
                return None
            
            for win in windows:
                if win.is_visible():
                    return win
            return None
        except Exception:
            return None
    
    def launch_application(self, path: str, args: str = "") -> Optional[Any]:
        """Launch an application and return the app object"""
        try:
            import pywinauto
            from pywinauto import Application
            
            if args:
                app = Application(backend="uia").start(f'"{path}" {args}')
            else:
                app = Application(backend="uia").start(path)
            
            # Wait for app to start
            time.sleep(1)
            return app
        except Exception as e:
            return None
    
    def close_application(self, process_id: int) -> bool:
        """Close an application by process ID"""
        try:
            import psutil
            proc = psutil.Process(process_id)
            proc.terminate()
            proc.wait(timeout=5)
            return True
        except Exception:
            return False


desktop_manager = DesktopManager()


class ListWindowsTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="desktop.list_windows",
            description="List all visible windows on the desktop",
            category=ToolCategory.DESKTOP,
            parameters=[
                ToolParameter(name="filter", type="string", description="Filter windows by title (substring)", required=False),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{"filter": "Notepad"}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        filter_text = arguments.get("filter", "").lower()
        
        windows = desktop_manager.get_windows()
        
        if filter_text:
            windows = [w for w in windows if filter_text in w.title.lower()]
        
        data = {
            "windows": [
                {
                    "handle": w.handle,
                    "title": w.title,
                    "class_name": w.class_name,
                    "process_id": w.process_id,
                    "rect": w.rect,
                    "is_visible": w.is_visible,
                    "is_enabled": w.is_enabled
                }
                for w in windows
            ],
            "count": len(windows)
        }
        
        return ToolResult(success=True, data=data)


class GetWindowInfoTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="desktop.get_window_info",
            description="Get detailed information about a specific window",
            category=ToolCategory.DESKTOP,
            parameters=[
                ToolParameter(name="handle", type="integer", description="Window handle (HWND)", required=True),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{"handle": 123456}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        handle = arguments["handle"]
        
        try:
            import pywinauto
            from pywinauto import Desktop
            
            desktop = Desktop(backend="uia")
            win = desktop.window(handle=handle)
            
            if not win.exists():
                return ToolResult(success=False, error=f"Window with handle {handle} not found")
            
            rect = win.rectangle()
            data = {
                "handle": handle,
                "title": win.window_text() or "",
                "class_name": win.class_name() or "",
                "process_id": win.process_id(),
                "rect": {"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom},
                "is_visible": win.is_visible(),
                "is_enabled": win.is_enabled(),
                "is_maximized": win.is_maximized(),
                "is_minimized": win.is_minimized(),
            }
            
            return ToolResult(success=True, data=data)
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to get window info: {str(e)}")


class FocusWindowTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="desktop.focus_window",
            description="Bring a window to the foreground and focus it",
            category=ToolCategory.DESKTOP,
            parameters=[
                ToolParameter(name="handle", type="integer", description="Window handle (HWND)", required=True),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{"handle": 123456}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        handle = arguments["handle"]
        
        try:
            import pywinauto
            from pywinauto import Desktop
            
            desktop = Desktop(backend="uia")
            win = desktop.window(handle=handle)
            
            if not win.exists():
                return ToolResult(success=False, error=f"Window with handle {handle} not found")
            
            win.set_focus()
            await asyncio.sleep(0.2)
            
            return ToolResult(success=True, data={"handle": handle, "focused": True})
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to focus window: {str(e)}")


class InspectWindowTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="desktop.inspect_window",
            description="Inspect the UI element tree of a window",
            category=ToolCategory.DESKTOP,
            parameters=[
                ToolParameter(name="handle", type="integer", description="Window handle (HWND)", required=True),
                ToolParameter(name="max_depth", type="integer", description="Maximum depth to inspect", required=False, default=3),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{"handle": 123456, "max_depth": 3}]
        )
    
    def _element_to_dict(self, element, depth: int = 0, max_depth: int = 3) -> Optional[Dict]:
        if depth > max_depth:
            return None
        
        try:
            result = {
                "control_type": element.element_info.control_type,
                "name": element.window_text() or "",
                "class_name": element.class_name() or "",
                "automation_id": element.automation_id() or "",
                "rect": None,
                "is_visible": element.is_visible(),
                "is_enabled": element.is_enabled(),
                "children": []
            }
            
            try:
                rect = element.rectangle()
                result["rect"] = {"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom}
            except Exception:
                pass
            
            try:
                children = element.children()
                for child in children:
                    child_dict = self._element_to_dict(child, depth + 1, max_depth)
                    if child_dict:
                        result["children"].append(child_dict)
            except Exception:
                pass
            
            return result
        except Exception:
            return None
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        handle = arguments["handle"]
        max_depth = arguments.get("max_depth", 3)
        
        try:
            import pywinauto
            from pywinauto import Desktop
            
            desktop = Desktop(backend="uia")
            win = desktop.window(handle=handle)
            
            if not win.exists():
                return ToolResult(success=False, error=f"Window with handle {handle} not found")
            
            tree = self._element_to_dict(win, 0, max_depth)
            
            return ToolResult(success=True, data={"handle": handle, "ui_tree": tree})
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to inspect window: {str(e)}")


class FindElementTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="desktop.find_element",
            description="Find a UI element within a window by various criteria",
            category=ToolCategory.DESKTOP,
            parameters=[
                ToolParameter(name="handle", type="integer", description="Window handle (HWND)", required=True),
                ToolParameter(name="control_type", type="string", description="Control type (Button, Edit, Text, ComboBox, etc.)", required=False),
                ToolParameter(name="name", type="string", description="Element name/text", required=False),
                ToolParameter(name="automation_id", type="string", description="Automation ID", required=False),
                ToolParameter(name="class_name", type="string", description="Class name", required=False),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{"handle": 123456, "control_type": "Button", "name": "OK"}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        handle = arguments["handle"]
        control_type = arguments.get("control_type")
        name = arguments.get("name")
        automation_id = arguments.get("automation_id")
        class_name = arguments.get("class_name")
        
        try:
            import pywinauto
            from pywinauto import Desktop
            
            desktop = Desktop(backend="uia")
            win = desktop.window(handle=handle)
            
            if not win.exists():
                return ToolResult(success=False, error=f"Window with handle {handle} not found")
            
            # Build search criteria
            criteria = {}
            if control_type:
                criteria["control_type"] = control_type
            if name:
                criteria["title"] = name
            if automation_id:
                criteria["auto_id"] = automation_id
            if class_name:
                criteria["class_name"] = class_name
            
            if not criteria:
                return ToolResult(success=False, error="At least one search criterion required")
            
            elements = win.descendants(**criteria)
            
            results = []
            for elem in elements[:10]:  # Limit to 10 results
                try:
                    rect = elem.rectangle()
                    results.append({
                        "handle": elem.handle,
                        "control_type": elem.element_info.control_type,
                        "name": elem.window_text() or "",
                        "class_name": elem.class_name() or "",
                        "automation_id": elem.automation_id() or "",
                        "rect": {"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom},
                        "is_visible": elem.is_visible(),
                        "is_enabled": elem.is_enabled(),
                    })
                except Exception:
                    continue
            
            return ToolResult(success=True, data={"elements": results, "count": len(results)})
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to find element: {str(e)}")


class ClickElementTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="desktop.click_element",
            description="Click a UI element in a window",
            category=ToolCategory.DESKTOP,
            parameters=[
                ToolParameter(name="handle", type="integer", description="Window handle (HWND)", required=True),
                ToolParameter(name="control_type", type="string", description="Control type (Button, Edit, Text, etc.)", required=False),
                ToolParameter(name="name", type="string", description="Element name/text", required=False),
                ToolParameter(name="automation_id", type="string", description="Automation ID", required=False),
                ToolParameter(name="x_offset", type="integer", description="X offset from element center", required=False, default=0),
                ToolParameter(name="y_offset", type="integer", description="Y offset from element center", required=False, default=0),
            ],
            risk_level="MODERATE",
            requires_approval=True,
            idempotent=False,
            examples=[{"handle": 123456, "control_type": "Button", "name": "OK"}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        handle = arguments["handle"]
        control_type = arguments.get("control_type")
        name = arguments.get("name")
        automation_id = arguments.get("automation_id")
        x_offset = arguments.get("x_offset", 0)
        y_offset = arguments.get("y_offset", 0)
        
        try:
            import pywinauto
            from pywinauto import Desktop
            
            desktop = Desktop(backend="uia")
            win = desktop.window(handle=handle)
            
            if not win.exists():
                return ToolResult(success=False, error=f"Window with handle {handle} not found")
            
            criteria = {}
            if control_type:
                criteria["control_type"] = control_type
            if name:
                criteria["title"] = name
            if automation_id:
                criteria["auto_id"] = automation_id
            
            if not criteria:
                return ToolResult(success=False, error="At least one search criterion required")
            
            elements = win.descendants(**criteria)
            if not elements:
                return ToolResult(success=False, error="Element not found")
            
            elem = elements[0]
            if not elem.is_visible() or not elem.is_enabled():
                return ToolResult(success=False, error="Element not visible or enabled")
            
            # Click with offset
            rect = elem.rectangle()
            click_x = (rect.left + rect.right) // 2 + x_offset
            click_y = (rect.top + rect.bottom) // 2 + y_offset
            
            elem.click_input(coords=(click_x, click_y))
            await asyncio.sleep(0.2)
            
            return ToolResult(success=True, data={"clicked": True, "element": name or control_type})
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to click element: {str(e)}")


class TypeTextTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="desktop.type_text",
            description="Type text into an edit control",
            category=ToolCategory.DESKTOP,
            parameters=[
                ToolParameter(name="handle", type="integer", description="Window handle (HWND)", required=True),
                ToolParameter(name="control_type", type="string", description="Control type (Edit, TextBox, etc.)", required=False, default="Edit"),
                ToolParameter(name="name", type="string", description="Element name", required=False),
                ToolParameter(name="automation_id", type="string", description="Automation ID", required=False),
                ToolParameter(name="text", type="string", description="Text to type", required=True),
                ToolParameter(name="clear_first", type="boolean", description="Clear field before typing", required=False, default=True),
            ],
            risk_level="MODERATE",
            requires_approval=True,
            idempotent=False,
            examples=[{"handle": 123456, "text": "Hello World", "clear_first": True}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        handle = arguments["handle"]
        control_type = arguments.get("control_type", "Edit")
        name = arguments.get("name")
        automation_id = arguments.get("automation_id")
        text = arguments["text"]
        clear_first = arguments.get("clear_first", True)
        
        try:
            import pywinauto
            from pywinauto import Desktop
            
            desktop = Desktop(backend="uia")
            win = desktop.window(handle=handle)
            
            if not win.exists():
                return ToolResult(success=False, error=f"Window with handle {handle} not found")
            
            criteria = {"control_type": control_type}
            if name:
                criteria["title"] = name
            if automation_id:
                criteria["auto_id"] = automation_id
            
            elements = win.descendants(**criteria)
            if not elements:
                return ToolResult(success=False, error="Element not found")
            
            elem = elements[0]
            if not elem.is_visible() or not elem.is_enabled():
                return ToolResult(success=False, error="Element not visible or enabled")
            
            # Focus the element
            elem.set_focus()
            await asyncio.sleep(0.1)
            
            if clear_first:
                # Select all and delete
                elem.type_keys("^a{DELETE}")
                await asyncio.sleep(0.1)
            
            # Type the text
            elem.type_keys(text, with_spaces=True)
            await asyncio.sleep(0.2)
            
            return ToolResult(success=True, data={"typed": True, "text_length": len(text)})
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to type text: {str(e)}")


class PressKeyTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="desktop.press_key",
            description="Press a key or key combination",
            category=ToolCategory.DESKTOP,
            parameters=[
                ToolParameter(name="handle", type="integer", description="Window handle (HWND)", required=True),
                ToolParameter(name="keys", type="string", description="Keys to press (e.g., '^s' for Ctrl+S, '{ENTER}', '{TAB}')", required=True),
            ],
            risk_level="MODERATE",
            requires_approval=True,
            idempotent=False,
            examples=[{"handle": 123456, "keys": "^s"}, {"handle": 123456, "keys": "{ENTER}"}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        handle = arguments["handle"]
        keys = arguments["keys"]
        
        try:
            import pywinauto
            from pywinauto import Desktop
            
            desktop = Desktop(backend="uia")
            win = desktop.window(handle=handle)
            
            if not win.exists():
                return ToolResult(success=False, error=f"Window with handle {handle} not found")
            
            win.set_focus()
            await asyncio.sleep(0.1)
            win.type_keys(keys)
            await asyncio.sleep(0.2)
            
            return ToolResult(success=True, data={"keys_pressed": keys})
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to press key: {str(e)}")


class TakeScreenshotTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="desktop.take_screenshot",
            description="Take a screenshot of a window or the entire screen",
            category=ToolCategory.DESKTOP,
            parameters=[
                ToolParameter(name="handle", type="integer", description="Window handle (HWND), omit for full screen", required=False),
                ToolParameter(name="path", type="string", description="Path to save screenshot", required=False),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{"handle": 123456, "path": "./data/workspace/screenshot.png"}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        handle = arguments.get("handle")
        path = arguments.get("path")
        
        try:
            import pywinauto
            from pywinauto import Desktop
            from PIL import ImageGrab
            import io
            import base64
            
            if handle:
                desktop = Desktop(backend="uia")
                win = desktop.window(handle=handle)
                
                if not win.exists():
                    return ToolResult(success=False, error=f"Window with handle {handle} not found")
                
                rect = win.rectangle()
                img = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom))
            else:
                img = ImageGrab.grab()
            
            if path:
                from app.security.path_policy import path_policy
                resolved = path_policy.validate_write(path)
                img.save(resolved)
                return ToolResult(success=True, data={"path": resolved, "size": img.size})
            else:
                # Return base64
                buffer = io.BytesIO()
                img.save(buffer, format="PNG")
                img_base64 = base64.b64encode(buffer.getvalue()).decode()
                return ToolResult(success=True, data={"screenshot_base64": img_base64, "size": img.size})
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to take screenshot: {str(e)}")


class LaunchApplicationTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="desktop.launch_application",
            description="Launch a Windows application",
            category=ToolCategory.DESKTOP,
            parameters=[
                ToolParameter(name="path", type="string", description="Path to executable", required=True),
                ToolParameter(name="args", type="string", description="Command line arguments", required=False, default=""),
                ToolParameter(name="working_dir", type="string", description="Working directory", required=False),
            ],
            risk_level="MODERATE",
            requires_approval=True,
            idempotent=False,
            examples=[{"path": "C:\\Windows\\System32\\notepad.exe"}, {"path": "calc.exe"}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        path = arguments["path"]
        args = arguments.get("args", "")
        working_dir = arguments.get("working_dir")
        
        try:
            import pywinauto
            from pywinauto import Application
            import os
            
            # Validate path is allowed
            if os.path.isabs(path):
                from app.security.path_policy import path_policy
                # Allow common system paths for standard apps
                allowed_system_paths = [
                    os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32"),
                    os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "SysWOW64"),
                ]
                # For system apps, we allow them if they're in standard locations
            
            if args:
                cmd = f'"{path}" {args}'
            else:
                cmd = path
            
            app = Application(backend="uia").start(cmd, work_dir=working_dir)
            
            # Wait for app to start
            await asyncio.sleep(1.5)
            
            # Get the main window
            try:
                windows = app.windows()
                main_window = windows[0] if windows else None
                handle = main_window.handle if main_window else None
            except Exception:
                handle = None
            
            return ToolResult(success=True, data={
                "launched": True,
                "path": path,
                "process_id": app.process,
                "main_window_handle": handle
            })
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to launch application: {str(e)}")


class CloseApplicationTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="desktop.close_application",
            description="Close a Windows application by process ID or window handle",
            category=ToolCategory.DESKTOP,
            parameters=[
                ToolParameter(name="process_id", type="integer", description="Process ID to terminate", required=False),
                ToolParameter(name="handle", type="integer", description="Window handle to close", required=False),
            ],
            risk_level="HIGH",
            requires_approval=True,
            idempotent=False,
            examples=[{"process_id": 1234}, {"handle": 5678}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        process_id = arguments.get("process_id")
        handle = arguments.get("handle")
        
        if not process_id and not handle:
            return ToolResult(success=False, error="Either process_id or handle required")
        
        try:
            import pywinauto
            from pywinauto import Desktop
            import psutil
            
            if handle:
                desktop = Desktop(backend="uia")
                win = desktop.window(handle=handle)
                if win.exists():
                    process_id = win.process_id()
            
            if process_id:
                proc = psutil.Process(process_id)
                proc.terminate()
                await asyncio.sleep(0.5)
                
                # Check if still running
                if proc.is_running():
                    proc.kill()
                    await asyncio.sleep(0.5)
                
                return ToolResult(success=True, data={"closed": True, "process_id": process_id})
            else:
                return ToolResult(success=False, error="Could not determine process ID")
        except psutil.NoSuchProcess:
            return ToolResult(success=True, data={"closed": True, "process_id": process_id, "note": "Process already terminated"})
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to close application: {str(e)}")


def register_desktop_tools(registry):
    registry.register(ListWindowsTool())
    registry.register(GetWindowInfoTool())
    registry.register(FocusWindowTool())
    registry.register(InspectWindowTool())
    registry.register(FindElementTool())
    registry.register(ClickElementTool())
    registry.register(TypeTextTool())
    registry.register(PressKeyTool())
    registry.register(TakeScreenshotTool())
    registry.register(LaunchApplicationTool())
    registry.register(CloseApplicationTool())