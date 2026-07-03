# Docker Engine on WSL2

**Date:** 2026-07-03
**Status:** Active local runtime architecture

## Finding

Docker Desktop has been removed from this Windows host. Docker Engine v29.6.1
runs inside the WSL2 `Ubuntu` distribution.

Agents and scripts must not assume that `docker` is available directly from
Windows PowerShell through Docker Desktop. Use WSL explicitly unless a local
PowerShell proxy function is known to be loaded.

## Required Command Form

Use this form from Windows:

```powershell
wsl -d Ubuntu docker <args>
wsl -d Ubuntu docker compose <args>
```

Examples:

```powershell
wsl -d Ubuntu docker info
wsl -d Ubuntu docker compose -f compose/docker-compose.yml ps -a
wsl -d Ubuntu docker compose -f compose/docker-compose.yml --profile interactive up -d
```

If running from PowerShell, proxy helpers may exist only when `$PROFILE` has
loaded:

```powershell
docker <args>
docker-gpu <args>
docker-web <args>
docker-build <args>
```

Do not rely on those helpers in automation. Prefer the explicit `wsl -d Ubuntu`
prefix.

## Storage Layout

Docker's engine storage remains inside the WSL2 ext4 VHDX:

```text
/var/lib/docker/
```

Persistent host data that must survive WSL distro rebuilds is stored on Windows:

```text
C:\Users\Mark\wsl-data\
  models/
  datasets/
  checkpoints/
  .env
  bootstrap.sh
  update-secrets.ps1
```

Large ML artifacts should use `C:\Users\Mark\wsl-data\` rather than WSL-only
paths when they need to survive distro resets.

## Networking

WSL2 uses mirrored networking. The current Windows LAN IP is `192.168.178.27`.
Published container ports, for example `-p 8080:80`, are reachable on the LAN at
that host IP. mDNS/Avahi works between the LAN, Windows host, WSL2, and
containers.

## Credentials

Four Docker Swarm secrets currently exist:

- `infra_ghcr_token`
- `infra_cloudflare_token`
- `infra_caprover_password`
- `infra_uptimerobot_apikey`

Ad-hoc container environment values live at:

```text
C:\Users\Mark\wsl-data\.env
```

Credential sync is handled by:

```text
C:\Users\Mark\wsl-data\update-secrets.ps1
```

That script reads Windows Credential Manager and syncs both the `.env` file and
Swarm secrets.

## Security Profiles

Use the appropriate helper profile when available:

| Helper | Intended workload | Security posture |
|:---|:---|:---|
| `docker-gpu` | GPU training/inference jobs | `nobody`, drops capabilities, `SYS_NICE`, read-only, no network |
| `docker-web` | Web services | `www-data`, drops capabilities, `NET_BIND_SERVICE`, read-only, no new privileges |
| `docker-build` | CI/build workloads | `nobody`, drops capabilities, no new privileges, no network |

These helpers are PowerShell profile conveniences. For portable automation,
expand the intended flags explicitly or run Docker through WSL.

## Common Operations

```powershell
# Start Docker
wsl -d Ubuntu sudo service docker start

# Stop Docker
wsl -d Ubuntu sudo service docker stop

# Check Docker status
wsl -d Ubuntu docker info

# Pull an image
wsl -d Ubuntu docker pull <image>

# Run Compose
wsl -d Ubuntu docker compose up -d
```

Use `docker compose`, not `docker-compose`.

## What No Longer Works

- Docker Desktop GUI
- Docker Desktop system tray integration
- Direct Windows `docker` commands unless a PowerShell proxy is loaded
- `docker-compose` v1

## SSH Key Access

The WSL rebuild/support SSH key is stored at:

```text
C:\Users\Mark\wsl-data\root\.ssh\id_rsa
```
