"""
Prometheus Metrics
===================
Defines all the counters and histograms that track middleware activity.

Think of each metric like a counter on a dashboard:
- Every time a tag is scanned → rfid_tags_total goes up by 1
- Every time a health packet arrives → rfid_health_packets_total goes up by 1
- Every time there's an error → rfid_errors_total goes up by 1
- Every request → rfid_request_duration_seconds records how long it took

Prometheus scrapes these every 15 seconds from the /metrics endpoint.
Grafana then draws charts from this data.
"""

from prometheus_client import Counter, Histogram, Gauge, Info

# ---------------------------------------------------------------------------
# Counters — go up by 1 every time something happens
# ---------------------------------------------------------------------------

# Total tag scans, labeled by gate reader and direction (IN/OUT)
rfid_tags_total = Counter(
    "rfid_tags_total",
    "Total RFID tag scan events received",
    ["gate_reader_id", "direction"]
)

# Total health packets, labeled by gate reader
rfid_health_packets_total = Counter(
    "rfid_health_packets_total",
    "Total health status packets received",
    ["gate_reader_id"]
)

# Total errors by type (4001=validation, 4002=DB, 4010=unknown)
rfid_errors_total = Counter(
    "rfid_errors_total",
    "Total error responses sent",
    ["error_code"]
)

# Total successful ACKs (error code 4000)
rfid_success_total = Counter(
    "rfid_success_total",
    "Total successful ACK responses (4000)",
    ["packet_type"]
)

# Total API key rejections
rfid_auth_rejections_total = Counter(
    "rfid_auth_rejections_total",
    "Total requests rejected due to missing or invalid API key",
    ["reason"]
)

# Total AI alerts published
rfid_ai_alerts_total = Counter(
    "rfid_ai_alerts_total",
    "Total AI anomaly alerts published to MQTT",
    ["alert_type", "severity"]
)

# ---------------------------------------------------------------------------
# Histograms — track how long things take
# ---------------------------------------------------------------------------

# How long each request takes to process (in seconds)
rfid_request_duration_seconds = Histogram(
    "rfid_request_duration_seconds",
    "Time to process each RFID request",
    ["packet_type"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

# ---------------------------------------------------------------------------
# Gauges — current value (can go up or down)
# ---------------------------------------------------------------------------

# Number of antennas currently down across all readers
rfid_antennas_down = Gauge(
    "rfid_antennas_down",
    "Number of antennas currently reporting N (down)",
    ["gate_reader_id"]
)

# MQTT connection status (1=connected, 0=disconnected)
mqtt_connected = Gauge(
    "mqtt_connected",
    "MQTT broker connection status (1=connected, 0=disconnected)"
)

# ---------------------------------------------------------------------------
# Info — static labels about the system
# ---------------------------------------------------------------------------

app_info = Info(
    "rfid_middleware",
    "RFID Gate Intelligence Middleware information"
)
app_info.info({
    "version": "1.0.0",
    "project": "rfid-gate-intelligence",
})