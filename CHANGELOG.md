# Changelog

All notable changes to this project will be documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- Example skill: `dependency-audit` — scan npm and pip projects for known security vulnerabilities
- README: skills table listing all four bundled examples (`daily-review`, `repo-sync`, `system-health`, `dependency-audit`)
- 6 structural tests for example skills (`test_skill_examples.py`) — validates frontmatter, required fields, name/dirname consistency, non-empty body; CI now enforces skill format on every PR

---

## [0.2.1] — 2026-04-20

### Added
- 44 unit tests covering `memory.fencing`, `search.query`, and `core.nudges` modules
- GitHub Actions CI workflow — runs pytest on push/PR across Python 3.11 and 3.12
- Example skills: `system-health` and `repo-sync` (see `examples/skills/`)
- CI badge and `## Development` section in README

### Fixed
- Corrected GitHub repo URLs in `pyproject.toml` and `README.md` (`mateuszrybak` → `mateury`)

---

## [0.2.0] — 2026-04-19

### Added
- **FTS5 full-text session search** — search past conversation turns by keyword (`/recall` command)
- **Memory fencing** (`agent_loop.memory.fencing`) — injects recalled memory into user messages (not system prompt) to preserve prefix cache; strips injected tags from real user input to prevent prompt injection
- **Nudge counters** (`agent_loop.core.nudges`) — periodic reminders every N turns/iterations to consolidate knowledge into memory or save repeatable workflows as skills; adopted from Hermes Agent pattern
- **Skills loader** (`agent_loop.skills.loader`) — load custom skill definitions from `skills/` directory; skills are injected as context for recurring procedures
- `/recall` bot command — search past session context by keyword
- Turn counter stats in `/ping` response

### Changed
- Session storage upgraded to FTS5 virtual table for efficient keyword search
- Memory injection moved to user message boundary (preserves Anthropic prefix cache TTL)

---

## [0.1.0] — 2026-04-14

### Added
- Core agent loop with Claude Code CLI integration (`claude -p --stream-json --continue`)
- Telegram bridge — streaming tool-use status updates, file/photo/voice handling
- File-based tiered memory system (core / standard / ephemeral) with `MEMORY.md` index
- Heartbeat loop — autonomous task execution every 30 minutes (08:00–22:00)
- Daily digest — end-of-day journal and memory insight extraction from conversation log
- Memory maintenance — periodic verification, tagging, deduplication, and condensation
- Multi-threading mode — replies routed to new threads when session is busy
- 13 bot commands: `/start`, `/new`, `/clear`, `/model`, `/context`, `/todo`, `/memory`, `/ping`, and more
- Voice message transcription via Whisper (`small` model)
- `run-task` — background subagent runner with configurable model and timeout
- Docker and systemd deployment configurations
- Interactive setup wizard (`agent-loop setup`)
