"""Configuration loader — merges YAML config, .env, and defaults."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv


@dataclass
class AgentConfig:
    name: str = "Atlas"
    language: str = "en"
    model: str = "sonnet"
    timeout: int = 600


@dataclass
class BridgeConfig:
    type: str = "telegram"
    typing_interval: float = 4.0
    progress_interval: float = 3.0
    max_side_sessions: int = 3


@dataclass
class TelegramConfig:
    bot_token: str = ""
    user_id: str = ""
    group_ids: str = ""


@dataclass
class MemoryConfig:
    enabled: bool = True
    path: str = "data/memory"
    core_ttl_days: int | None = None
    standard_ttl_days: int = 30
    ephemeral_ttl_days: int = 14


@dataclass
class HeartbeatConfig:
    enabled: bool = True
    interval_minutes: int = 30
    active_hours_start: int = 8
    active_hours_end: int = 22
    model: str = "sonnet"
    timeout: int = 900


@dataclass
class DigestConfig:
    enabled: bool = True
    hour: int = 23
    minute: int = 0
    model: str = "haiku"


@dataclass
class MaintainConfig:
    enabled: bool = True
    interval_hours: int = 6
    model: str = "sonnet"


@dataclass
class LoopsConfig:
    heartbeat: HeartbeatConfig = field(default_factory=HeartbeatConfig)
    digest: DigestConfig = field(default_factory=DigestConfig)
    maintain: MaintainConfig = field(default_factory=MaintainConfig)


@dataclass
class LoggingConfig:
    conversation_log: bool = True
    usage_csv: bool = True
    log_dir: str = "data/logs"
    level: str = "INFO"


@dataclass
class Config:
    agent: AgentConfig = field(default_factory=AgentConfig)
    bridge: BridgeConfig = field(default_factory=BridgeConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    loops: LoopsConfig = field(default_factory=LoopsConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # Resolved paths (set after loading)
    project_root: Path = field(default_factory=lambda: Path.cwd())
    claude_path: str = "claude"


def _merge_dict_to_dataclass(dc, data: dict):
    """Recursively merge a dict into a dataclass, only setting known fields."""
    if not data or not isinstance(data, dict):
        return
    for key, value in data.items():
        if not hasattr(dc, key):
            continue
        current = getattr(dc, key)
        if hasattr(current, "__dataclass_fields__") and isinstance(value, dict):
            _merge_dict_to_dataclass(current, value)
        else:
            setattr(dc, key, value)


def _find_claude_path() -> str:
    """Find claude CLI binary."""
    env_path = os.environ.get("CLAUDE_PATH", "")
    if env_path:
        return env_path
    # Check common locations
    for candidate in [
        shutil.which("claude"),
        os.path.expanduser("~/.local/bin/claude"),
        "/usr/local/bin/claude",
    ]:
        if candidate and Path(candidate).is_file():
            return candidate
    return "claude"


def load_config(
    config_path: str | Path | None = None,
    env_path: str | Path | None = None,
    project_root: Path | None = None,
) -> Config:
    """Load configuration from YAML + .env + environment.

    Priority (highest wins): env vars > .env > config.yaml > defaults
    """
    root = project_root or Path.cwd()
    cfg = Config(project_root=root)

    # Load .env file
    env_file = Path(env_path) if env_path else root / ".env"
    if env_file.exists():
        load_dotenv(env_file)

    # Load YAML config
    yaml_path = Path(config_path) if config_path else root / "config.yaml"
    if yaml_path.exists():
        with open(yaml_path) as f:
            data = yaml.safe_load(f) or {}

        _merge_dict_to_dataclass(cfg.agent, data.get("agent"))
        _merge_dict_to_dataclass(cfg.bridge, data.get("bridge"))
        _merge_dict_to_dataclass(cfg.memory, data.get("memory"))
        _merge_dict_to_dataclass(cfg.logging, data.get("logging"))

        # Loops have nested config
        loops_data = data.get("loops", {})
        if loops_data:
            _merge_dict_to_dataclass(cfg.loops.heartbeat, loops_data.get("heartbeat"))
            _merge_dict_to_dataclass(cfg.loops.digest, loops_data.get("digest"))
            _merge_dict_to_dataclass(cfg.loops.maintain, loops_data.get("maintain"))

    # Telegram config from environment
    cfg.telegram.bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    cfg.telegram.user_id = os.environ.get("TELEGRAM_USER_ID", "")
    cfg.telegram.group_ids = os.environ.get(
        "TELEGRAM_GROUP_IDS", os.environ.get("TELEGRAM_GROUP_ID", "")
    )

    # Claude path
    cfg.claude_path = _find_claude_path()

    # Override timeout from env
    env_timeout = os.environ.get("CLAUDE_TIMEOUT")
    if env_timeout:
        cfg.agent.timeout = int(env_timeout)

    return cfg
