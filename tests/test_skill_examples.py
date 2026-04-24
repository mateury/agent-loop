"""Structural tests for bundled example skills in examples/skills/."""

import re
from pathlib import Path

SKILLS_DIR = Path(__file__).parent.parent / "examples" / "skills"
REQUIRED_FIELDS = {"name", "description", "version", "platforms", "tags"}


def _parse_frontmatter(text: str) -> dict:
    """Extract YAML frontmatter fields as a simple key→value dict."""
    match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}
    fields = {}
    for line in match.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            key, _, val = line.partition(":")
            fields[key.strip()] = val.strip()
    return fields


def skill_dirs():
    return [d for d in SKILLS_DIR.iterdir() if d.is_dir()]


class TestSkillExamples:
    def test_at_least_one_skill(self):
        assert len(skill_dirs()) >= 1, "No skill examples found"

    def test_each_skill_has_skill_md(self):
        for skill_dir in skill_dirs():
            skill_md = skill_dir / "SKILL.md"
            assert skill_md.exists(), f"{skill_dir.name}: missing SKILL.md"

    def test_each_skill_has_frontmatter(self):
        for skill_dir in skill_dirs():
            content = (skill_dir / "SKILL.md").read_text()
            assert content.startswith("---"), f"{skill_dir.name}: SKILL.md missing frontmatter"
            fields = _parse_frontmatter(content)
            assert fields, f"{skill_dir.name}: could not parse frontmatter"

    def test_each_skill_has_required_fields(self):
        for skill_dir in skill_dirs():
            content = (skill_dir / "SKILL.md").read_text()
            fields = _parse_frontmatter(content)
            missing = REQUIRED_FIELDS - fields.keys()
            assert not missing, f"{skill_dir.name}: missing fields {missing}"

    def test_each_skill_name_matches_dirname(self):
        for skill_dir in skill_dirs():
            content = (skill_dir / "SKILL.md").read_text()
            fields = _parse_frontmatter(content)
            assert fields.get("name") == skill_dir.name, (
                f"{skill_dir.name}: name field '{fields.get('name')}' "
                f"doesn't match directory name"
            )

    def test_each_skill_has_body(self):
        for skill_dir in skill_dirs():
            content = (skill_dir / "SKILL.md").read_text()
            after_frontmatter = re.sub(r"^---\n.*?\n---\n", "", content, flags=re.DOTALL)
            assert len(after_frontmatter.strip()) > 50, (
                f"{skill_dir.name}: SKILL.md body too short"
            )
