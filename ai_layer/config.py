"""
AI Layer Configuration
=======================
Settings for MQTT, Claude via Bedrock, and anomaly detection timing.
"""

import os

# ---------------------------------------------------------------------------
# MQTT Broker connection
# ---------------------------------------------------------------------------
MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "localhost")
MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))

# MQTT credentials for the AI service
MQTT_USER = os.getenv("MQTT_AI_USER", "")
MQTT_PASS = os.getenv("MQTT_AI_PASS", "")

# Topic where the middleware publishes all RFID events
MQTT_UPLINK_TOPIC = "Intellidb/rfid/gr/uplink"

# Topic prefix for publishing AI alerts back to specific gate readers
MQTT_DOWNLINK_PREFIX = "Intellidb/rfid/gr/downlink"

# Topic specifically for AI-generated alerts (so dashboards can subscribe)
MQTT_AI_ALERT_TOPIC = "Intellidb/rfid/ai/alerts"

# ---------------------------------------------------------------------------
# Claude AI — via Amazon Bedrock
# ---------------------------------------------------------------------------
# Which method to use: "bedrock" (AWS-native) or "direct" (api.anthropic.com)
# Bedrock uses IAM role — no API key needed on EC2
# Direct uses ANTHROPIC_API_KEY — needed for local development
AI_PROVIDER = os.getenv("AI_PROVIDER", "bedrock")

# Bedrock settings
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")

# Direct API settings (fallback for local dev without AWS credentials)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
DIRECT_MODEL = "claude-haiku-4-5-20251001"

# Shared settings
CLAUDE_MAX_TOKENS = 1024

# ---------------------------------------------------------------------------
# Anomaly detection timing
# ---------------------------------------------------------------------------
ANALYSIS_INTERVAL_SECONDS = 60
ANALYSIS_EVENT_THRESHOLD = 10
MAX_EVENTS_IN_MEMORY = 100

# ---------------------------------------------------------------------------
# Demo mode overrides
# ---------------------------------------------------------------------------
DEMO_ANALYSIS_INTERVAL_SECONDS = 30
DEMO_ANALYSIS_EVENT_THRESHOLD = 5