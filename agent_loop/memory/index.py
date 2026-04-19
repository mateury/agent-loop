"""MEMORY.md index management."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from agent_loop.memory.manager import Memory

log = logging.getLogger(__name__)

# Sections in MEMORY.md, ordered
SECTIONS = ["User", "Project", "Feedback", "Reference", "Journal"]

# Map memory type → section name
TYPE_TO_SECTION = {
    "user": "User",
    "project": "Project",
    "feedback": "Feedback",
    "reference": "Reference",
    "journal": "Journal",
}


def generate_index(memories: list[Memory]) -> str:
    """Generate MEMORY.md content from a list of memories."""
    sections: dict[str, list[str]] = {s: [] for s in SECTIONS}

    for mem in memories:
        section = TYPE_TO_SECTION.get(mem.type, "Project")
        desc = mem.description or mem.name
        line = f"- [{mem.name}]({mem.filename}) \u2014 {desc}"
        sections[section].append(line)

    lines = []
    for section_name in SECTIONS:
        entries = sections[section_name]
        if entries:
            lines.append(f"## {section_name}")
            lines.extend(entries)
            lines.append("")

    return "\n".join(lines).strip() + "\n"


def update_index(memory_dir: Path, memories: list[Memory]):
    """Write/overwrite MEMORY.md index."""
    index_path = memory_dir / "MEMORY.md"
    content = generate_index(memories)
    index_path.write_text(content)
    log.info("Updated MEMORY.md with %d entries", len(memories))


def add_to_index(memory_dir: Path, memory: Memory):
    """Add a single memory entry to MEMORY.md (appending to correct section)."""
    index_path = memory_dir / "MEMORY.md"
    section_name = TYPE_TO_SECTION.get(memory.type, "Project")
    entry = f"- [{memory.name}]({memory.filename}) \u2014 {memory.description or memory.name}"

    if not index_path.exists():
        content = f"## {section_name}\n{entry}\n"
        index_path.write_text(content)
        return

    content = index_path.read_text()

    # Find the section and append
    section_header = f"## {section_name}"
    if section_header in content:
        # Insert before the next section or at end
        lines = content.split("\n")
        new_lines = []
        inserted = False
        in_section = False
        for line in lines:
            if line.strip() == section_header:
                in_section = True
                new_lines.append(line)
                continue
            if in_section and (line.startswith("## ") or not line.strip()):
                if not inserted:
                    new_lines.append(entry)
                    inserted = True
                in_section = False
            new_lines.append(line)
        if in_section and not inserted:
            new_lines.append(entry)
        content = "\n".join(new_lines)
    else:
        # Section doesn't exist — add it
        content += f"\n## {section_name}\n{entry}\n"

    index_path.write_text(content)


def remove_from_index(memory_dir: Path, filename: str):
    """Remove a memory entry from MEMORY.md by filename."""
    index_path = memory_dir / "MEMORY.md"
    if not index_path.exists():
        return

    content = index_path.read_text()
    # Remove lines containing the filename
    lines = content.split("\n")
    filtered = [line for line in lines if f"({filename})" not in line]
    index_path.write_text("\n".join(filtered))


def init_memory_dir(memory_dir: Path):
    """Initialize memory directory with empty MEMORY.md and stats."""
    memory_dir.mkdir(parents=True, exist_ok=True)

    index_path = memory_dir / "MEMORY.md"
    if not index_path.exists():
        index_path.write_text(
            "## User\n\n## Project\n\n## Feedback\n\n## Reference\n\n## Journal\n"
        )

    stats_path = memory_dir / "memory-stats.json"
    if not stats_path.exists():
        import json

        stats = {
            "_meta": {
                "version": 1,
                "description": "Memory usage tracking for agent-loop",
                "tiers": {
                    "core": "Never delete — critical memories",
                    "standard": "Default — archive if unused 30+ days",
                    "ephemeral": "Auto-archive after 14 days",
                },
            },
            "files": {},
        }
        stats_path.write_text(json.dumps(stats, indent=2))
