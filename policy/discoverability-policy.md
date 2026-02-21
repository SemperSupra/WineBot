# Discoverability & Internet Exposure Policy

This document defines the project's stance on service discovery and public internet exposure.

## 1. Local Network Discoverability (Approved)

WineBot instances may advertise their presence on the local link using mDNS (Bonjour/Zeroconf) under the `_winebot-session._tcp.local.` service type.

- **Purpose**: To facilitate the "WineBot Hub" and multi-node management within a trusted local environment.
- **Constraints**: Metadata shared via mDNS TXT records must not contain sensitive information. Truncated HMAC signatures of the `API_TOKEN` are permitted to allow credential verification by trusted clients.

## 2. Broad Internet Discoverability (Forbidden)

WineBot **MUST NOT** implement or support protocols that enable automatic discovery over the public internet (e.g., global node registries, UPnP port forwarding, or public STUN/TURN integration for VNC).

- **Rationale**: WineBot provides full GUI control and arbitrary execution capabilities within a container. Publicly discoverable nodes are high-value targets for unauthorized takeover and brute-force attacks.
- **Security Standard**: Access from outside the local network must be handled via established secure tunnels (VPN, SSH Tunnels, or authenticated Reverse Proxies).

## 3. Remote Access Guidance

Users requiring remote access to WineBot instances should follow the "Secure-by-Design" principle:
1. **VPN**: Use WireGuard or Tailscale to extend the local trust boundary.
2. **SSH**: Use `ssh -L 8000:localhost:8000` to securely tunnel the API and VNC traffic.
3. **Proxy**: Use an authenticated proxy (e.g., Nginx with Basic Auth + TLS) if the API must be exposed.
