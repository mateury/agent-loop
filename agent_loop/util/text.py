"""Text utilities — tool descriptions, text splitting."""

from __future__ import annotations

# Tool name → human-readable label (English defaults, override via config)
DEFAULT_TOOL_LABELS = {
    "Bash": "Running command",
    "Read": "Reading file",
    "Write": "Writing file",
    "Edit": "Editing file",
    "Glob": "Searching files",
    "Grep": "Searching code",
    "WebSearch": "Searching the web",
    "WebFetch": "Fetching page",
    "Agent": "Running subagent",
    "TodoWrite": "Updating tasks",
    "NotebookEdit": "Editing notebook",
}


def describe_tool_use(
    tool_name: str, tool_input: dict, labels: dict[str, str] | None = None
) -> str:
    """Create a human-readable description of a Claude tool call."""
    tool_labels = labels or DEFAULT_TOOL_LABELS
    label = tool_labels.get(tool_name, tool_name)

    if tool_name == "Bash":
        desc = tool_input.get("description", "")
        cmd = tool_input.get("command", "")
        detail = desc if desc else (cmd[:60] + "..." if len(cmd) > 60 else cmd)
        return f"{label}: {detail}" if detail else label
    elif tool_name in ("Read", "Write", "Edit"):
        path = tool_input.get("file_path", "")
        if path:
            parts = path.rsplit("/", 2)
            short = "/".join(parts[-2:]) if len(parts) >= 2 else path
            return f"{label}: {short}"
        return label
    elif tool_name in ("Glob", "Grep"):
        pattern = tool_input.get("pattern", "")
        return f"{label}: {pattern}" if pattern else label
    elif tool_name == "Agent":
        desc = tool_input.get("description", "")
        return f"{label}: {desc}" if desc else label
    else:
        return label


def split_text(text: str, max_len: int = 4096) -> list[str]:
    """Split text into chunks, preferring to break at newlines."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        split_pos = text.rfind("\n", 0, max_len)
        if split_pos == -1 or split_pos < max_len // 2:
            split_pos = max_len
        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip("\n")
    return chunks
