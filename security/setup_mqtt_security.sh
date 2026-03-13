#!/bin/bash
# ============================================================
# MQTT Security Setup Script
# RFID Gate Intelligence Platform
# ============================================================
# This script:
#   1. Generates secure random passwords for each MQTT user
#   2. Creates a hashed password file for Mosquitto
#   3. Creates a .env file with all secrets
#   4. Starts a secured Mosquitto container
#
# Usage:
#   chmod +x setup_mqtt_security.sh
#   ./setup_mqtt_security.sh
# ============================================================

set -e  # Stop on any error

# Colours for output
GREEN='\033[92m'
YELLOW='\033[93m'
RED='\033[91m'
CYAN='\033[96m'
RESET='\033[0m'

echo ""
echo "============================================================"
echo -e "  ${CYAN}MQTT Security Setup${RESET}"
echo "  RFID Gate Intelligence Platform"
echo "============================================================"
echo ""

# ----------------------------------------------------------
# Step 1: Generate random passwords
# ----------------------------------------------------------
echo -e "${YELLOW}[1/4]${RESET} Generating secure passwords..."

# Generate 20-character random passwords using openssl
MQTT_MIDDLEWARE_PASS=$(openssl rand -base64 20 | tr -dc 'a-zA-Z0-9' | head -c 20)
MQTT_AI_PASS=$(openssl rand -base64 20 | tr -dc 'a-zA-Z0-9' | head -c 20)
MQTT_DASHBOARD_PASS=$(openssl rand -base64 20 | tr -dc 'a-zA-Z0-9' | head -c 20)
MIDDLEWARE_API_KEY=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 32)

echo -e "  ✓ middleware_svc password generated"
echo -e "  ✓ ai_svc password generated"
echo -e "  ✓ dashboard_svc password generated"
echo -e "  ✓ middleware API key generated"

# ----------------------------------------------------------
# Step 2: Create the Mosquitto password file
# ----------------------------------------------------------
echo ""
echo -e "${YELLOW}[2/4]${RESET} Creating Mosquitto password file..."

# Get the project root directory (parent of security/)
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MOSQUITTO_DIR="${PROJECT_ROOT}/security/mosquitto"
PASSWD_FILE="${MOSQUITTO_DIR}/passwd"

# Stop any existing mosquitto container
docker stop mosquitto-secure 2>/dev/null || true
docker rm mosquitto-secure 2>/dev/null || true

# Use a temporary Mosquitto container to hash passwords
# (mosquitto_passwd hashes with PBKDF2-SHA512 — very secure)
docker run --rm -v "${MOSQUITTO_DIR}:/mosquitto/config" eclipse-mosquitto \
    mosquitto_passwd -b -c /mosquitto/config/passwd middleware_svc "$MQTT_MIDDLEWARE_PASS"

docker run --rm -v "${MOSQUITTO_DIR}:/mosquitto/config" eclipse-mosquitto \
    mosquitto_passwd -b /mosquitto/config/passwd ai_svc "$MQTT_AI_PASS"

docker run --rm -v "${MOSQUITTO_DIR}:/mosquitto/config" eclipse-mosquitto \
    mosquitto_passwd -b /mosquitto/config/passwd dashboard_svc "$MQTT_DASHBOARD_PASS"

echo -e "  ✓ Password file created at: ${MOSQUITTO_DIR}/passwd"

# ----------------------------------------------------------
# Step 3: Create the .env file
# ----------------------------------------------------------
echo ""
echo -e "${YELLOW}[3/4]${RESET} Creating .env file with all secrets..."

ENV_FILE="${PROJECT_ROOT}/.env"

cat > "$ENV_FILE" << EOF
# ============================================================
# RFID Gate Intelligence Platform — Environment Secrets
# ============================================================
# This file contains ALL secrets for the project.
# NEVER commit this to Git! (it's in .gitignore)
# ============================================================

# --- MQTT Broker ---
MQTT_BROKER_HOST=localhost
MQTT_BROKER_PORT=1883

# --- MQTT User: middleware_svc ---
MQTT_MIDDLEWARE_USER=middleware_svc
MQTT_MIDDLEWARE_PASS=${MQTT_MIDDLEWARE_PASS}

# --- MQTT User: ai_svc ---
MQTT_AI_USER=ai_svc
MQTT_AI_PASS=${MQTT_AI_PASS}

# --- MQTT User: dashboard_svc ---
MQTT_DASHBOARD_USER=dashboard_svc
MQTT_DASHBOARD_PASS=${MQTT_DASHBOARD_PASS}

# --- Middleware API Key ---
# Simulators and readers must include this in their HTTP headers
MIDDLEWARE_API_KEY=${MIDDLEWARE_API_KEY}

# --- Claude API ---
# Your Anthropic API key (already set in ~/.bashrc, copied here for reference)
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-your-key-here}
EOF

echo -e "  ✓ .env file created at: ${ENV_FILE}"

# ----------------------------------------------------------
# Step 4: Make sure .env is in .gitignore
# ----------------------------------------------------------
echo ""
echo -e "${YELLOW}[4/4]${RESET} Checking .gitignore..."

GITIGNORE="${PROJECT_ROOT}/.gitignore"

if ! grep -q "^\.env$" "$GITIGNORE" 2>/dev/null; then
    echo "" >> "$GITIGNORE"
    echo "# Secrets — never commit" >> "$GITIGNORE"
    echo ".env" >> "$GITIGNORE"
    echo "security/mosquitto/passwd" >> "$GITIGNORE"
    echo -e "  ✓ Added .env and passwd to .gitignore"
else
    echo -e "  ✓ .env already in .gitignore"
fi

# ----------------------------------------------------------
# Summary
# ----------------------------------------------------------
echo ""
echo "============================================================"
echo -e "  ${GREEN}✓ Security setup complete!${RESET}"
echo "============================================================"
echo ""
echo "  Files created:"
echo "    • security/mosquitto/passwd  (hashed passwords)"
echo "    • .env                       (all secrets)"
echo ""
echo "  MQTT Users:"
echo "    • middleware_svc  → used by the Flask middleware"
echo "    • ai_svc         → used by the AI anomaly detector"
echo "    • dashboard_svc  → used by Grafana (read-only)"
echo ""
echo -e "  ${YELLOW}Next step:${RESET} Start the secured Mosquitto broker with:"
echo "    docker run -d --name mosquitto-secure \\"
echo "      -p 1883:1883 \\"
echo "      -v ${MOSQUITTO_DIR}/mosquitto.conf:/mosquitto/config/mosquitto.conf \\"
echo "      -v ${MOSQUITTO_DIR}/passwd:/mosquitto/config/passwd \\"
echo "      -v ${MOSQUITTO_DIR}/acl:/mosquitto/config/acl \\"
echo "      eclipse-mosquitto"
echo ""
echo -e "  ${RED}IMPORTANT:${RESET} Never commit .env or passwd to Git!"
echo ""