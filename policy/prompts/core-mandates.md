# WineBot Agent Mandates (LLM-Optimized)

Follow these rules strictly when operating in the WineBot repository:

1. **NO HOST MODIFICATIONS**: All build, lint, and test commands must run via `scripts/wb` or `docker compose`. Never run `pip install` or `pytest` on the host.
2. **VERIFIED BINARIES**: Only download Windows tools via `windows-tools/download_tool.sh` with a hardcoded SHA256 hash.
3. **LAYERED TRUTH**: The session directory `/artifacts/sessions/<id>/` is the source of truth for runtime state (PIDs, logs, state files).
4. **HUMAN PRIORITY**: During interactive sessions, never preempt user input. Drop agent actions if the Input Broker denies access (HTTP 423).
5. **GRACEFUL TEARDOWN**: Always use `POST /lifecycle/shutdown` to stop the container. This ensures FFmpeg recording muxing and subtitle generation.
6. **PINNED EVERYTHING**: Use exact version numbers (`==`) for Python and full SHAs for GitHub Actions.
