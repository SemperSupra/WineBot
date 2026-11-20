# WineBot: Disposable runtime / application / persistent-state architecture

**Status:** opt-in public RDTE, **not production-promoted**. This is separate
from legacy `compose/docker-compose.yml`. Do not combine the two files until
an explicit migration/release gate has been qualified.

## Authority and design

Git/DLE holds desired topology, source, pins, package custody, diagnostics and
acceptance receipts. No long-lived local checkout, worktree, builder container,
runtime container, cache or privileged sidecar is authoritative.

| Layer | Representation | Lifetime | Allowed writes |
| --- | --- | --- | --- |
| Runtime | digest-pinned OCI WineBot REL image | disposable per run/restart | `tmpfs` only; no permanent rootfs writes |
| Applications | separately built digest-pinned OCI app pack; one-shot seed into a **version-specific external** volume mounted `/apps:ro` | replaceable independently | one-shot offline pack seeder only; never a running WineBot process |
| Persistent user state | external named volumes for Wine prefix, user home, configuration, user files, session evidence, and shared state | survives upgrades, container deletion and `docker compose down` | the unprivileged runtime/user; not app seeder |

The package *seeder* and state-preparer are short-lived, network-disabled
containers. Runtime runs as uid/gid 1000, with no capabilities, read-only image
filesystem and bounded writable tmpfs. The preparer runs as root with only
CHOWN, modifies top-level volume directory ownership but does not recursively
rewrite or delete user files. The app seeder is root inside its container but
has no Linux capabilities and no network. Neither preparer sees credentials.

The disposable runtime mounts all seven external application/state volumes with
`volume.nocopy: true`. Docker's default initial volume population can copy
image directory contents **and metadata/ownership** into a newly created
external volume when multiple dependent Compose containers are created.
Prevent runtime image copy-up before the independent one-shot app seeder and
state initializer execute. Do not use runtime image copy-up as an installer,
migration, backup or profile-provisioning mechanism. The build and deployment
must be qualified together: the composite startup test specifically tests this
ownership race and keeps its proof volumes isolated to one disposable runner.
Failure to acquire a seeder lock is not automatically a concurrent installation;
a separately classified unwritable app volume must fail without modifying user
data. This correction remains experimental until composite HIL demonstrates it.

The original `/wineprefix` retains Wine registry and per-user installed-app
state; this is **not** yet a clean separation of arbitrary Windows MSI/EXE
installation mutations. The new app layer is fully usable for portable packages
and curated read-only application payloads. Nonportable installers that alter
registry, Program Files, fonts, system DLLs and user configuration still need a
future snapshot/registry-overlay/migration qualification; do not assert their
portable installation semantics from this MVP. Never download or install
unverified programs on every runtime boot. The legacy
`WINEBOT_LOADOUT`, `WINE_WINETRICKS`, and `WINE_INSTALL_MS_FONTS` runtime
install paths are fail-closed in layered mode.

## Build / promotion

1. Build the runtime independently in a disposable public GHA job from
   pinned tool-builder and Wine base sources; tools fetched during build are
   checksum-controlled. The current third-party E2E Playwright builder image
   and remaining mutable input references require independent custody review
   before release. Artifact signatures, SBOM and provenance remain separate
   release/security gates.
2. Assemble an app pack from `apps/` into `docker/app-bundle.Dockerfile`.
   The builder uses an immutable Debian digest; there is no download or Wine
   installation step inside the app pack image. It creates deterministic
   per-file SHA-256 manifests, rejects symlinks and exits on errors.
   Restricted installers/assets must NOT be committed into the public repo;
   qualify them in a private controlled app-pack build and move only permitted
   verified artifacts.
3. Promote immutable runtime and app pack image **digests** independently.
   Create a fresh version-specific app volume when its app-pack content
   changes. The app seeder refuses existing mismatched/incomplete packs rather
   than overwriting them. Roll back by selecting the older immutable
   app image/dedicated volume; never alter user state implicitly.
4. Integrate installed-app registry migration only with explicit per-app
   compatibility metadata and reversible, backed-up state transactions.
   Uninstall or reset is never `docker compose down --volumes`.

## Deployment contract

Required environment variables (use a secure deployment/secret manager; never
publish values to CI logs or DLE):

- `WINEBOT_RUNTIME_IMAGE` and `WINEBOT_APP_BUNDLE_IMAGE`: immutable
  `registry/repository@sha256:<64-hex-digest>`.
- `WINEBOT_APP_VOLUME`: a **version-specific** existing external app-pack
  volume, not shared with mutable user state.
- `WINEBOT_PREFIX_VOLUME`, `WINEBOT_HOME_VOLUME`,
  `WINEBOT_CONFIG_VOLUME`, `WINEBOT_USERDATA_VOLUME`,
  `WINEBOT_ARTIFACT_VOLUME`, `WINEBOT_SHARED_VOLUME`: independent
  external volumes, each unique to the deployment/user and starting with
  `winebot-`; the preflight validates distinct names.
- `WINEBOT_API_TOKEN`, `WINEBOT_VNC_PASSWORD`: secrets supplied at
  deployment. The current API/VNC implementation uses environment-based
  injection and must receive separate secret-file or manager qualification
  before deployment beyond localhost.

Run `bash scripts/layers/preflight.sh --check` to validate without
modification, or `--create` to initialize only missing named volumes.
Then `docker compose -f compose/layered.yml config --quiet` and
`docker compose -f compose/layered.yml up --no-build -d winebot-interactive`.
No build occurs on the deployed host. UI/API/VNC only bind loopback until
an approved authenticated ingress/proxy is independently qualified.

`docker compose -f compose/layered.yml down` removes only containers/networks.
All volumes are declared `external: true`; even `down -v` must not delete
their data. Do not use `docker volume rm` on user/app volumes. Back up and
restore each external volume before any migration or rollback and verify the
restored user profile, application settings, files and credentials. A change to
app version may require a compatible Wine prefix migration; do not silently
rewrite the profile to make an installer pass.

## Qualification / DX / UX

The dedicated public `disposable-layer-qualification.yml` workflow performs
zero-secret, synthetic, network-off GHA replay: source-contract checks, shell
syntax checks, bundle build, idempotent seed, state ownership bootstrap,
read-only nonroot runtime recreation, persistent state replay, rejected app
version overwrite, fresh versioned app volume and retained profile data.
Only fixed-category results are published. Disposable CI volumes and images
are cleaned without ever touching real deployment volumes.

The composite source-pinned Wine 11 HIL has now passed real read-only-root
startup, authenticated API health, 90-second resource sampling, container
recreation with retained prefix/home/configuration/user/evidence state, and a
forced SIGKILL with retained state and health. That was a public RDTE milestone
and does **not** by itself qualify a production deployment.

The next gate, qualified in the same disposable public-runner composite,
extends the source-pinned Wine 11 candidate to a **55-minute sustained resource
soak**, an authenticated post-soak health check, bounded in-container Openbox
termination/recovery and another health check, followed by the previously
qualified container restart and SIGKILL persistent-state replay. The soak
records raw output only within the disposable runner; a fixed-enum classifier
from the pinned candidate reports failures. This gate is pending until its
exact-head public Actions result is terminal green.

Still required for release: arbitrary Windows installer/registry overlays and
safe migration, WinInspect real application observer and human accessibility
acceptance, user-data external-volume backup/restore and disaster recovery,
secure secret delivery, mandatory legacy-v1 conformance, and rights/security
reviews.

Human UI: recognizable profiles/app-pack versions, explicit backup/rollback
warnings, and desktop settings that survive replacement. Automation DX:
stable exit statuses, bounded enumerated markers, declarative configuration
and no hidden installs. Agent DX: exact immutable image/volume IDs, DLE
evidence, no secret/raw data publication, and non-destructive reconciliation.

## Legacy caveat

`docs/installing-apps.md` and the older `scripts/install-app.sh` describe
the legacy mutable-prefix flow. They are **not** approved as the new app
promotion mechanism. In particular, legacy `down -v` destroys data and must
not be used to reset a layered deployment.
