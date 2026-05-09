#!/usr/bin/env bash
# One-time GCP setup for SFM backend deployment.
# Run once from a machine with `gcloud` installed and authenticated.
# Prereq: gcloud auth login && gcloud auth application-default login
set -euo pipefail

# ── Inputs ────────────────────────────────────────────────────────────────────
read -rp "GCP Project ID: " PROJECT_ID
read -rp "Region [us-central1]: " REGION
REGION="${REGION:-us-central1}"

SA_NAME="github-actions-sfm"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
REPO="sfm"
KEY_FILE="gcp-sa-key.json"

echo ""
echo "Using project: $PROJECT_ID  region: $REGION"
echo "────────────────────────────────────────────"

# ── Project ───────────────────────────────────────────────────────────────────
gcloud config set project "$PROJECT_ID"

# ── Enable APIs ───────────────────────────────────────────────────────────────
echo "Enabling APIs..."
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  iam.googleapis.com

# ── Artifact Registry ─────────────────────────────────────────────────────────
echo "Creating Artifact Registry repository '$REPO'..."
gcloud artifacts repositories create "$REPO" \
  --repository-format docker \
  --location "$REGION" \
  --description "SFM Docker images" 2>/dev/null \
  || echo "  (already exists, skipping)"

# ── Service account ───────────────────────────────────────────────────────────
echo "Creating service account '$SA_NAME'..."
gcloud iam service-accounts create "$SA_NAME" \
  --display-name "GitHub Actions – SFM" 2>/dev/null \
  || echo "  (already exists, skipping)"

echo "Granting IAM roles..."
for ROLE in \
  roles/artifactregistry.writer \
  roles/run.admin \
  roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member "serviceAccount:$SA_EMAIL" \
    --role "$ROLE" \
    --quiet
done

# ── SA key ────────────────────────────────────────────────────────────────────
echo "Generating service account key → $KEY_FILE"
gcloud iam service-accounts keys create "$KEY_FILE" \
  --iam-account "$SA_EMAIL"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════"
echo " Setup complete. Add these secrets to GitHub:"
echo " https://github.com/YOUR_ORG/SFM/settings/secrets/actions"
echo "════════════════════════════════════════════════════"
echo ""
echo "  GCP_PROJECT_ID  →  $PROJECT_ID"
echo ""
echo "  GCP_SA_KEY      →  paste the output of:"
if command -v pbcopy &>/dev/null; then
  echo "                     cat $KEY_FILE | base64 | pbcopy   (copies to clipboard)"
else
  echo "                     cat $KEY_FILE | base64"
fi
echo ""
echo "  DATABASE_URL    →  your Neon/Supabase connection string, e.g.:"
echo "                     postgresql+asyncpg://user:pass@ep-xxx.us-east-2.aws.neon.tech/sfm?sslmode=require"
echo ""
echo "  Get a free Postgres DB at: https://neon.tech"
echo ""
echo "  ⚠  Keep $KEY_FILE secret — do NOT commit it to git."
echo ""
