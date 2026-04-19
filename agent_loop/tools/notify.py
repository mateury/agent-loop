"""Send proactive notifications via the configured messenger bridge."""

from __future__ import annotations

import asyncio
import sys

from agent_loop.config import load_config


def main():
    """CLI entry point: agent-notify 'message' or echo 'message' | agent-notify"""
    if len(sys.argv) > 1:
        message = " ".join(sys.argv[1:])
    elif not sys.stdin.isatty():
        message = sys.stdin.read().strip()
    else:
        print("Usage: agent-notify 'message'", file=sys.stderr)
        print("   or: echo 'message' | agent-notify", file=sys.stderr)
        sys.exit(1)

    if not message:
        sys.exit(0)

    asyncio.run(_send(message))


async def _send(message: str):
    config = load_config()

    # Import bridge to send notification
    if config.bridge.type == "telegram":
        from agent_loop.bridges.telegram.format import markdown_to_telegram_html
        from telegram import Bot

        token = config.telegram.bot_token
        if not token:
            print("Error: TELEGRAM_BOT_TOKEN not set", file=sys.stderr)
            sys.exit(1)

        # Determine chat ID
        group_ids = config.telegram.group_ids
        user_id = config.telegram.user_id
        chat_id = int(group_ids.split(",")[0]) if group_ids else int(user_id)

        bot = Bot(token=token)
        formatted = markdown_to_telegram_html(message)

        async with bot:
            try:
                await bot.send_message(
                    chat_id=chat_id, text=formatted, parse_mode="HTML"
                )
            except Exception:
                # Fallback to plain text
                await bot.send_message(chat_id=chat_id, text=message[:4096])

        print("OK")
    else:
        print(f"Bridge '{config.bridge.type}' not yet supported for notifications", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
