# agent-loop

Open-source framework for building autonomous AI agents powered by [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code). Connect your agent to Telegram (more messengers coming soon) and let it work for you 24/7.

## What is this?

**agent-loop** gives you an always-on AI agent that:

- **Lives in your messenger** — chat with it on Telegram like a colleague
- **Works autonomously** — heartbeat loop picks and executes tasks every 30 minutes
- **Remembers everything** — tiered file-based memory (core/standard/ephemeral)
- **Streams progress** — see what Claude is doing in real-time (tool use, file reads, etc.)
- **Runs on your VPS** — self-hosted, no SaaS, your data stays yours

Built on Claude Code CLI, which means your agent has full capabilities: file system access, code execution, web search, and all Claude Code tools.

## Quick Start

### Prerequisites

- Python 3.11+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))

### Install

```bash
git clone https://github.com/mateuszrybak/agent-loop.git
cd agent-loop
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Setup

Interactive wizard:

```bash
agent-loop setup
```

This creates `.env` (secrets), `config.yaml` (settings), and `data/` directory.

Or manually:

```bash
cp .env.example .env       # Edit with your tokens
cp config.example.yaml config.yaml  # Customize
agent-loop init             # Create data directories
```

### Run

```bash
agent-loop start
```

That's it. Send a message to your Telegram bot.

### Docker

```bash
cp .env.example .env && vim .env
cp config.example.yaml config.yaml
docker-compose up -d
```

## Architecture

```
┌──────────────────────────────────────────┐
│            Messenger Bridge              │
│         (Telegram / Slack / ...)         │
├──────────────────────────────────────────┤
│           Agent Controller               │
│    (session mgmt, concurrency, routing)  │
├──────────────────────────────────────────┤
│          Claude Code CLI Runner          │
│     (streaming, tool use, progress)      │
├───────────┬──────────┬───────────────────┤
│  Memory   │  Loops   │     Tools         │
│  System   │ (heart-  │  (notify, run-    │
│  (tiered) │  beat,   │   task, check)    │
│           │  digest) │                   │
└───────────┴──────────┴───────────────────┘
```

### Core Modules

| Module | Description |
|--------|-------------|
| `core/claude.py` | Async Claude CLI runner with stream-json parsing |
| `core/session.py` | Session management (--resume for continuity) |
| `core/controller.py` | Concurrency control (main session lock + side sessions) |
| `bridges/telegram/` | Full Telegram bridge (streaming, files, voice, commands) |
| `memory/` | File-based memory with YAML frontmatter and tier system |
| `loops/heartbeat.py` | Autonomous heartbeat — picks highest-value action |
| `loops/digest.py` | Daily journal + memory insight extraction |
| `loops/maintain.py` | Memory maintenance (cleanup, verification, enrichment) |

### Key Design Decisions

1. **Claude Code CLI** (not API) — gives full agent capabilities for free with a Claude subscription
2. **File-based memory** — simple, inspectable, git-friendly, zero external deps
3. **Single process** — bot + scheduler in one process (optional: cron mode)
4. **Bridge as plugin** — add new messengers without touching core code

## Configuration

### .env (secrets)

```bash
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_USER_ID=your_id
# TELEGRAM_GROUP_IDS=group1,group2
# CLAUDE_PATH=claude
```

### config.yaml (everything else)

See [`config.example.yaml`](config.example.yaml) for all options.

Key settings:

```yaml
agent:
  name: "Atlas"
  language: "en"
  model: "sonnet"

loops:
  heartbeat:
    enabled: true
    interval_minutes: 30
    active_hours_start: 8
    active_hours_end: 22
```

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/new` | Reset session (start fresh) |
| `/model` | Show/change model (opus, sonnet, haiku) |
| `/memory` | Show memory index |
| `/todo` | Show task list |
| `/ping` | Bot status |

## Memory System

Memories are markdown files with YAML frontmatter:

```markdown
---
name: User profile
description: User role and preferences
type: user
tags: [profile, preferences]
---

User is a data engineer focused on observability.
Prefers concise responses.
```

Types: `user`, `project`, `feedback`, `reference`, `journal`

Tiers:
- **core** — never deleted (critical knowledge)
- **standard** — archived after 30 days inactive
- **ephemeral** — auto-archived after 14 days (journals, temp notes)

## Autonomous Loops

### Heartbeat (default: every 30 min)

Picks the single highest-value action and executes it:
- Reads todo list and session context
- Checks system health
- Prioritizes by urgency (red > yellow > green)
- Reports what it did via Telegram

### Daily Digest (default: 23:00)

Creates a daily journal with:
- What was accomplished
- Key decisions made
- Items still in progress

### Memory Maintenance (default: every 6h)

One maintenance action per cycle:
- Verify file paths in memories still exist
- Find duplicate/stale memories
- Enrich descriptions and tags
- Review tier assignments

## CLI Commands

```bash
agent-loop start          # Start bot + loops
agent-loop start --no-loops  # Bot only, no autonomous loops
agent-loop setup          # Interactive setup wizard
agent-loop init           # Initialize data directory
agent-loop heartbeat      # Run one heartbeat cycle
agent-loop digest         # Run daily digest
agent-loop maintain       # Run memory maintenance
```

## Shell Tools

Install to PATH for use in scripts and by Claude:

```bash
tools/agent-notify "Hello from agent"     # Send notification
tools/agent-run-task "My task" "prompt"    # Spawn background subagent
```

## Adding a New Bridge

Create `agent_loop/bridges/yourbridge/`:

```python
# __init__.py
from agent_loop.bridges import register_bridge
from .bot import YourBridge
register_bridge("yourbridge", YourBridge)

# bot.py
from agent_loop.bridges.base import MessengerBridge

class YourBridge(MessengerBridge):
    async def start(self): ...
    async def stop(self): ...
    async def send_message(self, chat_id, text): ...
    async def send_typing(self, chat_id): ...
    async def send_progress(self, chat_id, text): ...
    async def send_file(self, chat_id, path, caption=""): ...
    async def notify(self, text): ...
```

Then set `bridge.type: "yourbridge"` in config.yaml.

## Deployment

### systemd

```ini
[Unit]
Description=Agent Loop
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/path/to/agent-loop
ExecStart=/path/to/agent-loop/.venv/bin/agent-loop start
Restart=always
RestartSec=5
EnvironmentFile=/path/to/agent-loop/.env

[Install]
WantedBy=multi-user.target
```

### Cron mode (alternative to built-in scheduler)

```bash
# Disable built-in loops
agent-loop start --no-loops

# Use system cron instead
*/30 8-22 * * * cd /path/to/agent-loop && .venv/bin/agent-loop heartbeat
0 23 * * *      cd /path/to/agent-loop && .venv/bin/agent-loop digest
0 */6 * * *     cd /path/to/agent-loop && .venv/bin/agent-loop maintain
```

## License

MIT
