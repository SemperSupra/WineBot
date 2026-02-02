# Future Security Hardening (Strategy B)

This document outlines additional security hardening measures recommended for production deployments of WineBot.

## 1. Network Isolation
**Risk:** Malware or compromised automation scripts running in Wine could attack other devices on the network.
**Mitigation:**
- Isolate the container using a dedicated Docker network with no outbound access if internet is not required.
- Use `--network none` or internal-only networks.
- In `docker-compose.yml`, define a `winebot-net` with `internal: true`.

## 2. VNC/noVNC Hardening
**Risk:** VNC traffic is unencrypted by default.
**Mitigation:**
- Enforce `VNC_PASSWORD` in `entrypoint.sh`. Fail startup if `ENABLE_VNC=1` but password is unset.
- Recommend using SSH tunneling for VNC access (`-L 5900:localhost:5900`) rather than exposing ports globally.
- Disable noVNC (HTTP) in high-security environments.

## 3. Least Privilege & Read-Only Mounts
**Risk:** Automation scripts could modify the bot's own tools or installers.
**Mitigation:**
- Mount `apps/` and `automation/` as read-only (`:ro`) in `docker-compose.yml`.
- Run the API server as a separate user if possible (though it needs access to Wine/X11).
- Ensure the `winebot` user only has write access to `/wineprefix` and `/tmp`.

## 4. Resource Limits
**Risk:** DoS attacks via CPU/Memory exhaustion.
**Mitigation:**
- Set `cpus` and `mem_limit` in `docker-compose.yml`.
- Configure `ulimits` (e.g., `nofile`, `nproc`).

## 5. API Rate Limiting
**Risk:** Brute-force attacks on the API token.
**Mitigation:**
- Implement rate limiting middleware in `api/server.py` (e.g., `slowapi`).
