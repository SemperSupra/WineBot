# Design Decision: Switch from MinIO to Garage for Dataset Registry

**Date:** 2026-06-29
**Status:** Decided
**Deciders:** Mark E. DeYoung
**Category:** Infrastructure — Dataset Versioning

## Context

The WineBot dataset registry needs S3-compatible object storage on TrueNAS for
DVC-based dataset versioning. We originally built a custom TrueNAS app definition
for MinIO, deploying it as a Custom App.

## Problem

The official TrueNAS **MinIO app** (stable train) is [deprecated](https://github.com/truenas/apps/tree/master/ix-dev/stable/minio):

1. **Blocks new installs** — the docker-compose template fails at install time:
   ```
   MinIO is deprecated and will be removed in a future release.
   Please consider using an alternative object storage solution such as AIStor.
   ```
2. **Title is "MinIO (Deprecated)"** — the app.yaml title field confirms it.
3. **No replacement in the community train** — `minio-console` is only a web UI, not a MinIO server.

Maintaining our own MinIO Custom App definition works today but:
- We're maintaining a full app definition (app.yaml, questions.yaml, templates, migrations, CI)
- MinIO as a project is fine, but the TrueNAS integration path has no future
- Any updates to the TrueNAS app system would require us to maintain parity

## Options Considered

### Option 1: Keep Custom MinIO App (Rejected)

**Pros:** Our app definition already exists. MinIO is battle-tested with DVC.

**Cons:** We're maintaining a full TrueNAS app definition ourselves. No official
integration path. If iXsystems changes the app format, we update it ourselves.
The upstream deprecation signals that MinIO on TrueNAS is a dead path.

### Option 2: Garage — Official Community App (Chosen)

**Pros:**
- **Official TrueNAS community app** — installs from TrueNAS Web UI in one click
- **Actively maintained** — iXsystems updates the app definition, not us
- **Fully S3-compatible** — DVC works identically to MinIO
- **Open source** — AGPL license, self-hosted
- **Lightweight** — single binary, modest resource requirements (2 CPU, 2 GB RAM)
- **Built-in web UI** — optional `khairul169/garage-webui` container
- **No deprecation risk** — newly added app (June 2025), actively developed
- **Config generation** — Garage app includes an init container that auto-generates the TOML config

**Cons:**
- Different CLI for bucket/key management (`garage` instead of `mc`)
- Designed for multi-node clusters (replication factor concepts), though single-node works fine
- Slightly less documented than MinIO for DVC integration specifically
- 64-character hex RPC secret requirement (minor friction)

### Option 3: SeaweedFS — Official Community App (Rejected)

**Pros:** Also an official TrueNAS community app. S3-compatible.

**Cons:**
- Complex architecture — 7 port mappings (master, volume, filer, S3, WebDAV, gRPC)
- S3 is bolted on top of a file system, not a native object store
- Overkill for a single-node dataset registry
- Designed for data-center topologies (racks, data centers as first-class config)

### Option 4: Deploy Raw MinIO Container via Custom App (Rejected)

**Pros:** No app definition to maintain. Just one Docker container.

**Cons:** No TrueNAS integration (no health checks, no permissions container,
no portal links, no upgrade path). Manual management of container lifecycle.
Worse UX than the community app approach.

## Decision

Replace the custom MinIO app definition with Garage from the TrueNAS community train.

Garage provides the best balance of:
- **Low maintenance** — iXsystems maintains the TrueNAS app integration
- **S3 compatibility** — DVC works without changes (same S3 API)
- **Simplicity** — single container, ~5 config fields
- **Future-proof** — newly added, actively maintained community app

## Consequences

**Positive:**
- We delete ~50 lines of custom TrueNAS app definition (no app.yaml, questions.yaml, etc.)
- Garage installs from the TrueNAS Web UI like any other community app
- We get proper health checks, permissions containers, and upgrade paths for free
- Our DVC configuration is near-identical — just change the endpoint URL

**Negative:**
- Port change: S3 API moves from port 9000 to **30188** (different from MinIO default)
- All existing DVC remotes must update their `endpointurl`
- Bucket creation uses Garage CLI (`garage bucket create`) instead of `mc`
- New RPC secret concept to manage (64-char hex)

**Migration path:**
- Deploy Garage alongside existing MinIO (different ports, no conflict)
- Run post-deploy script to create buckets and DVC keys
- Update DVC remote endpoint URL on all clients
- Decommission MinIO container once data is migrated

## Implementation

1. Removed `infra/dataset-registry/truenas-apps/dataset-registry/` (MinIO app def)
2. Created `infra/dataset-registry/truenas-apps/garage/` with:
   - `garage-values.yaml` — pre-filled install values for the TrueNAS Web UI
   - `post-deploy.sh` — bucket creation and DVC key generation
3. Updated all deployment scripts to reference Garage
4. Updated both client setup scripts (port 9000 → 30188)
5. Updated this README with Garage architecture

## References

- [Garage on TrueNAS Apps](https://github.com/truenas/apps/tree/master/ix-dev/community/garage)
- [Garage Documentation](https://garagehq.deuxfleurs.fr/)
- [Garage GitHub](https://git.deuxfleurs.fr/Deuxfleurs/garage)
- [DVC S3 Remote Configuration](https://dvc.org/doc/user-guide/data-management/remote-storage/amazon-s3)
- [TrueNAS MinIO Deprecation](https://github.com/truenas/apps/tree/master/ix-dev/stable/minio)
