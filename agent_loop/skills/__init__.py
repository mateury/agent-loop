"""Skills loader — markdown-based skills compatible with agentskills.io standard.

Skills are directories with a required SKILL.md (YAML frontmatter + body) plus
optional references/, templates/, scripts/, assets/ subdirectories.

Skills are activated via slash commands (e.g. /my-skill) — the body is injected
as a user message when triggered. Progressive disclosure: list metadata cheaply,
load body only when activated.

Compatible with:
- ~/.claude/skills/ (Claude Code native skills)
- ~/.hermes/skills/ (Hermes Agent)
- agentskills.io open standard
"""

from agent_loop.skills.loader import Skill, SkillLoader, scan_skills

__all__ = ["Skill", "SkillLoader", "scan_skills"]
