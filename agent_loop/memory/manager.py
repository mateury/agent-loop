"""Memory manager — CRUD operations on file-based memories with YAML frontmatter."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class Memory:
    """A single memory file parsed into structure."""

    filename: str
    name: str = ""
    description: str = ""
    type: str = "project"
    tags: list[str] = field(default_factory=list)
    body: str = ""
    path: Path | None = None

    @property
    def frontmatter(self) -> str:
        """Render YAML frontmatter."""
        lines = [
            "---",
            f"name: {self.name}",
            f"description: {self.description}",
            f"type: {self.type}",
        ]
        if self.tags:
            tags_str = ", ".join(self.tags)
            lines.append(f"tags: [{tags_str}]")
        lines.append("---")
        return "\n".join(lines)

    def render(self) -> str:
        """Render full file content."""
        return f"{self.frontmatter}\n\n{self.body}\n"


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from a markdown file.

    Returns:
        Tuple of (metadata_dict, body_text).
    """
    match = FRONTMATTER_RE.match(content)
    if not match:
        return {}, content

    fm_text = match.group(1)
    body = content[match.end():]

    # Simple YAML parsing (no full YAML dependency needed for flat key-value)
    metadata = {}
    for line in fm_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        # Handle lists: [tag1, tag2]
        if value.startswith("[") and value.endswith("]"):
            items = value[1:-1].split(",")
            metadata[key] = [item.strip() for item in items if item.strip()]
        elif value.lower() == "true":
            metadata[key] = True
        elif value.lower() == "false":
            metadata[key] = False
        elif value.isdigit():
            metadata[key] = int(value)
        else:
            metadata[key] = value

    return metadata, body


class MemoryManager:
    """Manages the file-based memory system.

    Memory files live in a directory with YAML frontmatter and markdown bodies.
    An index file (MEMORY.md) provides quick-reference pointers.
    """

    def __init__(self, memory_dir: str | Path):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def list_all(self) -> list[Memory]:
        """List all memory files (excluding index and stats)."""
        memories = []
        for path in sorted(self.memory_dir.glob("*.md")):
            if path.name in ("MEMORY.md",):
                continue
            try:
                content = path.read_text()
                meta, body = parse_frontmatter(content)
                memories.append(
                    Memory(
                        filename=path.name,
                        name=meta.get("name", path.stem),
                        description=meta.get("description", ""),
                        type=meta.get("type", "project"),
                        tags=meta.get("tags", []),
                        body=body.strip(),
                        path=path,
                    )
                )
            except Exception as e:
                log.warning("Failed to parse memory %s: %s", path.name, e)
        return memories

    def get(self, filename: str) -> Memory | None:
        """Get a specific memory by filename."""
        path = self.memory_dir / filename
        if not path.exists():
            return None
        content = path.read_text()
        meta, body = parse_frontmatter(content)
        return Memory(
            filename=filename,
            name=meta.get("name", path.stem),
            description=meta.get("description", ""),
            type=meta.get("type", "project"),
            tags=meta.get("tags", []),
            body=body.strip(),
            path=path,
        )

    def save(self, memory: Memory) -> Path:
        """Save a memory to disk."""
        path = self.memory_dir / memory.filename
        path.write_text(memory.render())
        memory.path = path
        log.info("Saved memory: %s", memory.filename)
        return path

    def delete(self, filename: str) -> bool:
        """Delete a memory file."""
        path = self.memory_dir / filename
        if path.exists():
            path.unlink()
            log.info("Deleted memory: %s", filename)
            return True
        return False

    def search(self, query: str) -> list[Memory]:
        """Search memories by name, description, tags, or body content."""
        query_lower = query.lower()
        results = []
        for mem in self.list_all():
            searchable = f"{mem.name} {mem.description} {' '.join(mem.tags)} {mem.body}".lower()
            if query_lower in searchable:
                results.append(mem)
        return results

    def by_type(self, memory_type: str) -> list[Memory]:
        """Filter memories by type (user, project, feedback, reference, journal)."""
        return [m for m in self.list_all() if m.type == memory_type]

    def by_tag(self, tag: str) -> list[Memory]:
        """Filter memories by tag."""
        return [m for m in self.list_all() if tag in m.tags]

    def all_tags(self) -> dict[str, int]:
        """Get all tags with their count."""
        tag_counts: dict[str, int] = {}
        for mem in self.list_all():
            for tag in mem.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        return dict(sorted(tag_counts.items(), key=lambda x: -x[1]))
