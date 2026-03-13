"""
AI Layer Configuration
=======================
Settings for the MQTT connection, Claude API, and anomaly detection timing.
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
# Claude API
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
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