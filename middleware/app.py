# ============================================================
# FLASK MIDDLEWARE - Main Application
# Listens on port 4501 for HTTP POST from CTAgent
# Routes packets to correct handler based on TYP field
# Now with API key authentication on /rfid/data
# ============================================================

import json
import logging
import os
from functools import wraps

import boto3
from dotenv import load_dotenv
from flask import Flask, request, jsonify

from mqtt_client import mqtt_client, UPLINK_TOPIC, DOWNLINK_TOPIC
from packet_handler import (
    validate_health_packet,
    validate_tag_packet,
    format_health_ack,
    format_tag_ack,
    extract_direction
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
# Read from environment variable (set in .env file)
MIDDLEWARE_API_KEY = os.getenv("MIDDLEWARE_API_KEY", "")

# DynamoDB tables
dynamodb     = boto3.resource('dynamodb', region_name=os.getenv("AWS_REGION", "us-east-1"))
rfid_table   = dynamodb.Table(os.getenv("DYNAMODB_RFID_TABLE",   "rfid-gate-intelligence-rfid-events"))
health_table = dynamodb.Table(os.getenv("DYNAMODB_HEALTH_TABLE", "rfid-gate-intelligence-health-events"))


# ---- API KEY DECORATOR --------------------------------------

def require_api_key(f):
    """
    Decorator that checks for a valid API key in the request header.
    
    How it works:
    - The caller must include: X-API-Key: <your-key> in the HTTP header
    - We compare it against MIDDLEWARE_API_KEY from the .env file
    - If it matches → request goes through
    - If it's missing or wrong → 401 Unauthorized
    - If no API key is configured → skip check (for local dev)
    
    Usage:
        @app.route("/rfid/data", methods=["POST"])
        @require_api_key
        def receive_rfid_data():
            ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # If no API key is configured, skip check (local development)
        if not MIDDLEWARE_API_KEY:
            logger.warning("API key not configured — skipping auth (dev mode)")
            return f(*args, **kwargs)

        # Check for the API key in the request header
        provided_key = request.headers.get("X-API-Key", "")

        if not provided_key:
            logger.warning(f"Rejected request — no API key provided from {request.remote_addr}")
            return jsonify({
                "error": "Missing API key",
                "hint": "Include X-API-Key header in your request"
            }), 401

        if provided_key != MIDDLEWARE_API_KEY:
            logger.warning(f"Rejected request — invalid API key from {request.remote_addr}")
            return jsonify({
                "error": "Invalid API key"
            }), 403

        # Key is valid — let the request through
        return f(*args, **kwargs)

    return decorated


# ---- ROUTES -------------------------------------------------

@app.route("/health", methods=["GET"])
def health_check():
    """
    Health check - tells you if the server and MQTT are running.
    No API key needed — this is a public status endpoint.
    """
    return jsonify({
        "status":         "ok",
        "mqtt_connected": mqtt_client.connected,
        "auth_enabled":   bool(MIDDLEWARE_API_KEY)
    }), 200


@app.route("/rfid/data", methods=["POST"])
@require_api_key
def receive_rfid_data():
    """
    Main endpoint - receives ALL packets from CTAgent
    URL: http://<server>:4501/rfid/data
    Requires X-API-Key header when MIDDLEWARE_API_KEY is set.
    Detects packet type from TYP field and routes to handler
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON body"}), 400

        packet_type = data.get("TYP", "").strip()
        logger.info(f"Received packet: {packet_type}")

        if packet_type == "GRHBPKT":
            return handle_health_packet(data)
        elif packet_type == "GRTAGDATA":
            return handle_tag_packet(data)
        else:
            return jsonify({
                "error":    "Unknown packet type",
                "received": packet_type,
                "expected": ["GRHBPKT", "GRTAGDATA"]
            }), 400

    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({"error": str(e)}), 500


def handle_health_packet(data):
    """
    Handles GRHBPKT packets:
    1. Validate  2. Store in DynamoDB
    3. Publish to MQTT uplink
    4. Send ACK to MQTT downlink
    5. Return HTTP response
    """
    is_valid, error_msg = validate_health_packet(data)
    if not is_valid:
        logger.error(f"Validation failed: {error_msg}")
        ack = format_health_ack(
            data.get("GATE_READER_ID", "unknown"),
            data.get("TIMESTAMP", "0"),
            error_code=4001
        )
        mqtt_client.publish(f"{DOWNLINK_TOPIC}/{data.get('GATE_READER_ID', 'unknown')}", ack)
        return jsonify(ack), 400

    gate_reader_id = data["GATE_READER_ID"]
    timestamp      = data["TIMESTAMP"]

    # Store in DynamoDB
    try:
        health_table.put_item(Item={
            "gate_reader_id":     gate_reader_id,
            "timestamp":          timestamp,
            "sample_periodicity": str(data.get("SAMPLE_PERIODICITY", 15)),
            "antenna_status":     json.dumps(data.get("HLTH_STAT_REQ", []))
        })
        error_code = 4000
    except Exception as e:
        logger.error(f"DynamoDB error: {e}")
        error_code = 4002

    # Publish uplink + downlink ACK
    mqtt_client.publish(UPLINK_TOPIC, data)
    ack = format_health_ack(gate_reader_id, timestamp, error_code)
    mqtt_client.publish(f"{DOWNLINK_TOPIC}/{gate_reader_id}", ack)

    return jsonify(ack), 200


def handle_tag_packet(data):
    """
    Handles GRTAGDATA packets:
    1. Validate  2. Store in DynamoDB
    3. Publish to MQTT uplink
    4. Send ACK to MQTT downlink
    5. Return HTTP response
    """
    is_valid, error_msg = validate_tag_packet(data)
    if not is_valid:
        logger.error(f"Validation failed: {error_msg}")
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
    except Exception as e:
        logger.error(f"DynamoDB error: {e}")
        error_code = 4002

    # Publish uplink + downlink ACK
    mqtt_client.publish(UPLINK_TOPIC, data)
    ack = format_tag_ack(gate_reader_id, readpoint, timestamp, error_code)
    mqtt_client.publish(f"{DOWNLINK_TOPIC}/{gate_reader_id}", ack)

    return jsonify(ack), 200


# ---- STARTUP ------------------------------------------------

if __name__ == "__main__":
    logger.info("Starting RFID Gate Intelligence Middleware...")

    # Log security status
    if MIDDLEWARE_API_KEY:
        logger.info("API key authentication: ENABLED")
    else:
        logger.warning("API key authentication: DISABLED (no MIDDLEWARE_API_KEY set)")

    mqtt_client.connect()
    port = int(os.getenv("FLASK_PORT", 4501))
    app.run(host="0.0.0.0", port=port, debug=False)