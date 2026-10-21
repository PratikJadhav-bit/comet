# Comet - Personal AI Agent

A production-minded autonomous AI computer agent for Windows, inspired by Comet-style AI browsers and computer-use agents.

## Features

- **Natural Language Task Execution**: Issue commands like "Open Notepad and type Hello from my AI agent"
- **Real Agent Loop**: Understand → Plan → Select Tools → Execute → Observe → Verify → Continue
- **62 Tools across 8 categories**: File, Browser, Desktop, Terminal, Coding, Memory, Scheduler, Verification
- **Security First**: Risk classification (LOW/MODERATE/HIGH), approval workflows, prompt injection defense
- **Provider-Agnostic**: Supports Gemini, Nemotron, OpenAI, Anthropic
- **Windows-First**: Native UI Automation via pywinauto, Playwright for browser

## Quick Start

### Prerequisites
- Windows 10/11
- Python 3.13+
- Node.js 18+ (for frontend)

### Backend Setup

```powershell
cd comet
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

### Configure Environment

```powershell
copy .env.example .env
# Edit .env with your settings:
# - GEMINI_API_KEY=your_api_key (get from https://aistudio.google.com)
# - MODEL_PROVIDER=gemini
# - ALLOWED_DIRECTORIES=./data/workspace
```

### Run Backend

```powershell
.venv\Scripts\Activate.ps1
python -m app.main
```

API available at `http://127.0.0.1:8000`

### Run Frontend (optional)

```powershell
cd frontend
npm install
npm run dev
```

Frontend available at `http://127.0.0.1:3000`

## API Usage

```bash
# Health check
curl http://127.0.0.1:8000/api/health

# List tools
curl http://127.0.0.1:8000/api/tools

# Create task
curl -X POST http://127.0.0.1:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title": "Open Notepad", "description": "Open Notepad and type Hello"}'

# Plan task
curl -X POST http://127.0.0.1:8000/api/tasks/1/plan \
  -H "Content-Type: application/json" \
  -d '{"task_id": 1, "instruction": "Open Notepad and type Hello from my AI agent"}'

# Execute task
curl -X POST http://127.0.0.1:8000/api/tasks/1/execute

# Check status
curl http://127.0.0.1:8000/api/tasks/1/status

# List pending approvals
curl http://127.0.0.1:8000/api/approvals/pending

# Respond to approval
curl -X POST http://127.0.0.1:8000/api/approvals/respond \
  -H "Content-Type: application/json" \
  -d '{"approval_id": "abc123", "approved": true}'
```

## Tool Categories

### File (10 tools)
- `list_files`, `read_file`, `write_file`, `copy_file`, `move_file`, `delete_file`
- `create_directory`, `get_file_info`, `verify.file_exists`, `verify.file_content`

### Browser (15 tools)
- `browser.navigate`, `browser.new_tab`, `browser.switch_tab`, `browser.close_tab`
- `browser.list_tabs`, `browser.read_page`, `browser.click`, `browser.fill`
- `browser.select_option`, `browser.press_key`, `browser.wait_for`
- `browser.screenshot`, `browser.extract`, `browser.download`, `verify.url_accessible`

### Desktop (13 tools)
- `desktop.list_windows`, `desktop.get_window_info`, `desktop.focus_window`
- `desktop.inspect_window`, `desktop.find_element`, `desktop.click_element`
- `desktop.type_text`, `desktop.press_key`, `desktop.take_screenshot`
- `desktop.launch_application`, `desktop.close_application`
- `verify.window_state`, `verify.element_exists`

### Terminal/Coding (11 tools)
- `terminal.execute`, `terminal.run_python`, `terminal.run_tests`, `terminal.lint`, `terminal.git`
- `vscode.open_folder`, `vscode.open_file`, `vscode.get_workspace`
- `vscode.install_extension`, `vscode.list_extensions`, `vscode.run_task`

### Memory (6 tools)
- `memory.store`, `memory.get`, `memory.search`, `memory.delete`, `memory.stats`, `memory.clear_expired`

### Scheduler (6 tools)
- `scheduler.create`, `scheduler.list`, `scheduler.get`, `scheduler.delete`, `scheduler.enable`, `scheduler.run_now`

### Verification (7 tools)
- `verify.file_exists`, `verify.file_content`, `verify.window_state`, `verify.element_exists`
- `verify.process_running`, `verify.url_accessible`, `verify.file_content`

## Security Model

### Risk Levels
- **LOW**: Read-only operations (auto-execute)
- **MODERATE**: Write operations (require approval)
- **HIGH**: Destructive/consequential (always require explicit approval)

### Approval Workflow
1. Agent plans action requiring approval
2. Approval request created with full details
3. User reviews and approves/rejects via API or UI
4. Agent executes only after approval

### Prompt Injection Defense
- External content treated as data, never as instructions
- Content trust boundaries: System > User > Tool Output > Web > External
- Automatic detection and blocking of injection patterns
- Secret redaction in logs

## Architecture

```
comet/
├── app/
│   ├── api/routes.py          # FastAPI REST endpoints
│   ├── agent/orchestrator.py  # Agent reasoning loop
│   ├── models/                # Model providers (Gemini, Nemotron)
│   ├── tools/                 # Tool implementations
│   │   ├── files.py           # File operations
│   │   ├── browser.py         # Playwright browser
│   │   ├── desktop.py         # Windows UI Automation
│   │   ├── terminal.py        # Controlled terminal
│   │   ├── vscode.py          # VS Code integration
│   │   ├── memory.py          # Memory system
│   │   ├── scheduler.py       # Windows Task Scheduler
│   │   └── verification.py    # Verification tools
│   ├── security/              # Security layer
│   │   ├── permissions.py     # Path policies, risk classification
│   │   ├── approvals.py       # Approval center
│   │   └── prompt_injection.py # Injection defense
│   └── storage/               # SQLite persistence
├── frontend/                  # React/TypeScript UI
├── tests/                     # Unit tests
└── scripts/                   # Utility scripts
```

## Configuration

Key settings in `.env`:

```env
MODEL_PROVIDER=gemini
GEMINI_API_KEY=your_key
GEMINI_MODEL=gemini-1.5-flash
ALLOWED_DIRECTORIES=./data/workspace
MAX_TOOL_CALLS_PER_TASK=100
APPROVAL_TIMEOUT_SECONDS=300
```

## Running Tests

```powershell
.venv\Scripts\Activate.ps1
python scripts/run_tests.py
```

## Security Notes

- Never disables Windows Smart App Control, Defender, Firewall, or UAC
- No arbitrary code execution - all actions through validated tool registry
- Path traversal protection via allowlist
- API keys never logged or exposed to model
- Windows Task Scheduler for reliable background tasks

## Limitations

- Requires valid Gemini API key for AI reasoning
- VS Code integration requires VS Code installed
- Desktop automation works best with standard Windows apps
- Browser automation requires Playwright Chromium
- Scheduler requires Windows Task Scheduler service running

## License

MIT License