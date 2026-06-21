---
name: http-health-check
description: Verify HTTP endpoints return expected status codes and respond within latency thresholds — with optional content keyword checks
version: 1.0.0
platforms: [linux, macos]
tags: [ops, monitoring, maintenance, reliability]
metadata:
  agentskills:
    compatible: true
---

# HTTP Health Check

Check that your production URLs are reachable, return the correct HTTP status, respond within an acceptable time, and contain expected content. Safe to run as a scheduled heartbeat action (recommended: hourly or after deploys).

## Steps

1. **Define your endpoints** — edit to match your production URLs and expected properties:
   ```bash
   # Format: "URL|expected_status|max_seconds|keyword"
   # keyword is optional — leave empty to skip content check
   ENDPOINTS=(
     "https://example.com|200|3|<title>"
     "https://example.com/api/health|200|2|ok"
     "https://example.com/sitemap.xml|200|5|<urlset"
     "https://example.com/robots.txt|200|2|"
   )
   ```

2. **Check each endpoint** using `curl`:
   ```bash
   errors=0
   warnings=0

   for entry in "${ENDPOINTS[@]}"; do
     IFS='|' read -r url expected_status max_seconds keyword <<< "$entry"

     # Fetch: follow redirects, capture status + timing, suppress body
     response=$(curl -sL --max-time "$max_seconds" \
       -o /tmp/_health_body \
       -w "%{http_code}|%{time_total}|%{url_effective}" \
       "$url" 2>/dev/null)

     http_code=$(echo "$response" | cut -d'|' -f1)
     time_total=$(echo "$response" | cut -d'|' -f2)
     final_url=$(echo "$response" | cut -d'|' -f3)

     # Status check
     if [ -z "$http_code" ] || [ "$http_code" = "000" ]; then
       echo "🔴 TIMEOUT/ERROR  $url — no response within ${max_seconds}s"
       errors=$((errors + 1))
       continue
     fi

     if [ "$http_code" != "$expected_status" ]; then
       echo "🔴 STATUS FAIL    $url — got $http_code, expected $expected_status"
       errors=$((errors + 1))
       continue
     fi

     # Latency check
     latency_ok=true
     time_ms=$(echo "$time_total * 1000 / 1" | bc 2>/dev/null || echo "?")
     if (( $(echo "$time_total > $max_seconds" | bc -l 2>/dev/null || echo 0) )); then
       echo "🟡 SLOW           $url — ${time_ms}ms (threshold ${max_seconds}s)"
       warnings=$((warnings + 1))
       latency_ok=false
     fi

     # Content check (optional)
     if [ -n "$keyword" ] && ! grep -q "$keyword" /tmp/_health_body 2>/dev/null; then
       echo "🔴 CONTENT FAIL   $url — keyword '$keyword' not found in response"
       errors=$((errors + 1))
       continue
     fi

     if $latency_ok; then
       echo "✅ OK             $url — HTTP $http_code in ${time_ms}ms"
     fi
   done
   rm -f /tmp/_health_body
   ```

3. **Produce output** in this format:
   ```
   # HTTP Health Check — YYYY-MM-DD HH:MM

   ## Endpoint Status
   - ✅ OK             https://example.com — HTTP 200 in 312ms
   - ✅ OK             https://example.com/api/health — HTTP 200 in 48ms
   - 🟡 SLOW           https://example.com/sitemap.xml — 3200ms (threshold 3s)
   - 🔴 STATUS FAIL    https://example.com/admin — got 503, expected 200

   ## Summary
   - 1 endpoint failing (immediate attention needed)
   - 1 endpoint slow (above latency threshold)
   - 2 endpoints healthy
   ```

4. If **any endpoint returns a non-2xx status or times out**, flag it prominently and suggest:
   - Check application logs: `journalctl -u <service> --since "5 minutes ago"`
   - Verify the deploy succeeded: confirm the latest commit is reflected
   - For 5xx errors: inspect for exceptions or OOM kills
   - For timeouts: check if the server process is running

## Notes

- Requires `curl` and `bc` (pre-installed on most Linux/macOS systems)
- `curl -sL` follows redirects automatically — the check passes if the final destination is healthy
- For APIs returning JSON, use a keyword like `"status":"ok"` or `{"healthy":true}`
- Pair with `ssl-check` for a complete endpoint health picture: SSL validity + HTTP reachability
- Latency thresholds depend on your SLOs — 3s is a sensible default for user-facing pages, 1s for APIs
- For sites behind a CDN, you may see variable response times — adjust thresholds or use `--resolve` to bypass CDN
