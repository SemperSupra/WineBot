# Security Policy

This document outlines security best practices and the shared responsibility model for running WineBot.

## 1. Shared Responsibility
WineBot provides a Windows compatibility layer inside a Linux container. Because Wine runs Windows binaries with the same privileges as the `winebot` user, a compromised Windows application can theoretically access any data within the container or attempt to pivot to your local network.

## 2. Recommended Hardening

### Network Isolation
If your automation does not require internet access, run the container with network isolation:
```bash
docker run --network none ...
```
In `docker-compose.yml`, use an internal network:
```yaml
networks:
  winebot-net:
    internal: true
```

### VNC Security (Encryption)
VNC traffic is **not encrypted** by default. To secure the remote desktop:
1. Bind VNC to localhost only: `VNC_BIND=127.0.0.1`.
2. Use an **SSH Tunnel** to access the desktop:
   ```bash
   ssh -L 5900:localhost:5900 user@remote-host
   ```
3. Always set a strong `VNC_PASSWORD`.

### API Protection
Always set an `API_TOKEN` in production environments. The dashboard and CLI will require this token to perform any actions.

### File System Safety
Mount your `apps/` and `automation/` directories as **Read-Only** (`:ro`) to prevent malicious scripts from modifying your local source files or installers. (Enabled by default in `compose/docker-compose.yml`).

## 3. Reporting a Vulnerability
If you discover a security vulnerability in WineBot, please open a GitHub Issue or contact the maintainers directly. Do not disclose sensitive bugs in public comments until a patch is available.

---

## 4. Credential Management Policy

### Naming Convention
All secrets use the `INFRA_<SERVICE>_<CREDENTIAL>` pattern:

| Variable | Purpose |
|----------|---------|
| `INFRA_WINEBOT_API_TOKEN` | API authentication token |
| `INFRA_WINEBOT_API_URL` | WineBot API URL |
| `INFRA_WINEBOT_SIDECAR_URL` | CV sidecar URL |
| `INFRA_VNC_PASSWORD` | VNC access password |
| `INFRA_NOVNC_PASSWORD` | noVNC web access password |
| `INFRA_GHCR_TOKEN` | GitHub Container Registry token (CI only) |
| `INFRA_DOCKER_GATEWAY` | Docker bridge gateway IP |
| `INFRA_CLOUDFLARE_TOKEN` | Cloudflare API token |
| `INFRA_UPTIMEROBOT_APIKEY` | UptimeRobot API key |
| `INFRA_HF_TOKEN` | HuggingFace token for model downloads |

### Setting Credentials
- **Local dev:** Copy `.env.example` → `.env` and fill in values. `.env` is gitignored.
- **Linux server:** Copy `deploy/winebot-credentials.template` to `/etc/winebot-credentials` with `chmod 600` and `chown root:root`.

### No Secrets in Code
- ❌ No hardcoded passwords, API keys, or tokens in source files
- ❌ No internal IPs, hostnames, or infrastructure topology in committed docs
- ✅ All secrets read from environment variables
- ✅ Fallback values documented as placeholders only
- ✅ `.env` files, `/etc/winebot-credentials` in `.gitignore`

## 5. Operational Logging Policy

All operational scripts log in structured JSON format to stderr:

```json
{"ts":"2026-06-28T12:34:56Z","level":"info","logger":"script-name","message":"Processing complete","elapsed_s":123.4}
```

### Python
```python
from logging_utils import get_logger
logger = get_logger("my-script")
logger.start("Processing")
logger.complete("Done")
logger.error("Failed", exc_info=True)
```

### Shell
```bash
source "$(dirname "$0")/logging_utils.sh"
log_start "Processing"
log_complete "Done"
```

### Event ID Allocation
| Range | Purpose |
|-------|---------|
| 1000-1099 | Local workstation |
| 1100-1199 | VPS infrastructure |
| 1200-1299 | Cloud services |
| 1300-1399 | Application deployments |
| 2000+ | Project-specific scripts |
