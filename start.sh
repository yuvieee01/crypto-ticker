#!/bin/bash

# ──────────────────────────────────────────────────────────────────────────────
# start.sh — Orchestration script for Crypto Ticker Stack
# ──────────────────────────────────────────────────────────────────────────────

# Color formatting codes
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}🚀 Initializing the Crypto Sentiment & Price Ticker stack...${NC}"

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    echo -e "${RED}❌ Error: Docker is not running. Please launch Docker Desktop and try again.${NC}"
    exit 1
fi

# Build and start services via Docker Compose
echo -e "${CYAN}📦 Building and spinning up containers...${NC}"
if ! docker compose up --build -d; then
    echo -e "${RED}❌ Error: Docker Compose failed to spin up the services.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Containers started successfully!${NC}"
echo -e "${CYAN}⏳ Waiting for Grafana dashboard to become healthy and load pre-configured assets...${NC}"

# Poll Grafana health API until it responds with HTTP 200
GRAFANA_URL="http://localhost:3000"
MAX_ATTEMPTS=30
ATTEMPT=1
HEALTHY=false

while [ $ATTEMPT -le $MAX_ATTEMPTS ]; do
    HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GRAFANA_URL/api/health" || true)
    
    if [ "$HTTP_STATUS" = "200" ]; then
        HEALTHY=true
        break
    fi
    
    echo -e "   [Attempt $ATTEMPT/$MAX_ATTEMPTS] Grafana is still starting (HTTP $HTTP_STATUS)..."
    sleep 2
    ATTEMPT=$((ATTEMPT + 1))
done

if [ "$HEALTHY" = true ]; then
    echo -e "${GREEN}✅ Grafana is healthy and online!${NC}"
    
    # Wait an extra 2 seconds for dashboard provisioning to finalize completely
    sleep 2
    
    # Open the pre-configured dashboard directly in the user's browser
    DASHBOARD_URL="http://localhost:3000/d/crypto-sentiment-dashboard"
    echo -e "${GREEN}🌐 Opening Grafana dashboard in your default browser...${NC}"
    open "$DASHBOARD_URL"
    
    # Print status summary
    echo -e "\n${GREEN}🎉 Stack is fully operational! Here are your local entrypoints:${NC}"
    echo -e "┌──────────────────────────────┬─────────────────────────────────────────────────┐"
    echo -e "│ Service                      │ Local URL                                       │"
    echo -e "├──────────────────────────────┼─────────────────────────────────────────────────┤"
    echo -e "│ ${CYAN}Grafana Dashboard${NC}            │ ${GREEN}$DASHBOARD_URL${NC} │"
    echo -e "│ ${CYAN}FastAPI Swagger Docs${NC}         │ ${GREEN}http://localhost:8000/docs${NC}                     │"
    echo -e "│ ${CYAN}FastAPI Raw Metrics${NC}          │ ${GREEN}http://localhost:8000/metrics${NC}                  │"
    echo -e "│ ${CYAN}Prometheus Scraper UI${NC}        │ ${GREEN}http://localhost:9090/targets${NC}                  │"
    echo -e "└──────────────────────────────┴─────────────────────────────────────────────────┘"
    echo -e "${YELLOW}💡 Tip: Use 'docker compose logs -f' to watch active price & sentiment scraping loops.${NC}\n"
else
    echo -e "${RED}❌ Warning: Grafana did not become healthy within the timeout period.${NC}"
    echo -e "You can try accessing it manually at: http://localhost:3000/d/crypto-sentiment-dashboard"
fi
