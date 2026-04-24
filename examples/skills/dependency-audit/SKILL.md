---
name: dependency-audit
description: Scan npm and pip projects for known security vulnerabilities and summarise findings
version: 1.0.0
platforms: [linux, macos]
tags: [security, maintenance, npm, python]
metadata:
  agentskills:
    compatible: true
---

# Dependency Audit

Scan all npm and Python projects in a directory tree for known security vulnerabilities. Produces a concise report — safe to run as a scheduled maintenance action.

## Steps

1. **Find npm projects** — locate `package.json` files (skip `node_modules`):
   ```bash
   find /path/to/projects -name "package.json" \
     -not -path "*/node_modules/*" \
     -not -path "*/.next/*"
   ```

2. **Audit each npm project**:
   ```bash
   for pkg in "${NPM_PROJECTS[@]}"; do
     dir=$(dirname "$pkg")
     echo "=== $dir ==="
     cd "$dir"
     npm audit --audit-level=moderate --json 2>/dev/null \
       | python3 -c "
   import sys, json
   data = json.load(sys.stdin)
   vulns = data.get('metadata', {}).get('vulnerabilities', {})
   total = sum(vulns.values())
   if total:
       print(f'  {vulns.get(\"critical\",0)} critical, {vulns.get(\"high\",0)} high, {vulns.get(\"moderate\",0)} moderate')
   else:
       print('  clean')
   "
   done
   ```

3. **Find Python projects** — locate `requirements.txt` or `pyproject.toml`:
   ```bash
   find /path/to/projects -name "requirements.txt" -o -name "pyproject.toml" \
     -not -path "*/.venv/*" -not -path "*/dist/*"
   ```

4. **Audit each Python project** (requires `pip-audit`):
   ```bash
   for req in "${PY_PROJECTS[@]}"; do
     dir=$(dirname "$req")
     echo "=== $dir ==="
     cd "$dir"
     pip-audit -r requirements.txt --format=columns 2>/dev/null \
       || echo "  pip-audit not available or no vulnerabilities"
   done
   ```

5. **Produce output** in this format:
   ```
   # Dependency Audit — YYYY-MM-DD HH:MM

   ## npm
   - /projects/app-one: 2 high, 1 moderate
     Action: npm audit fix (check for breaking changes first)
   - /projects/app-two: clean

   ## Python
   - /projects/service-one: 1 critical (requests 2.27.0 — CVE-2023-32681)
     Action: pip install requests>=2.31.0
   - /projects/service-two: clean

   ## Summary
   - 1 project needs attention (high/critical)
   - 2 projects clean
   ```

6. For any **critical or high** severity findings, flag them prominently and suggest the exact fix command if `npm audit` provides one.

## Notes

- Never run `npm audit fix --force` automatically — breaking changes require human review
- `pip-audit` must be installed separately: `pip install pip-audit`
- Moderate-only findings can be noted but do not require urgent action
- Run this weekly or before any production deployment
