"""Skills loader with progressive disclosure.

Scans skill directories, parses YAML frontmatter lightly, filters by platform,
and exposes slash commands. The body is loaded lazily on activation.
"""

from __future__ import annotations

import logging
import platform
import re
from dataclasses import dataclass, field
from pathlib import Path

from agent_loop.memory.manager import parse_frontmatter

log = logging.getLogger(__name__)

SKILL_FILE = "SKILL.md"


@dataclass
class Skill:
    """A single skill — metadata-only by default; body loaded on demand."""

    name: str
    description: str
    path: Path
    version: str = "1.0.0"
    platforms: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    prerequisites: dict = field(default_factory=dict)
    disabled: bool = False

    @property
    def command(self) -> str:
        """Slash command name (kebab-case from skill name)."""
        return re.sub(r"[^a-z0-9-]", "-", self.name.lower()).strip("-")

    @property
    def skill_file(self) -> Path:
        """Path to the SKILL.md file."""
        return self.path / SKILL_FILE

    def load_body(self) -> str:
        """Load the skill body (markdown content) — progressive disclosure."""
        if not self.skill_file.exists():
            return ""
        content = self.skill_file.read_text()
        _, body = parse_frontmatter(content)
        return body.strip()

    def activation_message(self) -> str:
        """The message injected when the skill is activated via /command."""
        body = self.load_body()
        return f"# Skill: {self.name}\n\n{body}"

    def is_compatible(self) -> bool:
        """Check if this skill runs on the current platform."""
        if not self.platforms:
            return True
        current = platform.system().lower()  # 'linux', 'darwin', 'windows'
        if current == "darwin":
            current = "macos"
        return current in [p.lower() for p in self.platforms]


def parse_skill_file(skill_file: Path) -> Skill | None:
    """Parse a SKILL.md into a Skill dataclass."""
    if not skill_file.exists():
        return None

    try:
        content = skill_file.read_text()
    except OSError as e:
        log.warning("Cannot read %s: %s", skill_file, e)
        return None

    meta, _ = parse_frontmatter(content)

    name = meta.get("name") or skill_file.parent.name
    description = meta.get("description", "")

    # Platforms can be a list or a single string
    platforms = meta.get("platforms", [])
    if isinstance(platforms, str):
        platforms = [platforms]

    tags = meta.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]

    # agentskills.io format uses nested hermes.tags
    if not tags:
        metadata = meta.get("metadata", {})
        if isinstance(metadata, dict):
            hermes = metadata.get("hermes", {})
            if isinstance(hermes, dict):
                tags = hermes.get("tags", []) or []

    return Skill(
        name=name,
        description=description,
        path=skill_file.parent,
        version=str(meta.get("version", "1.0.0")),
        platforms=platforms,
        tags=tags,
        prerequisites=meta.get("prerequisites", {}) or {},
    )


def scan_skills(directories: list[Path]) -> dict[str, Skill]:
    """Scan directories for skills.

    Returns dict of command -> Skill. If multiple skills share a command,
    the first found wins (local dirs should come first in `directories`).
    """
    skills: dict[str, Skill] = {}
    for skills_dir in directories:
        if not skills_dir or not skills_dir.exists():
            continue
        for entry in sorted(skills_dir.iterdir()):
            if not entry.is_dir():
                continue
            skill_file = entry / SKILL_FILE
            if not skill_file.exists():
                continue
            skill = parse_skill_file(skill_file)
            if not skill:
                continue
            if not skill.is_compatible():
                log.debug("Skill %s not compatible with this platform", skill.name)
                continue
            if skill.command in skills:
                log.debug("Skill command %s already registered, skipping %s",
                          skill.command, entry)
                continue
            skills[skill.command] = skill
    return skills


class SkillLoader:
    """Manages skill discovery from one or more directories."""

    def __init__(self, primary_dir: Path, external_dirs: list[Path] | None = None):
        """
        Args:
            primary_dir: User's main skills directory (writable).
            external_dirs: Additional read-only directories (e.g. team skills).
        """
        self.primary_dir = Path(primary_dir)
        self.external_dirs = [Path(d) for d in (external_dirs or [])]
        self._skills: dict[str, Skill] = {}

    def reload(self):
        """Rescan all directories."""
        dirs = [self.primary_dir] + self.external_dirs
        self._skills = scan_skills(dirs)
        log.info("Loaded %d skills from %d directories", len(self._skills), len(dirs))

    @property
    def skills(self) -> dict[str, Skill]:
        """Get all loaded skills (keyed by command name)."""
        if not self._skills:
            self.reload()
        return self._skills

    def get(self, command: str) -> Skill | None:
        """Look up a skill by command name."""
        return self.skills.get(command.lstrip("/"))

    def list_names(self) -> list[str]:
        """List all skill command names."""
        return sorted(self.skills.keys())

    def describe_all(self) -> str:
        """Render a markdown list of all skills with descriptions."""
        if not self.skills:
            return "_no skills installed_"
        lines = []
        for cmd, skill in sorted(self.skills.items()):
            lines.append(f"- **/{cmd}** — {skill.description or skill.name}")
        return "\n".join(lines)
