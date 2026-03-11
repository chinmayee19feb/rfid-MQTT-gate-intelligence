"""
AI Layer Configuration
=======================
Settings for the MQTT connection, Claude API, and anomaly detection timing.
"""

import os

# ---------------------------------------------------------------------------
# MQTT Broker connection
# ---------------------------------------------------------------------------
# The AI layer connects to the same MQTT broker as the middleware.
# It SUBSCRIBES to the uplink topic to listen for incoming tag events.
MQTT_BROKER_HOST = "localhost"
MQTT_BROKER_PORT = 1883

# Topic where the middleware publishes all RFID events
MQTT_UPLINK_TOPIC = "Intellidb/rfid/gr/uplink"

# Topic prefix for publishing AI alerts back to specific gate readers
MQTT_DOWNLINK_PREFIX = "Intellidb/rfid/gr/downlink"

# Topic specifically for AI-generated alerts (so dashboards can subscribe)
MQTT_AI_ALERT_TOPIC = "Intellidb/rfid/ai/alerts"

# ---------------------------------------------------------------------------
# Claude API
# ---------------------------------------------------------------------------
# The API key is read from the environment variable we set up in ~/.bashrc
# This keeps the key out of your code (safe for GitHub).
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# We use Haiku — it's the cheapest and fastest model.
# Perfect for real-time anomaly detection where speed matters.
# Cost: roughly $0.001 per analysis (fractions of a cent).
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

# Maximum tokens Claude can use in its response.
# 1024 is plenty for an anomaly report.
CLAUDE_MAX_TOKENS = 1024

# ---------------------------------------------------------------------------
# Anomaly detection timing
# ---------------------------------------------------------------------------
# How often to run anomaly detection (in seconds).
# Every 60 seconds, the AI layer sends accumulated events to Claude.
ANALYSIS_INTERVAL_SECONDS = 60

# OR trigger analysis after this many tag events, whichever comes first.
ANALYSIS_EVENT_THRESHOLD = 10

# How many recent events to keep in memory for analysis.
# Older events get dropped to keep the analysis focused.
MAX_EVENTS_IN_MEMORY = 100

# ---------------------------------------------------------------------------
# Demo mode overrides
# ---------------------------------------------------------------------------
# In demo mode, we analyze more frequently for faster feedback.
DEMO_ANALYSIS_INTERVAL_SECONDS = 30
DEMO_ANALYSIS_EVENT_THRESHOLD = 5