"""Telegram bot commands — /start, /new, /model, /memory, /ping, etc."""

from __future__ import annotations

import logging
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from agent_loop.config import Config
from agent_loop.core.claude import MODELS
from agent_loop.core.controller import AgentController
from agent_loop.skills import SkillLoader

log = logging.getLogger(__name__)


def register_commands(config: Config, controller: AgentController):
    """Return a dict of command_name -> handler function."""

    async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Welcome message with available commands."""
        name = config.agent.name
        text = (
            f"**{name}** — your autonomous AI agent\n\n"
            f"Send me a message and I'll process it through Claude Code.\n\n"
            f"**Commands:**\n"
            f"/new — Start a new session\n"
            f"/model — Show/change model (opus, sonnet, haiku)\n"
            f"/memory — Show memory index\n"
            f"/todo — Show task list\n"
            f"/ping — Check bot status\n"
        )
        await update.message.reply_text(text)

    async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Reset the current session."""
        chat_id = str(update.message.chat_id)
        old = controller.reset_session(chat_id)
        if old:
            await update.message.reply_text("Session reset. Starting fresh.")
        else:
            await update.message.reply_text("No active session. Ready for a new conversation.")

    async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show or change the current model."""
        args = context.args
        if not args:
            current = controller.model or config.agent.model
            available = ", ".join(MODELS.keys())
            await update.message.reply_text(
                f"Current model: **{current}**\nAvailable: {available}"
            )
            return

        name = args[0].lower()
        if name not in MODELS:
            await update.message.reply_text(
                f"Unknown model: {name}\nAvailable: {', '.join(MODELS.keys())}"
            )
            return

        controller.set_model(name)
        await update.message.reply_text(f"Model changed to: **{name}** ({MODELS[name]})")

    async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show memory index."""
        memory_path = config.project_root / config.memory.path / "MEMORY.md"
        if not memory_path.exists():
            await update.message.reply_text("No memory index found.")
            return

        content = memory_path.read_text()
        if len(content) > 4000:
            content = content[:4000] + "\n\n... (truncated)"
        await update.message.reply_text(content)

    async def cmd_todo(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show the task list."""
        todo_path = config.project_root / "data" / "todo.md"
        if not todo_path.exists():
            await update.message.reply_text("No todo list found.")
            return

        content = todo_path.read_text()
        if len(content) > 4000:
            content = content[:4000] + "\n\n... (truncated)"
        await update.message.reply_text(content)

    async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Bot status check."""
        current_model = controller.model or config.agent.model
        sessions = controller.sessions.active_count
        store_stats = controller.store.stats()
        await update.message.reply_text(
            f"**{config.agent.name}** is running\n"
            f"Model: {current_model}\n"
            f"Active sessions: {sessions}\n"
            f"History: {store_stats['messages']} msgs in {store_stats['sessions']} sessions"
        )

    async def cmd_recall(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Search past conversations with FTS5."""
        args = context.args
        if not args:
            await update.message.reply_text(
                "Usage: /recall <query>\nSearches past sessions for relevant messages."
            )
            return

        query = " ".join(args)
        hits = controller.store.search(query, limit=10)
        if not hits:
            await update.message.reply_text(f"No matches for: {query}")
            return

        lines = [f"**Recall results for:** {query}\n"]
        for hit in hits:
            ts = hit["timestamp"][:10]
            role = hit["role"]
            content = hit["content"].replace("\n", " ")[:200]
            lines.append(f"`{ts}` [{role}] {content}")

        output = "\n".join(lines)
        if len(output) > 4000:
            output = output[:4000] + "\n\n... (truncated)"
        await update.message.reply_text(output)

    async def cmd_skills(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List available skills."""
        from agent_loop.skills import SkillLoader

        primary = config.project_root / "data" / "skills"
        external = [Path.home() / ".claude" / "skills"]
        loader = SkillLoader(primary, external)

        if not loader.skills:
            await update.message.reply_text(
                "No skills installed.\n\n"
                f"Create one at: {primary}/<name>/SKILL.md"
            )
            return

        text = "**Available skills:**\n" + loader.describe_all()
        await update.message.reply_text(text)

    return {
        "start": cmd_start,
        "new": cmd_new,
        "clear": cmd_new,  # alias
        "model": cmd_model,
        "memory": cmd_memory,
        "todo": cmd_todo,
        "ping": cmd_ping,
        "recall": cmd_recall,
        "skills": cmd_skills,
    }
