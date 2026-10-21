import pytest
import asyncio
import tempfile
import os
from pathlib import Path

from app.security.path_policy import PathPolicy
from app.security.permissions import PermissionPolicy, ActionType, RiskLevel, get_default_policy
from app.security.risk import assess_risk, RiskFactor
from app.tools.registry import tool_registry, ToolSchema, ToolParameter, ToolCategory, BaseTool
from app.tools.files import ListFilesTool, ReadFileTool, WriteFileTool
from app.storage.models import TaskStatus, RiskLevel as ModelRiskLevel


class TestPathPolicy:
    def test_resolve_relative_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            allowed = os.path.join(tmpdir, "test")
            os.makedirs(allowed, exist_ok=True)
            policy = PathPolicy(allowed_dirs=[allowed])
            resolved = policy.resolve_path("subdir/file.txt", allowed)
            expected = os.path.normpath(os.path.join(allowed, "subdir", "file.txt"))
            assert resolved == expected

    def test_resolve_absolute_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            allowed = os.path.join(tmpdir, "test")
            os.makedirs(allowed, exist_ok=True)
            policy = PathPolicy(allowed_dirs=[allowed])
            resolved = policy.resolve_path(os.path.join(allowed, "file.txt"))
            assert resolved == os.path.join(allowed, "file.txt")

    def test_is_allowed_within_allowed_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            allowed = os.path.join(tmpdir, "test")
            os.makedirs(allowed, exist_ok=True)
            policy = PathPolicy(allowed_dirs=[allowed])
            assert policy.is_allowed(os.path.join(allowed, "file.txt")) == True
            assert policy.is_allowed(os.path.join(allowed, "subdir", "file.txt")) == True

    def test_is_denied_outside_allowed_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            allowed = os.path.join(tmpdir, "test")
            other = os.path.join(tmpdir, "other")
            os.makedirs(allowed, exist_ok=True)
            os.makedirs(other, exist_ok=True)
            policy = PathPolicy(allowed_dirs=[allowed])
            assert policy.is_allowed(os.path.join(other, "file.txt")) == False

    def test_blocked_directories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            allowed = os.path.join(tmpdir, "test")
            secret = os.path.join(allowed, "secret")
            os.makedirs(allowed, exist_ok=True)
            os.makedirs(secret, exist_ok=True)
            policy = PathPolicy(allowed_dirs=[allowed], blocked_dirs=[secret])
            assert policy.is_allowed(os.path.join(secret, "file.txt")) == False


class TestPermissionPolicy:
    def test_default_policy_allows_workspace(self):
        policy = get_default_policy()
        assert policy.is_directory_allowed("./data/workspace") == True

    def test_default_policy_blocks_system_dirs(self):
        policy = get_default_policy()
        assert policy.is_directory_allowed("C:\\Windows\\System32") == False
        assert policy.is_directory_allowed("C:\\Program Files") == False

    def test_risk_classification(self):
        policy = get_default_policy()
        assert policy.get_risk_level(ActionType.READ_FILE) == RiskLevel.LOW
        assert policy.get_risk_level(ActionType.WRITE_FILE) == RiskLevel.MODERATE
        assert policy.get_risk_level(ActionType.DELETE_FILE) == RiskLevel.HIGH
        assert policy.get_risk_level(ActionType.FINANCIAL_ACTION) == RiskLevel.HIGH

    def test_requires_approval(self):
        policy = get_default_policy()
        assert policy.requires_approval(ActionType.READ_FILE) == False
        assert policy.requires_approval(ActionType.WRITE_FILE) == True
        assert policy.requires_approval(ActionType.DELETE_FILE) == True


class TestRiskAssessment:
    def test_read_file_low_risk(self):
        assessment = assess_risk(ActionType.READ_FILE)
        assert assessment.level == RiskLevel.LOW
        assert assessment.requires_approval == False
        assert assessment.reversible == True

    def test_write_file_moderate_risk(self):
        assessment = assess_risk(ActionType.WRITE_FILE)
        assert assessment.level == RiskLevel.MODERATE
        assert assessment.requires_approval == True
        assert RiskFactor.USER_DATA_MODIFICATION in assessment.factors

    def test_delete_file_high_risk(self):
        assessment = assess_risk(ActionType.DELETE_FILE)
        assert assessment.level == RiskLevel.HIGH
        assert assessment.requires_approval == True
        assert assessment.reversible == False
        assert RiskFactor.DESTRUCTIVE in assessment.factors
        assert RiskFactor.IRREVERSIBLE in assessment.factors

    def test_financial_action_high_risk(self):
        assessment = assess_risk(ActionType.FINANCIAL_ACTION)
        assert assessment.level == RiskLevel.HIGH
        assert RiskFactor.FINANCIAL_IMPACT in assessment.factors
        assert RiskFactor.AUTHENTICATION_REQUIRED in assessment.factors


class TestToolRegistry:
    def setup_method(self):
        self.original_tools = dict(tool_registry._tools)
        self.original_categories = dict(tool_registry._categories)
        tool_registry._tools.clear()
        tool_registry._categories.clear()

    def teardown_method(self):
        tool_registry._tools = self.original_tools
        tool_registry._categories = self.original_categories

    def test_register_tool(self):
        class TestTool(BaseTool):
            def _define_schema(self):
                return ToolSchema(
                    name="test_tool",
                    description="A test tool",
                    category=ToolCategory.FILE,
                    parameters=[ToolParameter(name="param", type="string", description="Test param")]
                )
            async def execute(self, arguments, context=None):
                return {"success": True}
        
        tool_registry.register(TestTool())
        assert "test_tool" in tool_registry._tools
        assert tool_registry.get("test_tool") is not None

    def test_list_tools(self):
        class TestTool1(BaseTool):
            def _define_schema(self):
                return ToolSchema(name="test1", description="Test 1", category=ToolCategory.FILE)
            async def execute(self, arguments, context=None):
                pass
        
        class TestTool2(BaseTool):
            def _define_schema(self):
                return ToolSchema(name="test2", description="Test 2", category=ToolCategory.BROWSER)
            async def execute(self, arguments, context=None):
                pass
        
        tool_registry.register(TestTool1())
        tool_registry.register(TestTool2())
        
        all_tools = tool_registry.list_tools()
        assert len(all_tools) == 2
        
        file_tools = tool_registry.list_tools(ToolCategory.FILE)
        assert len(file_tools) == 1
        assert file_tools[0].name == "test1"


class TestFileTools:
    @pytest.fixture
    def temp_workspace(self):
        # Use the actual allowed workspace directory
        workspace = Path("./data/workspace")
        workspace.mkdir(parents=True, exist_ok=True)
        test_dir = workspace / "test_temp"
        if test_dir.exists():
            import shutil
            shutil.rmtree(test_dir)
        test_dir.mkdir()
        (test_dir / "test.txt").write_text("Hello World")
        (test_dir / "subdir").mkdir()
        (test_dir / "subdir" / "nested.txt").write_text("Nested")
        yield str(test_dir)
        # Cleanup
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_list_files(self, temp_workspace):
        tool = ListFilesTool()
        result = await tool.execute({"path": temp_workspace, "recursive": True})
        assert result.success == True
        assert len(result.data["files"]) >= 3

    @pytest.mark.asyncio
    async def test_read_file(self, temp_workspace):
        tool = ReadFileTool()
        file_path = os.path.join(temp_workspace, "test.txt")
        result = await tool.execute({"path": file_path})
        assert result.success == True
        assert result.data["content"] == "Hello World"

    @pytest.mark.asyncio
    async def test_write_file(self, temp_workspace):
        tool = WriteFileTool()
        file_path = os.path.join(temp_workspace, "new.txt")
        result = await tool.execute({"path": file_path, "content": "New content"})
        assert result.success == True
        assert os.path.exists(file_path)
        with open(file_path) as f:
            assert f.read() == "New content"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])