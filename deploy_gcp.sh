#!/usr/bin/env bash
# =====================================================================
# Phase L12 — GCP Cloud Run & Firebase Hosting Automated Deployment Script
# Cyclone Twin — Critical Access Restoration Engine
# =====================================================================
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-cyclone-twin-gcc}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="${CLOUD_RUN_SERVICE:-cyclone-twin-backend}"
IMAGE_TAG="gcr.io/${PROJECT_ID}/${SERVICE_NAME}:latest"

echo "================================================================="
echo "Cyclone Twin Phase L12 — Google Cloud Deployment Engine"
echo "Project ID: ${PROJECT_ID}"
echo "Region:     ${REGION}"
echo "Service:    ${SERVICE_NAME}"
echo "================================================================="

usage() {
    echo "Usage: $0 [check|build|deploy-backend|deploy-frontend|deploy-all]"
    echo ""
    echo "Commands:"
    echo "  check            Validate local CLI tools, Docker, and environment"
    echo "  build            Build container image locally via Docker"
    echo "  deploy-backend   Build and deploy FastAPI backend to Google Cloud Run"
    echo "  deploy-frontend  Build Vite frontend and deploy to Firebase Hosting"
    echo "  deploy-all       Execute complete full-stack deployment"
    exit 1
}

check_environment() {
    echo "--> [1/4] Checking required tools..."
    command -v gcloud >/dev/null 2>&1 || { echo "ERROR: gcloud CLI is not installed."; exit 1; }
    command -v firebase >/dev/null 2>&1 || { echo "WARNING: firebase CLI is not installed in PATH (needed for frontend deploy)."; }
    command -v docker >/dev/null 2>&1 || { echo "WARNING: docker CLI is not installed locally."; }
    
    echo "--> [2/4] Verifying gcloud authentication..."
    CURRENT_ACCOUNT=$(gcloud config get-value account 2>/dev/null || echo "unauthenticated")
    echo "Active gcloud account: ${CURRENT_ACCOUNT}"
    
    echo "--> [3/4] Verifying project setting..."
    gcloud config set project "${PROJECT_ID}" --quiet || true
    
    echo "--> [4/4] Environment check completed successfully."
}

build_docker() {
    echo "--> Building container image locally: ${IMAGE_TAG}"
    docker build -t "${IMAGE_TAG}" .
    echo "--> Docker build completed successfully."
}

deploy_backend() {
    echo "--> Deploying backend container to Google Cloud Run..."
    gcloud builds submit --tag "${IMAGE_TAG}" .
    gcloud run deploy "${SERVICE_NAME}" \
        --image "${IMAGE_TAG}" \
        --platform managed \
        --region "${REGION}" \
        --allow-unauthenticated \
        --set-env-vars "GCP_PROJECT_ID=${PROJECT_ID},GCS_BUCKET_NAME=${PROJECT_ID}-media,FIRESTORE_COLLECTION=disaster_states,BIGQUERY_DATASET=telemetry" \
        --port 8080
    
    CLOUD_RUN_URL=$(gcloud run services describe "${SERVICE_NAME}" --platform managed --region "${REGION}" --format 'value(status.url)' 2>/dev/null || echo "")
    echo "==> Backend Cloud Run Service live at: ${CLOUD_RUN_URL}"
}

deploy_frontend() {
    echo "--> Building Vite frontend static bundle..."
    (cd frontend && npm run build)
    
    echo "--> Deploying to Firebase Hosting..."
    firebase deploy --only hosting --project "${PROJECT_ID}"
    echo "==> Frontend live on Firebase Hosting!"
}

case "${1:-check}" in
    check)
        check_environment
        ;;
    build)
        build_docker
        ;;
    deploy-backend)
        check_environment
        deploy_backend
        ;;
    deploy-frontend)
        deploy_frontend
        ;;
    deploy-all)
        check_environment
        deploy_backend
        deploy_frontend
        ;;
    *)
        usage
        ;;
esac

echo "================================================================="
echo "Phase L12 Deployment process execution completed."
echo "================================================================="
