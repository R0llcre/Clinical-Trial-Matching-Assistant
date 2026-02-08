#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

AZ_LOCATION="${AZ_LOCATION:-eastus}"
AZ_RESOURCE_GROUP="${AZ_RESOURCE_GROUP:-rg-ctmatch-preview}"
AZ_ACR_NAME="${AZ_ACR_NAME:-acrctmatchpreview}"
AZ_CONTAINERAPPS_ENV="${AZ_CONTAINERAPPS_ENV:-cae-ctmatch-preview}"

AZ_API_APP="${AZ_API_APP:-ca-api-preview}"
AZ_WEB_APP="${AZ_WEB_APP:-ca-web-preview}"
AZ_WORKER_APP="${AZ_WORKER_APP:-ca-worker-preview}"

AZ_PG_SERVER="${AZ_PG_SERVER:-pg-ctmatch-preview}"
AZ_PG_DB="${AZ_PG_DB:-ctmatch}"
AZ_PG_USER="${AZ_PG_USER:-ctmatchadmin}"
AZ_PG_PASSWORD="${AZ_PG_PASSWORD:-}"

AZ_REDIS_NAME="${AZ_REDIS_NAME:-redis-ctmatch-preview}"
IMAGE_TAG="${IMAGE_TAG:-$(date +%Y%m%d%H%M%S)}"

SYNC_CONDITION="${SYNC_CONDITION:-cancer}"
SYNC_PAGE_LIMIT="${SYNC_PAGE_LIMIT:-1}"
SYNC_INTERVAL_SECONDS="${SYNC_INTERVAL_SECONDS:-3600}"

if ! command -v az >/dev/null 2>&1; then
  echo "az CLI not found. Install Azure CLI first."
  exit 1
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl not found. Install openssl first."
  exit 1
fi

if ! az account show >/dev/null 2>&1; then
  echo "Not logged in to Azure. Run: az login"
  exit 1
fi

if [[ -z "${AZ_PG_PASSWORD}" ]]; then
  AZ_PG_PASSWORD="$(openssl rand -base64 32 | tr -dc 'A-Za-z0-9' | head -c 24)"
  echo "Generated AZ_PG_PASSWORD for this deployment run."
fi

echo "Using settings:"
echo "  AZ_LOCATION=${AZ_LOCATION}"
echo "  AZ_RESOURCE_GROUP=${AZ_RESOURCE_GROUP}"
echo "  AZ_ACR_NAME=${AZ_ACR_NAME}"
echo "  AZ_CONTAINERAPPS_ENV=${AZ_CONTAINERAPPS_ENV}"
echo "  AZ_API_APP=${AZ_API_APP}"
echo "  AZ_WEB_APP=${AZ_WEB_APP}"
echo "  AZ_WORKER_APP=${AZ_WORKER_APP}"
echo "  AZ_PG_SERVER=${AZ_PG_SERVER}"
echo "  AZ_PG_DB=${AZ_PG_DB}"
echo "  AZ_PG_USER=${AZ_PG_USER}"
echo "  AZ_REDIS_NAME=${AZ_REDIS_NAME}"
echo "  IMAGE_TAG=${IMAGE_TAG}"

echo "Ensuring required Azure extension..."
az extension add --name containerapp --upgrade >/dev/null

echo "Creating resource group..."
az group create \
  --name "${AZ_RESOURCE_GROUP}" \
  --location "${AZ_LOCATION}" \
  --output none

echo "Ensuring ACR exists..."
if ! az acr show --name "${AZ_ACR_NAME}" --resource-group "${AZ_RESOURCE_GROUP}" >/dev/null 2>&1; then
  az acr create \
    --name "${AZ_ACR_NAME}" \
    --resource-group "${AZ_RESOURCE_GROUP}" \
    --sku Basic \
    --admin-enabled true \
    --location "${AZ_LOCATION}" \
    --output none
fi

ACR_LOGIN_SERVER="$(az acr show --name "${AZ_ACR_NAME}" --resource-group "${AZ_RESOURCE_GROUP}" --query loginServer -o tsv)"
ACR_USERNAME="$(az acr credential show --name "${AZ_ACR_NAME}" --query username -o tsv)"
ACR_PASSWORD="$(az acr credential show --name "${AZ_ACR_NAME}" --query passwords[0].value -o tsv)"

echo "Ensuring PostgreSQL flexible server exists..."
if ! az postgres flexible-server show --name "${AZ_PG_SERVER}" --resource-group "${AZ_RESOURCE_GROUP}" >/dev/null 2>&1; then
  az postgres flexible-server create \
    --name "${AZ_PG_SERVER}" \
    --resource-group "${AZ_RESOURCE_GROUP}" \
    --location "${AZ_LOCATION}" \
    --admin-user "${AZ_PG_USER}" \
    --admin-password "${AZ_PG_PASSWORD}" \
    --sku-name Standard_B1ms \
    --tier Burstable \
    --storage-size 32 \
    --version 16 \
    --public-access All \
    --yes \
    --output none
fi
if ! az postgres flexible-server db show \
  --server-name "${AZ_PG_SERVER}" \
  --resource-group "${AZ_RESOURCE_GROUP}" \
  --database-name "${AZ_PG_DB}" >/dev/null 2>&1; then
  az postgres flexible-server db create \
    --server-name "${AZ_PG_SERVER}" \
    --resource-group "${AZ_RESOURCE_GROUP}" \
    --database-name "${AZ_PG_DB}" \
    --output none
fi

PG_FQDN="$(az postgres flexible-server show --name "${AZ_PG_SERVER}" --resource-group "${AZ_RESOURCE_GROUP}" --query fullyQualifiedDomainName -o tsv)"
DATABASE_URL="postgresql://${AZ_PG_USER}:${AZ_PG_PASSWORD}@${PG_FQDN}:5432/${AZ_PG_DB}?sslmode=require"

echo "Ensuring Redis exists..."
if ! az redis show --name "${AZ_REDIS_NAME}" --resource-group "${AZ_RESOURCE_GROUP}" >/dev/null 2>&1; then
  az redis create \
    --name "${AZ_REDIS_NAME}" \
    --resource-group "${AZ_RESOURCE_GROUP}" \
    --location "${AZ_LOCATION}" \
    --sku Basic \
    --vm-size c0 \
    --output none
fi
REDIS_HOST="$(az redis show --name "${AZ_REDIS_NAME}" --resource-group "${AZ_RESOURCE_GROUP}" --query hostName -o tsv)"
REDIS_KEY="$(az redis list-keys --name "${AZ_REDIS_NAME}" --resource-group "${AZ_RESOURCE_GROUP}" --query primaryKey -o tsv)"
REDIS_URL="rediss://:${REDIS_KEY}@${REDIS_HOST}:6380/0"

echo "Ensuring Container Apps environment exists..."
if ! az containerapp env show --name "${AZ_CONTAINERAPPS_ENV}" --resource-group "${AZ_RESOURCE_GROUP}" >/dev/null 2>&1; then
  az containerapp env create \
    --name "${AZ_CONTAINERAPPS_ENV}" \
    --resource-group "${AZ_RESOURCE_GROUP}" \
    --location "${AZ_LOCATION}" \
    --output none
fi

echo "Building API image in ACR..."
az acr build \
  --registry "${AZ_ACR_NAME}" \
  --image "ctmatch-api:${IMAGE_TAG}" \
  --file "apps/api/Dockerfile" \
  "${ROOT_DIR}/apps/api" \
  --output none

API_IMAGE="${ACR_LOGIN_SERVER}/ctmatch-api:${IMAGE_TAG}"
JWT_SECRET="$(openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | head -c 40)"

echo "Deploying API Container App..."
az containerapp up \
  --name "${AZ_API_APP}" \
  --resource-group "${AZ_RESOURCE_GROUP}" \
  --environment "${AZ_CONTAINERAPPS_ENV}" \
  --image "${API_IMAGE}" \
  --ingress external \
  --target-port 8000 \
  --registry-server "${ACR_LOGIN_SERVER}" \
  --registry-username "${ACR_USERNAME}" \
  --registry-password "${ACR_PASSWORD}" \
  --env-vars \
    DATABASE_URL="${DATABASE_URL}" \
    REDIS_URL="${REDIS_URL}" \
    CTGOV_BASE_URL="https://clinicaltrials.gov/api/v2" \
    JWT_SECRET="${JWT_SECRET}" \
    JWT_ALGORITHM="HS256" \
    ALLOWED_ORIGINS="https://placeholder.invalid"

API_FQDN="$(az containerapp show --name "${AZ_API_APP}" --resource-group "${AZ_RESOURCE_GROUP}" --query properties.configuration.ingress.fqdn -o tsv)"
API_BASE_URL="https://${API_FQDN}"

echo "Building Web image in ACR (NEXT_PUBLIC_API_BASE=${API_BASE_URL})..."
az acr build \
  --registry "${AZ_ACR_NAME}" \
  --image "ctmatch-web:${IMAGE_TAG}" \
  --file "apps/web/Dockerfile" \
  --build-arg "NEXT_PUBLIC_API_BASE=${API_BASE_URL}" \
  "${ROOT_DIR}/apps/web" \
  --output none

WEB_IMAGE="${ACR_LOGIN_SERVER}/ctmatch-web:${IMAGE_TAG}"

echo "Deploying Web Container App..."
az containerapp up \
  --name "${AZ_WEB_APP}" \
  --resource-group "${AZ_RESOURCE_GROUP}" \
  --environment "${AZ_CONTAINERAPPS_ENV}" \
  --image "${WEB_IMAGE}" \
  --ingress external \
  --target-port 3000 \
  --registry-server "${ACR_LOGIN_SERVER}" \
  --registry-username "${ACR_USERNAME}" \
  --registry-password "${ACR_PASSWORD}"

WEB_FQDN="$(az containerapp show --name "${AZ_WEB_APP}" --resource-group "${AZ_RESOURCE_GROUP}" --query properties.configuration.ingress.fqdn -o tsv)"
WEB_ORIGIN="https://${WEB_FQDN}"

echo "Updating API CORS origin to ${WEB_ORIGIN}..."
az containerapp update \
  --name "${AZ_API_APP}" \
  --resource-group "${AZ_RESOURCE_GROUP}" \
  --set-env-vars \
    DATABASE_URL="${DATABASE_URL}" \
    REDIS_URL="${REDIS_URL}" \
    CTGOV_BASE_URL="https://clinicaltrials.gov/api/v2" \
    JWT_SECRET="${JWT_SECRET}" \
    JWT_ALGORITHM="HS256" \
    ALLOWED_ORIGINS="${WEB_ORIGIN}" \
  --output none

echo "Building Worker image in ACR..."
az acr build \
  --registry "${AZ_ACR_NAME}" \
  --image "ctmatch-worker:${IMAGE_TAG}" \
  --file "apps/worker/Dockerfile" \
  "${ROOT_DIR}/apps/worker" \
  --output none

WORKER_IMAGE="${ACR_LOGIN_SERVER}/ctmatch-worker:${IMAGE_TAG}"

echo "Deploying Worker Container App..."
if az containerapp show --name "${AZ_WORKER_APP}" --resource-group "${AZ_RESOURCE_GROUP}" >/dev/null 2>&1; then
  az containerapp update \
    --name "${AZ_WORKER_APP}" \
    --resource-group "${AZ_RESOURCE_GROUP}" \
    --image "${WORKER_IMAGE}" \
    --set-env-vars \
      DATABASE_URL="${DATABASE_URL}" \
      REDIS_URL="${REDIS_URL}" \
      CTGOV_BASE_URL="https://clinicaltrials.gov/api/v2" \
      SYNC_CONDITION="${SYNC_CONDITION}" \
      SYNC_PAGE_LIMIT="${SYNC_PAGE_LIMIT}" \
      SYNC_INTERVAL_SECONDS="${SYNC_INTERVAL_SECONDS}" \
    --output none
else
  az containerapp create \
    --name "${AZ_WORKER_APP}" \
    --resource-group "${AZ_RESOURCE_GROUP}" \
    --environment "${AZ_CONTAINERAPPS_ENV}" \
    --image "${WORKER_IMAGE}" \
    --registry-server "${ACR_LOGIN_SERVER}" \
    --registry-username "${ACR_USERNAME}" \
    --registry-password "${ACR_PASSWORD}" \
    --min-replicas 1 \
    --max-replicas 1 \
    --env-vars \
      DATABASE_URL="${DATABASE_URL}" \
      REDIS_URL="${REDIS_URL}" \
      CTGOV_BASE_URL="https://clinicaltrials.gov/api/v2" \
      SYNC_CONDITION="${SYNC_CONDITION}" \
      SYNC_PAGE_LIMIT="${SYNC_PAGE_LIMIT}" \
      SYNC_INTERVAL_SECONDS="${SYNC_INTERVAL_SECONDS}" \
    --output none
fi

echo ""
echo "Deployment completed."
echo "Web URL : https://${WEB_FQDN}"
echo "API URL : https://${API_FQDN}"
echo ""
echo "Smoke checks:"
echo "  curl -fsS https://${API_FQDN}/health"
echo "  curl -fsS https://${API_FQDN}/readyz"
echo "  curl -fsS 'https://${API_FQDN}/api/trials?page=1&page_size=5'"
