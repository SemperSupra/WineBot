# Dataset Registry

A standalone S3-compatible dataset registry backed by MinIO on TrueNAS and
versioned with DVC (Data Version Control). This is designed to work independently —
any project can use it to version, store, and share datasets and model artifacts.

Deploy MinIO as a **TrueNAS app** via the web UI, then configure clients with DVC.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  TRUENAS (truenas.fritz.box)                                    │
│                                                                  │
│  MinIO Container (Docker)                                        │
│  ├─ Port 9000: S3-compatible API                                │
│  └─ Port 9001: Web Console                                      │
│                                                                  │
│  Buckets:                                                        │
│  ├─ winebot-models     → Model weights, datasets, checkpoints    │
│  ├─ winebot-annotations → Label files, evaluation results        │
│  └─ winebot-archives   → Old versions, experiment artifacts      │
│                                                                  │
│  Storage: /mnt/Storage/models/minio/                             │
└──────────────────────────────────────────────────────────────────┘
         ▲
         │ S3 API (port 9000)
         ▼
┌──────────────────────────────────────────────────────────────────┐
│  CLIENT MACHINES (Windows, Linux, WSL, CI runners)               │
│                                                                  │
│  DVC (Data Version Control)                                      │
│  ├─ dvc add   → track files/directories                         │
│  ├─ dvc push  → upload to TrueNAS MinIO                         │
│  ├─ dvc pull  → download from TrueNAS MinIO                     │
│  └─ dvc dag   → show data lineage                               │
│                                                                  │
│  Local cache: .dvc/cache/                                       │
│  Artifacts:   models/yolo/, models/dataset/, etc.               │
└──────────────────────────────────────────────────────────────────┘
```

## Setup

### Step 1: Deploy MinIO on TrueNAS (Automated)

Run the deployment script from your local machine:

```bash
bash infra/dataset-registry/scripts/deploy-truenas-api.sh
```

The script will:
1. Connect to TrueNAS via SSH (prompts for password if no SSH key)
2. Auto-generate a TrueNAS API key (or accept one you provide)
3. Prompt for MinIO root password (auto-generates with strong default)
4. Deploy MinIO as a TrueNAS Custom App via the REST API
5. Create S3 buckets and a dedicated DVC user
6. Print DVC credentials and offer to run client setup

Or deploy manually via the TrueNAS Web UI:
1. Open TrueNAS Web UI / Apps / Custom App
2. Upload truenas-apps/minio/app.yaml
3. Set the root password, click Deploy

Or copy it first:
```bash
scp infra/dataset-registry/scripts/deploy-truenas.sh truenas.fritz.box:/tmp/
ssh truenas.fritz.box "sudo bash /tmp/deploy-truenas.sh"
```

The script will:
1. Start MinIO as a Docker container with persistent storage
2. Create buckets (`winebot-models`, `winebot-annotations`, `winebot-archives`)
3. Generate access credentials
4. Print DVC remote configuration for client machines

**Save the credentials** printed at the end.

### Step 2: Configure Client (Linux/WSL)

```bash
# Install DVC and configure the remote
export INFRA_MINIO_ACCESS_KEY="winebot-dvc"
export INFRA_MINIO_SECRET_KEY="your-secret-key"
bash infra/dataset-registry/scripts/setup-client.sh
```

### Step 2: Configure Client (Windows PowerShell)

```powershell
$env:INFRA_MINIO_ACCESS_KEY = "winebot-dvc"
$env:INFRA_MINIO_SECRET_KEY = "your-secret-key"
.\infra\dataset-registry\scripts\setup-client.ps1
```

## Usage

### Version a Dataset

```bash
# Track a directory
dvc add models/wine-dataset/
git add models/wine-dataset.dvc .gitignore
git commit -m "dvc: track wine-dataset v1"

# Upload to TrueNAS
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
| `scripts/deploy-truenas.sh` | Deploy MinIO on TrueNAS (run once) |
| `scripts/setup-client.sh` | Configure DVC on Linux/WSL |
| `scripts/setup-client.ps1` | Configure DVC on Windows |
| `.env.registry.example` | Credential template |
| `README.md` | This file |

## Troubleshooting

### Cannot reach MinIO

```bash
# From client machine, test connectivity:
curl -v http://truenas.fritz.box:9000/minio/health/live

# If it fails, check TrueNAS firewall and MinIO container:
ssh truenas.fritz.box "docker ps --filter name=minio"
ssh truenas.fritz.box "docker logs minio --tail 20"
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
