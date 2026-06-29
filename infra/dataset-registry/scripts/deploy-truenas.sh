#!/usr/bin/env bash
# ── Deploy Garage S3 + DVC Remote on TrueNAS ─────────────────────────────────
# Guide to deploying Garage for the dataset registry.
#
# Garage is now available as an OFFICIAL TrueNAS community app.
# This script is a guide — the actual install happens via the TrueNAS Web UI.
#
# Usage:
#   1. Apps → Available Apps → Garage → Install
#   2. Use garage-values.yaml for the form values (see truenas-apps/garage/)
#   3. Run this script afterward for bucket/key setup:
#      bash infra/dataset-registry/truenas-apps/garage/post-deploy.sh
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo ""
echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║      Dataset Registry — Garage Deployment Guide                  ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo ""
echo "  Garage is an OFFICIAL TrueNAS community app. Install it from:"
echo ""
echo "    TrueNAS Web UI → Apps → Available Apps → Garage → Install"
echo ""
echo "  Pre-filled values are at:"
echo "    ${PROJECT_ROOT}/truenas-apps/garage/garage-values.yaml"
echo ""
echo "  ── Key Configuration for Your Environment ──"
echo ""
echo "  S3 API Port:  30188  (DVC endpoint)"
echo "  Web UI Port:  30186"
echo "  Admin Port:   30190"
echo ""
echo "  Storage paths (use host_path):"
echo "    Data:              /mnt/Storage/models/garage/data"
echo "    Metadata:          /mnt/Storage/models/garage/meta"
echo "    Metadata Snapshots: /mnt/Storage/models/garage/snapshots"
echo ""
echo "  Replication Factor: 1 (single node)"
echo ""
echo "  ── After Installation ──"
echo "  Run the post-deploy script to create buckets and DVC keys:"
echo ""
echo "    bash ${PROJECT_ROOT}/truenas-apps/garage/post-deploy.sh"
echo ""
echo "  ── Prefer the Automated API Deploy? ──"
echo "  See deploy-truenas-api.sh for programmatic deployment."
echo ""
