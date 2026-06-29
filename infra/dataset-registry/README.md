# Dataset Registry

A standalone S3-compatible dataset registry backed by **Garage** on TrueNAS and
versioned with DVC (Data Version Control). This is designed to work independently —
any project can use it to version, store, and share datasets and model artifacts.

**Why Garage over MinIO?** The official TrueNAS MinIO app (stable train) is
[deprecated and blocks new installations](https://github.com/truenas/apps/tree/master/ix-dev/stable/minio).
Garage is the recommended replacement — available as an official TrueNAS
community app, actively maintained, and fully S3-compatible for DVC.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  TRUENAS (truenas.fritz.box)                                    │
│                                                                  │
│  Garage Container (official community app)                       │
│  ├─ Port 30188: S3-compatible API  (DVC endpoint)               │
│  ├─ Port 30186: Web UI              (management console)        │
│  └─ Port 30190: Admin API           (bucket/key management)     │
│                                                                  │
│  Storage (host_path):                                            │
│  ├─ /mnt/Storage/models/garage/data          → objects          │
│  ├─ /mnt/Storage/models/garage/meta          → metadata (SSD)   │
│  └─ /mnt/Storage/models/garage/snapshots     → snapshots        │
│                                                                  │
│  Buckets:                                                        │
│  ├─ winebot-models     → Model weights, datasets, checkpoints    │
│  ├─ winebot-annotations → Label files, evaluation results        │
│  └─ winebot-archives   → Old versions, experiment artifacts      │
└──────────────────────────────────────────────────────────────────┘
         ▲
         │ S3 API (port 30188)
         ▼
┌──────────────────────────────────────────────────────────────────┐
│  CLIENT MACHINES (Windows, Linux, WSL, CI runners)               │
│                                                                  │
│  DVC (Data Version Control)                                      │
│  ├─ dvc add   → track files/directories                         │
│  ├─ dvc push  → upload to TrueNAS Garage                        │
│  ├─ dvc pull  → download from TrueNAS Garage                    │
│  └─ dvc dag   → show data lineage                               │
│                                                                  │
│  Local cache: .dvc/cache/                                       │
│  Artifacts:   models/yolo/, models/dataset/, etc.               │
└──────────────────────────────────────────────────────────────────┘
```

## Setup

### Prerequisites

- TrueNAS 24.10+ (Docker-based app system)
- SSH access to `truenas.fritz.box`
- Sufficient storage at `/mnt/Storage/models/garage/`

### Step 1: Install Garage from TrueNAS Community Train

Garage is an official TrueNAS community app:

1. **TrueNAS Web UI → Apps → Available Apps → Garage → Install**

2. **Configure using the pre-filled values** at:
   [`truenas-apps/garage/garage-values.yaml`](truenas-apps/garage/garage-values.yaml)

   Key settings for your environment:
   - **Storage → Data**: Host path `/mnt/Storage/models/garage/data`
   - **Storage → Metadata**: Host path `/mnt/Storage/models/garage/meta`
   - **Storage → Metadata Snapshots**: Host path `/mnt/Storage/models/garage/snapshots`
   - **Network → S3 API Port**: 30188 (published)
   - **Network → Admin Port**: 30190 (published)
   - **Network → WebUI Port**: 30186 (published)
   - **Garage → Replication Factor**: 1 (single node)
   - **Garage → Region**: `garage`

3. **Generate secrets** before installing:
   ```bash
   # Admin token (for bucket/key management)
   openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 32

   # RPC secret (64-char hex)
   openssl rand -hex 32
   ```

4. Click **Install** and wait for the app to become healthy.

### Step 2: Post-Deploy — Create Buckets and DVC Keys

Run the setup script. It will SSH into TrueNAS, create buckets,
and generate DVC-compatible access keys:

```bash
bash infra/dataset-registry/truenas-apps/garage/post-deploy.sh
```

The script will prompt for the Garage admin token (from Step 1),
then:
1. Verify the Garage container is running
2. Create `winebot-models`, `winebot-annotations`, `winebot-archives` buckets
3. Create a `winebot-dvc` API key with read/write access
4. Print DVC credentials

Save the credentials printed at the end.

### Step 2: Post-Deploy — Create Buckets and DVC Keys

Run the setup script. It will SSH into TrueNAS, create buckets,
and generate DVC-compatible access keys:

```bash
bash infra/dataset-registry/truenas-apps/garage/post-deploy.sh
```

The script will prompt for the Garage admin token (from Step 1),
then:
1. Verify the Garage container is running
2. Create `winebot-models`, `winebot-annotations`, `winebot-archives` buckets
3. Create a `winebot-dvc` API key with read/write access
4. Optionally store credentials in the OS keychain and run client setup

### Step 3: Configure Client

**Recommended — store credentials in the OS credential manager:**

The credential is stored encrypted in your OS keychain, not in a plaintext file.

<details>
<summary>Linux (libsecret/secret-tool)</summary>

```bash
# Store credentials
bash infra/dataset-registry/scripts/setup-credential-store.sh \
  --access-key "GK..." --secret-key "your-secret-key"

# Run client setup (pulls from keychain automatically)
bash infra/dataset-registry/scripts/setup-client.sh
```
</details>

<details>
<summary>Windows (Windows Credential Manager)</summary>

```powershell
# Store credentials
.\infra\dataset-registry\scripts\setup-credential-store.ps1 `
  -AccessKey "GK..." -SecretKey "your-secret-key"

# Run client setup (pulls from Credential Manager automatically)
.\infra\dataset-registry\scripts\setup-client.ps1
```

To view stored credentials in the Windows UI:
Control Panel → User Accounts → Credential Manager → Windows Credentials → Generic Credentials

For the credential format reference:
```powershell
.\infra\dataset-registry\scripts\setup-credential-store.ps1 -ShowFormat
```
</details>

<details>
<summary>CI/CD or temporary (environment variables)</summary>

```bash
export INFRA_MINIO_ACCESS_KEY="winebot-dvc"
export INFRA_MINIO_SECRET_KEY="your-secret-key"
export INFRA_MINIO_PORT=30188
bash infra/dataset-registry/scripts/setup-client.sh
```
</details>

## Usage

### Version a Dataset

```bash
# Track a directory
dvc add models/wine-dataset/
git add models/wine-dataset.dvc .gitignore
git commit -m "dvc: track wine-dataset v1"

# Upload to TrueNAS Garage
dvc push -r truenas
```

### Download a Dataset

```bash
# From a fresh clone
git clone <repo>
dvc pull -r truenas
```

### Track Model Training (Provenance)

```bash
# Run training with DVC tracking
dvc run -n train-yolo-v4 \
  -d models/wine-dataset/ \
  -d scripts/train_yolo.py \
  -o models/yolo/wine-finetuned-v4.pt \
  python3 scripts/train_yolo.py

# View lineage
dvc dag

# Reproduce (re-run with same data + code)
dvc reproduce train-yolo-v4
```

### List Available Versions

```bash
# See what's tracked in the remote
dvc list-url s3://winebot-models

# See local DVC-tracked files
dvc status
```

## Credential Management

Credentials are stored in `.dvc/config.local` (gitignored). Set them once:

```bash
dvc remote modify truenas --local secret_access_key "your-key"
```

Or via environment variables (for CI/CD):
```bash
export DVC_REMOTE_TRUENAS_SECRET_ACCESS_KEY="your-key"
```

## Files

| File | Purpose |
|:---|:---|
| `truenas-apps/garage/garage-values.yaml` | Pre-filled config for TrueNAS Garage install |
| `truenas-apps/garage/post-deploy.sh` | Post-install: buckets, keys, DVC setup |
| `scripts/deploy-truenas.sh` | Deploy guide (points to Web UI + post-deploy) |
| `scripts/deploy-truenas-api.sh` | Automated deploy via TrueNAS API |
| `scripts/setup-credential-store.sh` | OS credential store for secrets (Linux/macOS) |
| `scripts/setup-credential-store.ps1` | Windows Credential Manager integration |
| `scripts/setup-client.sh` | Configure DVC on Linux/WSL (auto-detects keychain) |
| `scripts/setup-client.ps1` | Configure DVC on Windows (auto-detects Credential Manager) |
| `.env.registry.example` | Plaintext env template (fallback only) |

## Troubleshooting

### Cannot reach Garage S3 endpoint

```bash
# From client machine, test connectivity:
curl -v http://truenas.fritz.box:30188/health

# If it fails, check TrueNAS firewall and Garage container:
ssh truenas.fritz.box "docker ps --filter name=garage"
ssh truenas.fritz.box "docker logs garage --tail 20"
```

### DVC push fails with auth error

```bash
# Re-configure credentials:
dvc remote modify truenas --local secret_access_key "your-key"
dvc push -r truenas
```

### DVC says "not a DVC repository"

```bash
# Init DVC in your project:
cd your-project
dvc init
git commit -m "dvc: initialize"
# Then re-run setup-client.sh
```
