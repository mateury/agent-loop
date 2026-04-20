---
name: system-health
description: Check VPS health — disk, RAM, services, recent errors — and send a summary
version: 1.0.0
platforms: [linux]
tags: [ops, monitoring, maintenance]
metadata:
  agentskills:
    compatible: true
---

# System Health Check

Inspect the host's vital signs and produce a concise ops summary. Safe to run as a scheduled heartbeat action.

## Steps

1. **Disk usage** — flag any mount over 80%:
   ```bash
   df -h | awk 'NR>1 && $5+0 > 80 {print "WARN:", $0}'
   ```

2. **Memory pressure** — report used/total and flag if >85%:
   ```bash
   free -h
   ```

3. **Key services** — check status of services that must be running:
   ```bash
   systemctl is-active <service-name>
   ```

4. **Recent errors** — scan journal for errors in the past hour:
   ```bash
   journalctl --since "1 hour ago" -p err --no-pager | tail -20
   ```

5. **Produce output** in this format:
   ```
   # System Health — YYYY-MM-DD HH:MM

   ## Resources
   - Disk: XX% used (largest mount)
   - RAM: XX% used (X GB / Y GB)

   ## Services
   - <service>: ✅ active / ❌ inactive

   ## Recent errors
   - None / <error summary>

   ## Action required
   - None / <recommended action>
   ```

6. If any metric is critical (disk >90%, RAM >90%, service down), send an alert:
   ```bash
   notify-telegram "🚨 System alert: <issue>"
   ```

## Notes

- Keep the check idempotent — no writes, no side effects
- Skip the alert if running in dry-run mode (`$DRY_RUN=1`)
