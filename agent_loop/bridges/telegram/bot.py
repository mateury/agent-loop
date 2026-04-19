"""Telegram bridge — full implementation connecting Telegram to the AgentController."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from telegram import Bot, Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from agent_loop.bridges.base import MessengerBridge
from agent_loop.bridges.telegram.commands import register_commands
from agent_loop.bridges.telegram.format import (
    format_and_split,
    strip_html,
    MAX_MESSAGE_LENGTH,
)
from agent_loop.bridges.telegram.media import (
    detect_media_type,
    download_file,
    download_voice,
)
from agent_loop.config import Config
from agent_loop.core.controller import AgentController

log = logging.getLogger(__name__)


class TelegramBridge(MessengerBridge):
    """Telegram bot bridge — handles all Telegram-specific concerns."""

    def __init__(self, config: Config):
        self.config = config
        self.controller = AgentController(config)
        self._app: Application | None = None
        self._bot_username: str | None = None
        self._files_dir = Path("/tmp/agent_loop_files")
        self._files_dir.mkdir(parents=True, exist_ok=True)

        # Auth: parse allowed user and group IDs
        self._allowed_users = self._parse_ids(config.telegram.user_id)
        self._allowed_groups = self._parse_ids(config.telegram.group_ids)

        # Default notification chat (group first, then first user)
        self._notification_chat_id = (
            next(iter(self._allowed_groups), None)
            or next(iter(self._allowed_users), None)
        )

    @staticmethod
    def _parse_ids(raw: str) -> set[int]:
        """Parse comma-separated IDs into a set of ints."""
        if not raw:
            return set()
        return {int(x.strip()) for x in raw.split(",") if x.strip()}

    def _is_allowed(self, update: Update) -> bool:
        """Check if the message sender is authorized."""
        user = update.effective_user
        if not user:
            return False
        chat = update.effective_chat
        if chat and chat.type in ("group", "supergroup"):
            return chat.id in self._allowed_groups
        return user.id in self._allowed_users

    def _is_addressed(self, update: Update) -> bool:
        """Check if bot is addressed in a group (always True in DM or configured groups)."""
        chat = update.effective_chat
        if not chat or chat.type not in ("group", "supergroup"):
            return True
        if chat.id in self._allowed_groups:
            return True
        msg = update.message
        if not msg:
            return False
        if msg.reply_to_message and msg.reply_to_message.from_user:
            if msg.reply_to_message.from_user.is_bot:
                return True
        if self._bot_username and msg.text and f"@{self._bot_username}" in msg.text:
            return True
        return False

    async def start(self) -> None:
        """Start the Telegram bot."""
        token = self.config.telegram.bot_token
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")

        builder = Application.builder().token(token).concurrent_updates(True)
        self._app = builder.build()

        # Get bot username
        bot_info = await self._app.bot.get_me()
        self._bot_username = bot_info.username
        log.info("Telegram bot started: @%s", self._bot_username)

        # Register commands
        commands = register_commands(self.config, self.controller)
        for name, handler in commands.items():
            self._app.add_handler(CommandHandler(name, handler))

        # Register message handlers
        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
        )
        self._app.add_handler(
            MessageHandler(filters.PHOTO | filters.Document.ALL, self._handle_file)
        )
        self._app.add_handler(
            MessageHandler(filters.VOICE | filters.AUDIO, self._handle_voice)
        )

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)

    async def stop(self) -> None:
        """Stop the Telegram bot gracefully."""
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

    async def send_message(self, chat_id: str, text: str) -> None:
        """Send formatted message, splitting if needed."""
        bot = self._app.bot
        chunks = format_and_split(text)
        for chunk in chunks:
            try:
                await bot.send_message(
                    chat_id=int(chat_id), text=chunk, parse_mode="HTML"
                )
            except Exception:
                plain = strip_html(chunk)[:MAX_MESSAGE_LENGTH]
                await bot.send_message(chat_id=int(chat_id), text=plain)

    async def send_progress(self, chat_id: str, text: str) -> None:
        """Send a short progress update (plain text)."""
        try:
            await self._app.bot.send_message(chat_id=int(chat_id), text=text)
        except Exception as e:
            log.warning("Failed to send progress: %s", e)

    async def send_typing(self, chat_id: str) -> None:
        """Show typing indicator."""
        try:
            await self._app.bot.send_chat_action(
                chat_id=int(chat_id), action=ChatAction.TYPING
            )
        except Exception:
            pass

    async def send_file(self, chat_id: str, path: str, caption: str = "") -> None:
        """Send a file, auto-detecting type."""
        p = Path(path)
        if not p.exists():
            log.warning("File not found: %s", path)
            return

        bot = self._app.bot
        cid = int(chat_id)
        media_type = detect_media_type(path)

        with open(p, "rb") as f:
            if media_type == "photo":
                await bot.send_photo(chat_id=cid, photo=f, caption=caption)
            elif media_type == "video":
                await bot.send_video(chat_id=cid, video=f, caption=caption)
            else:
                await bot.send_document(chat_id=cid, document=f, caption=caption)

    async def notify(self, text: str) -> None:
        """Send a proactive notification to the default chat."""
        if not self._notification_chat_id:
            log.warning("No notification chat configured")
            return
        await self.send_message(str(self._notification_chat_id), text)

    # --- Internal handlers ---

    async def _handle_message(self, update: Update, context):
        """Handle incoming text messages."""
        if not self._is_allowed(update):
            await update.message.reply_text("Unauthorized.")
            return

        if not self._is_addressed(update):
            return

        prompt = update.message.text
        if not prompt:
            return

        # Strip @mention
        if self._bot_username:
            prompt = prompt.replace(f"@{self._bot_username}", "").strip()
        if not prompt:
            return

        # Prefix with sender name
        sender = update.effective_user.first_name or "User"
        prompt = f"[{sender}]: {prompt}"

        chat_id = str(update.message.chat_id)
        msg_id = update.message.message_id

        async def on_progress(text: str):
            await self.send_progress(chat_id, text)

        async def on_typing():
            await self.send_typing(chat_id)

        response = await self.controller.handle_message(
            chat_id=chat_id,
            text=prompt,
            on_progress=on_progress,
            on_typing=on_typing,
        )

        if response.is_side_session:
            await update.message.reply_text("(side session)")

        # Send response
        chunks = format_and_split(response.text)
        bot = context.bot
        for i, chunk in enumerate(chunks):
            reply_id = msg_id if i == 0 else None
            try:
                await bot.send_message(
                    chat_id=int(chat_id),
                    text=chunk,
                    parse_mode="HTML",
                    reply_to_message_id=reply_id,
                )
            except Exception:
                plain = strip_html(chunk)[:MAX_MESSAGE_LENGTH]
                await bot.send_message(
                    chat_id=int(chat_id),
                    text=plain,
                    reply_to_message_id=reply_id,
                )

    async def _handle_file(self, update: Update, context):
        """Handle incoming photos and documents."""
        if not self._is_allowed(update):
            return
        if not self._is_addressed(update):
            return

        try:
            local_path, caption = await download_file(update, self._files_dir)
        except Exception as e:
            await update.message.reply_text(f"Failed to download file: {e}")
            return

        sender = update.effective_user.first_name or "User"
        prompt = f"[{sender}] sent a file: {local_path}"
        if caption:
            prompt += f"\nCaption: {caption}"

        chat_id = str(update.message.chat_id)

        async def on_progress(text: str):
            await self.send_progress(chat_id, text)

        async def on_typing():
            await self.send_typing(chat_id)

        response = await self.controller.handle_message(
            chat_id=chat_id,
            text=prompt,
            on_progress=on_progress,
            on_typing=on_typing,
        )

        chunks = format_and_split(response.text)
        for chunk in chunks:
            try:
                await context.bot.send_message(
                    chat_id=int(chat_id), text=chunk, parse_mode="HTML"
                )
            except Exception:
                plain = strip_html(chunk)[:MAX_MESSAGE_LENGTH]
                await context.bot.send_message(chat_id=int(chat_id), text=plain)

    async def _handle_voice(self, update: Update, context):
        """Handle incoming voice messages (requires whisper optional dep)."""
        if not self._is_allowed(update):
            return
        if not self._is_addressed(update):
            return

        try:
            local_path = await download_voice(update, self._files_dir)
        except Exception as e:
            await update.message.reply_text(f"Failed to download voice: {e}")
            return

        # Try Whisper transcription
        transcription = None
        try:
            transcription = await self._transcribe(local_path)
        except ImportError:
            log.info("Whisper not installed — sending audio path to Claude")
        except Exception as e:
            log.warning("Transcription failed: %s", e)

        sender = update.effective_user.first_name or "User"
        if transcription:
            prompt = f"[{sender}] sent a voice message.\nTranscription: {transcription}"
        else:
            prompt = f"[{sender}] sent a voice message: {local_path}"

        chat_id = str(update.message.chat_id)

        async def on_progress(text: str):
            await self.send_progress(chat_id, text)

        async def on_typing():
            await self.send_typing(chat_id)

        response = await self.controller.handle_message(
            chat_id=chat_id,
            text=prompt,
            on_progress=on_progress,
            on_typing=on_typing,
        )

        chunks = format_and_split(response.text)
        for chunk in chunks:
            try:
                await context.bot.send_message(
                    chat_id=int(chat_id), text=chunk, parse_mode="HTML"
                )
            except Exception:
                plain = strip_html(chunk)[:MAX_MESSAGE_LENGTH]
                await context.bot.send_message(chat_id=int(chat_id), text=plain)

        # Clean up voice file
        try:
            local_path.unlink(missing_ok=True)
        except Exception:
            pass

    async def _transcribe(self, audio_path: Path) -> str:
        """Transcribe audio using Whisper (optional dependency)."""
        import whisper  # raises ImportError if not installed

        loop = asyncio.get_event_loop()

        def _do_transcribe():
            # Lazy-load model
            if not hasattr(self, "_whisper_model"):
                self._whisper_model = whisper.load_model("small")
            result = self._whisper_model.transcribe(str(audio_path), language="pl")
            return result.get("text", "")

        return await loop.run_in_executor(None, _do_transcribe)
