"""CLI entry point — agent-loop start|setup|heartbeat|digest|maintain"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from agent_loop import __version__
from agent_loop.config import load_config
from agent_loop.util.logging import setup_logging


def main():
    parser = argparse.ArgumentParser(
        prog="agent-loop",
        description="Autonomous AI agent framework powered by Claude Code CLI",
    )
    parser.add_argument("--version", action="version", version=f"agent-loop {__version__}")
    parser.add_argument("--config", type=str, default=None, help="Path to config.yaml")
    parser.add_argument("--env", type=str, default=None, help="Path to .env file")

    sub = parser.add_subparsers(dest="command")

    # start — run bot + scheduler
    start_p = sub.add_parser("start", help="Start the agent (bot + autonomous loops)")
    start_p.add_argument("--no-loops", action="store_true", help="Disable autonomous loops")

    # setup — interactive setup wizard
    sub.add_parser("setup", help="Interactive setup wizard")

    # init — initialize data directory
    sub.add_parser("init", help="Initialize data directory and CLAUDE.md")

    # heartbeat — run one heartbeat cycle
    sub.add_parser("heartbeat", help="Run one heartbeat cycle")

    # digest — run daily digest
    sub.add_parser("digest", help="Run daily digest")

    # maintain — run memory maintenance
    sub.add_parser("maintain", help="Run memory maintenance cycle")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "setup":
        _run_setup()
    elif args.command == "init":
        _run_init(args)
    elif args.command == "start":
        _run_start(args)
    elif args.command == "heartbeat":
        _run_loop(args, "heartbeat")
    elif args.command == "digest":
        _run_loop(args, "digest")
    elif args.command == "maintain":
        _run_loop(args, "maintain")


def _run_start(args):
    """Start the agent: messenger bridge + autonomous loops."""
    config = load_config(config_path=args.config, env_path=args.env)
    setup_logging(config.logging.level, config.project_root / config.logging.log_dir)

    log = logging.getLogger(__name__)
    log.info("Starting agent-loop v%s", __version__)
    log.info("Bridge: %s | Model: %s | Loops: %s",
             config.bridge.type,
             config.agent.model,
             "disabled" if args.no_loops else "enabled")

    asyncio.run(_start_async(config, enable_loops=not args.no_loops))


async def _start_async(config, enable_loops: bool):
    log = logging.getLogger(__name__)

    # Import and create bridge
    from agent_loop.bridges import get_bridge

    # Ensure telegram bridge is registered
    import agent_loop.bridges.telegram  # noqa: F401

    bridge = get_bridge(config.bridge.type, config)

    # Start scheduler
    scheduler = None
    if enable_loops:
        from agent_loop.loops.scheduler import LoopScheduler
        scheduler = LoopScheduler(config, notify_fn=bridge.notify)
        scheduler.start()

    # Handle shutdown signals
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def _signal_handler():
        log.info("Shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    # Start bridge
    try:
        await bridge.start()
        log.info("Agent is running. Press Ctrl+C to stop.")
        await stop_event.wait()
    finally:
        log.info("Shutting down...")
        if scheduler:
            scheduler.stop()
        await bridge.stop()
        log.info("Agent stopped.")


def _run_loop(args, loop_name: str):
    """Run a single loop cycle."""
    config = load_config(config_path=args.config, env_path=args.env)
    setup_logging(config.logging.level, config.project_root / config.logging.log_dir)

    if loop_name == "heartbeat":
        from agent_loop.loops.heartbeat import run_heartbeat
        result = asyncio.run(run_heartbeat(config))
    elif loop_name == "digest":
        from agent_loop.loops.digest import run_digest
        result = asyncio.run(run_digest(config))
    elif loop_name == "maintain":
        from agent_loop.loops.maintain import run_maintain
        result = asyncio.run(run_maintain(config))
    else:
        print(f"Unknown loop: {loop_name}", file=sys.stderr)
        sys.exit(1)

    if result:
        print(result)


def _run_init(args):
    """Initialize project data directory."""
    config = load_config(config_path=args.config, env_path=args.env)

    from agent_loop.memory.index import init_memory_dir

    # Create directories
    data_dir = config.project_root / "data"
    (data_dir / "logs").mkdir(parents=True, exist_ok=True)

    # Init memory
    memory_dir = config.project_root / config.memory.path
    init_memory_dir(memory_dir)

    # Create todo.md
    todo_path = data_dir / "todo.md"
    if not todo_path.exists():
        todo_path.write_text(
            "# Task List (TODO)\n\n"
            "> Format: `- [ ]` pending, `- [x]` done, `- [-]` cancelled\n\n"
            "## To Do\n\n"
            "(no tasks yet)\n"
        )

    # Create session-context.md
    ctx_path = data_dir / "session-context.md"
    if not ctx_path.exists():
        ctx_path.write_text(
            "# Session Context\n\n"
            "> Ephemeral state — updated during conversations, archived to memory.\n\n"
            "## Current\n\n(nothing in progress)\n"
        )

    print(f"Initialized data directory at {data_dir}")
    print(f"  Memory: {memory_dir}")
    print(f"  Logs: {data_dir / 'logs'}")
    print(f"  Todo: {todo_path}")
    print(f"  Context: {ctx_path}")


def _run_setup():
    """Interactive setup wizard."""
    print("=" * 50)
    print("  agent-loop setup wizard")
    print("=" * 50)
    print()

    # Check prerequisites
    import shutil
    claude = shutil.which("claude")
    if not claude:
        print("WARNING: 'claude' CLI not found in PATH.")
        print("Install Claude Code: https://docs.anthropic.com/en/docs/claude-code")
        claude = input("Path to claude binary (or Enter to skip): ").strip() or "claude"
    else:
        print(f"Found claude CLI: {claude}")

    print()

    # Bridge selection
    bridge = input("Messenger bridge [telegram]: ").strip() or "telegram"

    bot_token = ""
    user_id = ""
    group_ids = ""

    if bridge == "telegram":
        bot_token = input("Telegram bot token (from @BotFather): ").strip()
        user_id = input("Your Telegram user ID: ").strip()
        group_ids = input("Group chat IDs (comma-separated, or Enter to skip): ").strip()

    print()

    # Agent config
    name = input("Agent name [Atlas]: ").strip() or "Atlas"
    language = input("Response language [en]: ").strip() or "en"
    model = input("Default model (opus/sonnet/haiku) [sonnet]: ").strip() or "sonnet"

    print()

    # Loops
    enable_heartbeat = input("Enable heartbeat loop? [Y/n]: ").strip().lower() != "n"
    hb_interval = 30
    if enable_heartbeat:
        hb_raw = input("Heartbeat interval in minutes [30]: ").strip()
        if hb_raw.isdigit():
            hb_interval = int(hb_raw)

    print()

    # Write .env
    root = Path.cwd()
    env_path = root / ".env"
    env_lines = [
        f"TELEGRAM_BOT_TOKEN={bot_token}",
        f"TELEGRAM_USER_ID={user_id}",
    ]
    if group_ids:
        env_lines.append(f"TELEGRAM_GROUP_IDS={group_ids}")
    if claude != "claude":
        env_lines.append(f"CLAUDE_PATH={claude}")
    env_path.write_text("\n".join(env_lines) + "\n")
    print(f"Created: {env_path}")

    # Write config.yaml
    import yaml

    config_data = {
        "agent": {"name": name, "language": language, "model": model, "timeout": 600},
        "bridge": {"type": bridge},
        "memory": {"enabled": True, "path": "data/memory"},
        "loops": {
            "heartbeat": {
                "enabled": enable_heartbeat,
                "interval_minutes": hb_interval,
                "active_hours_start": 8,
                "active_hours_end": 22,
                "model": "sonnet",
            },
            "digest": {"enabled": True, "hour": 23, "minute": 0, "model": "haiku"},
            "maintain": {"enabled": True, "interval_hours": 6, "model": "sonnet"},
        },
        "logging": {
            "conversation_log": True,
            "usage_csv": True,
            "log_dir": "data/logs",
            "level": "INFO",
        },
    }
    config_path = root / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)
    print(f"Created: {config_path}")

    # Init data dir
    from agent_loop.memory.index import init_memory_dir

    data_dir = root / "data"
    (data_dir / "logs").mkdir(parents=True, exist_ok=True)
    init_memory_dir(data_dir / "memory")

    todo = data_dir / "todo.md"
    if not todo.exists():
        todo.write_text("# Task List\n\n## To Do\n\n(no tasks yet)\n")

    ctx = data_dir / "session-context.md"
    if not ctx.exists():
        ctx.write_text("# Session Context\n\n(nothing in progress)\n")

    print(f"Created: {data_dir}/")
    print()
    print("Setup complete! Start your agent:")
    print("  agent-loop start")
    print()
    print("Or with Docker:")
    print("  docker-compose up -d")


if __name__ == "__main__":
    main()
