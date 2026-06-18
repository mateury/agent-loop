---
name: ssl-check
description: Verify SSL certificates for a list of domains — expiry date, days remaining, and chain validity
version: 1.0.0
platforms: [linux, macos]
tags: [ops, security, monitoring, maintenance]
metadata:
  agentskills:
    compatible: true
---

# SSL Certificate Check

Verify that SSL certificates for your production domains are valid and not near expiry. Safe to run as a scheduled heartbeat action (recommended: daily or weekly).

## Steps

1. **Define your domains** — edit this list to match your production URLs:
   ```bash
   DOMAINS=(
     "example.com"
     "api.example.com"
     "shop.example.com"
   )
   ```

2. **Check each domain** using `openssl`:
   ```bash
   for domain in "${DOMAINS[@]}"; do
     expiry=$(echo | timeout 5 openssl s_client -servername "$domain" \
       -connect "$domain:443" 2>/dev/null \
       | openssl x509 -noout -enddate 2>/dev/null \
       | cut -d= -f2)

     if [ -z "$expiry" ]; then
       echo "ERROR $domain — could not connect or no certificate"
       continue
     fi

     expiry_epoch=$(date -d "$expiry" +%s 2>/dev/null \
       || date -j -f "%b %d %T %Y %Z" "$expiry" +%s 2>/dev/null)
     now_epoch=$(date +%s)
     days_left=$(( (expiry_epoch - now_epoch) / 86400 ))

     if [ "$days_left" -lt 14 ]; then
       status="🔴 CRITICAL"
     elif [ "$days_left" -lt 30 ]; then
       status="🟡 WARNING"
     else
       status="✅ OK"
     fi

     echo "$status $domain — $days_left days (expires $expiry)"
   done
   ```

3. **Verify certificate chain** (optional — catches incomplete chains):
   ```bash
   for domain in "${DOMAINS[@]}"; do
     result=$(echo | timeout 5 openssl s_client -servername "$domain" \
       -connect "$domain:443" -verify_return_error 2>&1 | grep "Verify return code")
     echo "$domain: $result"
   done
   ```

4. **Produce output** in this format:
   ```
   # SSL Check — YYYY-MM-DD HH:MM

   ## Certificate Status
   - ✅ example.com — 87 days (expires Sep 13 2026)
   - 🟡 api.example.com — 22 days (expires Jul 10 2026)
     Action: renew soon (Let's Encrypt: certbot renew)
   - 🔴 shop.example.com — 6 days (expires Jun 24 2026)
     Action: URGENT — renew immediately

   ## Summary
   - 1 domain needs urgent attention (< 14 days)
   - 1 domain due for renewal soon (< 30 days)
   - 1 domain healthy
   ```

5. For any domain with **< 14 days** remaining, flag it prominently and include the renewal command for common setups:
   - Let's Encrypt / Certbot: `certbot renew --dry-run` then `certbot renew`
   - Caddy: `caddy reload`
   - Manual: link to your CA's renewal panel

## Notes

- Requires `openssl` (pre-installed on most Linux/macOS systems) and `timeout`
- `timeout 5` prevents hanging on unresponsive hosts — adjust if needed
- The `date -d` syntax works on Linux (GNU coreutils); macOS uses `date -j -f`
- For wildcard certs (e.g. `*.example.com`), check any subdomain — expiry is shared
- Consider pairing with `system-health` to send a combined ops daily digest
- Let's Encrypt certificates expire every 90 days — alert at 30 days gives comfortable renewal window
