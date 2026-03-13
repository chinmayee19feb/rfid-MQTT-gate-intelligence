# ============================================================
# FLASK MIDDLEWARE - Main Application
# Listens on port 4501 for HTTP POST from CTAgent
# Routes packets to correct handler based on TYP field
# Now with API key auth + Prometheus metrics
# ============================================================

import json
import logging
import os
import time
from functools import wraps

import boto3
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from mqtt_client import mqtt_client, UPLINK_TOPIC, DOWNLINK_TOPIC
from packet_handler import (
    validate_health_packet,
    validate_tag_packet,
    format_health_ack,
    format_tag_ack,
    extract_direction
)
from metrics import (
    rfid_tags_total,
    rfid_health_packets_total,
    rfid_errors_total,
    rfid_success_total,
    rfid_auth_rejections_total,
    rfid_request_duration_seconds,
    rfid_antennas_down,
    mqtt_connected,
)

# Load .env file
load_dotenv()

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)

# API key for authenticating HTTP requests
MIDDLEWARE_API_KEY = os.getenv("MIDDLEWARE_API_KEY", "")

# DynamoDB tables
dynamodb     = boto3.resource('dynamodb', region_name=os.getenv("AWS_REGION", "us-east-1"))
rfid_table   = dynamodb.Table(os.getenv("DYNAMODB_RFID_TABLE",   "rfid-gate-intelligence-rfid-events"))
health_table = dynamodb.Table(os.getenv("DYNAMODB_HEALTH_TABLE", "rfid-gate-intelligence-health-events"))


# ---- API KEY DECORATOR --------------------------------------

def require_api_key(f):
    """Check for valid API key in X-API-Key header."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not MIDDLEWARE_API_KEY:
            logger.warning("API key not configured — skipping auth (dev mode)")
            return f(*args, **kwargs)

        provided_key = request.headers.get("X-API-Key", "")

        if not provided_key:
            logger.warning(f"Rejected request — no API key from {request.remote_addr}")
            rfid_auth_rejections_total.labels(reason="missing").inc()
            return jsonify({
                "error": "Missing API key",
                "hint": "Include X-API-Key header in your request"
            }), 401

        if provided_key != MIDDLEWARE_API_KEY:
            logger.warning(f"Rejected request — invalid API key from {request.remote_addr}")
            rfid_auth_rejections_total.labels(reason="invalid").inc()
            return jsonify({"error": "Invalid API key"}), 403

        return f(*args, **kwargs)
    return decorated


# ---- ROUTES -------------------------------------------------

@app.route("/health", methods=["GET"])
def health_check():
    """Health check - no API key needed."""
    # Update MQTT gauge
    mqtt_connected.set(1 if mqtt_client.connected else 0)
    return jsonify({
        "status":         "ok",
        "mqtt_connected": mqtt_client.connected,
        "auth_enabled":   bool(MIDDLEWARE_API_KEY)
    }), 200


@app.route("/metrics", methods=["GET"])
def metrics():
    """
    Prometheus metrics endpoint.
    Prometheus scrapes this every 15 seconds to collect data.
    """
    # Update MQTT gauge on every scrape
    mqtt_connected.set(1 if mqtt_client.connected else 0)
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


@app.route("/rfid/data", methods=["POST"])
@require_api_key
def receive_rfid_data():
    """Main endpoint - receives ALL packets from CTAgent."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON body"}), 400

        packet_type = data.get("TYP", "").strip()
        logger.info(f"Received packet: {packet_type}")

        # Start timing the request
        start_time = time.time()

        if packet_type == "GRHBPKT":
            result = handle_health_packet(data)
        elif packet_type == "GRTAGDATA":
            result = handle_tag_packet(data)
        else:
            return jsonify({
                "error":    "Unknown packet type",
                "received": packet_type,
                "expected": ["GRHBPKT", "GRTAGDATA"]
            }), 400

        # Record how long the request took
        duration = time.time() - start_time
        rfid_request_duration_seconds.labels(packet_type=packet_type).observe(duration)

        return result

    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({"error": str(e)}), 500


def handle_health_packet(data):
    """Handles GRHBPKT packets."""
    is_valid, error_msg = validate_health_packet(data)
    if not is_valid:
        logger.error(f"Validation failed: {error_msg}")
        rfid_errors_total.labels(error_code="4001").inc()
        ack = format_health_ack(
            data.get("GATE_READER_ID", "unknown"),
            data.get("TIMESTAMP", "0"),
            error_code=4001
        )
        mqtt_client.publish(f"{DOWNLINK_TOPIC}/{data.get('GATE_READER_ID', 'unknown')}", ack)
        return jsonify(ack), 400

    gate_reader_id = data["GATE_READER_ID"]
    timestamp      = data["TIMESTAMP"]

    # Track health packet metric
    rfid_health_packets_total.labels(gate_reader_id=gate_reader_id).inc()

    # Track antenna status
    antennas = data.get("HLTH_STAT_REQ", [])
    down_count = sum(1 for a in antennas if list(a.values())[0] == "N")
    rfid_antennas_down.labels(gate_reader_id=gate_reader_id).set(down_count)

    # Store in DynamoDB
    try:
        health_table.put_item(Item={
            "gate_reader_id":     gate_reader_id,
            "timestamp":          timestamp,
            "sample_periodicity": str(data.get("SAMPLE_PERIODICITY", 15)),
            "antenna_status":     json.dumps(data.get("HLTH_STAT_REQ", []))
        })
        error_code = 4000
        rfid_success_total.labels(packet_type="GRHBPKT").inc()
    except Exception as e:
        logger.error(f"DynamoDB error: {e}")
        error_code = 4002
        rfid_errors_total.labels(error_code="4002").inc()

    # Publish uplink + downlink ACK
    mqtt_client.publish(UPLINK_TOPIC, data)
    ack = format_health_ack(gate_reader_id, timestamp, error_code)
    mqtt_client.publish(f"{DOWNLINK_TOPIC}/{gate_reader_id}", ack)

    return jsonify(ack), 200


def handle_tag_packet(data):
    """Handles GRTAGDATA packets."""
    is_valid, error_msg = validate_tag_packet(data)
    if not is_valid:
        logger.error(f"Validation failed: {error_msg}")
        rfid_errors_total.labels(error_code="4001").inc()
        ack = format_tag_ack(
            data.get("GATE_READER_ID", "unknown"),
            data.get("READPOINT", "unknown"),
            data.get("EVENTTIME", "0"),
            error_code=4001
        )
        mqtt_client.publish(f"{DOWNLINK_TOPIC}/{data.get('GATE_READER_ID', 'unknown')}", ack)
        return jsonify(ack), 400

    gate_reader_id = data["GATE_READER_ID"]
    readpoint      = data["READPOINT"]
    timestamp      = data["EVENTTIME"]
    direction      = extract_direction(readpoint)

    # Track tag scan metric
    rfid_tags_total.labels(gate_reader_id=gate_reader_id, direction=direction).inc()

    # Store in DynamoDB
    try:
        rfid_table.put_item(Item={
            "gate_reader_id": gate_reader_id,
            "timestamp":      timestamp,
            "readpoint":      readpoint,
            "direction":      direction,
            "epc_list":       json.dumps(data.get("FILE_EPCList", []))
        })
        error_code = 4000
        rfid_success_total.labels(packet_type="GRTAGDATA").inc()
    except Exception as e:
        logger.error(f"DynamoDB error: {e}")
        error_code = 4002
        rfid_errors_total.labels(error_code="4002").inc()

    # Publish uplink + downlink ACK
    mqtt_client.publish(UPLINK_TOPIC, data)
    ack = format_tag_ack(gate_reader_id, readpoint, timestamp, error_code)
    mqtt_client.publish(f"{DOWNLINK_TOPIC}/{gate_reader_id}", ack)

    return jsonify(ack), 200


# ---- STARTUP ------------------------------------------------

if __name__ == "__main__":
    logger.info("Starting RFID Gate Intelligence Middleware...")

    if MIDDLEWARE_API_KEY:
        logger.info("API key authentication: ENABLED")
    else:
        logger.warning("API key authentication: DISABLED (no MIDDLEWARE_API_KEY set)")

    logger.info("Prometheus metrics: ENABLED on /metrics")

    mqtt_client.connect()
    port = int(os.getenv("FLASK_PORT", 4501))
    app.run(host="0.0.0.0", port=port, debug=False)