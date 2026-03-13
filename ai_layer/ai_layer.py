#!/usr/bin/env python3
"""
AI Layer  –  Phase 4 of the RFID Gate Intelligence Platform
=============================================================
This is the main program that ties everything together.

What it does:
  1. Connects to the MQTT broker (same one the middleware uses)
  2. Subscribes to the uplink topic to listen for RFID events
  3. Stores incoming events in the EventStore (short-term memory)
  4. Periodically sends accumulated events to Claude for analysis
  5. Publishes any anomaly alerts back to MQTT

Usage:
    # Normal mode (analyze every 60s or 10 events):
    python ai_layer.py

    # Demo mode (analyze every 30s or 5 events):
    python ai_layer.py --demo

    # Verbose logging:
    python ai_layer.py --demo --verbose
"""

import argparse
import json
import logging
import sys
import threading
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

import config
from event_store import EventStore
from anomaly_detector import AnomalyDetector

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logger = logging.getLogger("ai_layer")
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(
    "%(asctime)s  [%(levelname)s]  %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Colours
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
RESET = "\033[0m"


# ═══════════════════════════════════════════════════════════════════════════
# MQTT Callbacks
# ═══════════════════════════════════════════════════════════════════════════

def on_connect(client, userdata, flags, rc):
    """
    Called when we connect to the MQTT broker.
    rc=0 means success. Any other value is an error.
    """
    if rc == 0:
        logger.info(
            f"{GREEN}Connected to MQTT broker{RESET} "
            f"at {config.MQTT_BROKER_HOST}:{config.MQTT_BROKER_PORT}"
        )
        # Subscribe to the uplink topic to receive all RFID events
        client.subscribe(config.MQTT_UPLINK_TOPIC, qos=1)
        logger.info(
            f"Subscribed to: {CYAN}{config.MQTT_UPLINK_TOPIC}{RESET}"
        )
    elif rc == 5:
        logger.error(
            f"{RED}MQTT connection refused: not authorised.{RESET} "
            "Check MQTT_AI_USER and MQTT_AI_PASS."
        )
    else:
        error_messages = {
            1: "incorrect protocol version",
            2: "invalid client ID",
            3: "server unavailable",
            4: "bad username/password",
            5: "not authorized",
        }
        reason = error_messages.get(rc, f"unknown error code {rc}")
        logger.error(f"{RED}MQTT connection failed:{RESET} {reason}")


def on_disconnect(client, userdata, rc):
    """Called when we disconnect from the MQTT broker."""
    if rc == 0:
        logger.info("Disconnected from MQTT broker (clean).")
    else:
        logger.warning(
            f"{YELLOW}Unexpected MQTT disconnect (rc={rc}).{RESET} "
            "Will auto-reconnect..."
        )


def on_message(client, userdata, msg):
    """
    Called every time an MQTT message arrives on the uplink topic.

    This is where the action starts:
    1. Parse the JSON message
    2. Store it in the EventStore
    3. Check if it's time to analyze
    """
    try:
        # Parse the raw MQTT payload into a Python dict
        payload = json.loads(msg.payload.decode("utf-8"))
        packet_type = payload.get("TYP", "UNKNOWN")
        reader_id = payload.get("GATE_READER_ID", "?")[:8]

        # Store the event
        store = userdata["store"]
        event_count = store.add(payload)

        # Log what we received
        if packet_type == "GRTAGDATA":
            direction = payload.get("READPOINT", "").split(".")[-1]
            num_tags = len(payload.get("FILE_EPCList", []))
            logger.info(
                f"{CYAN}[MQTT]{RESET}  Received TAG event: "
                f"Reader {reader_id}…  "
                f"{'📥 IN ' if direction == 'IN' else '📤 OUT'}  "
                f"{num_tags} tags  "
                f"(buffer: {event_count} events)"
            )
        elif packet_type == "GRHBPKT":
            antennas = payload.get("HLTH_STAT_REQ", [])
            down_count = sum(
                1 for a in antennas if list(a.values())[0] == "N"
            )
            if down_count > 0:
                logger.info(
                    f"{YELLOW}[MQTT]{RESET}  Received HEALTH event: "
                    f"Reader {reader_id}…  "
                    f"⚠ {down_count} antenna(s) DOWN  "
                    f"(buffer: {event_count} events)"
                )
            else:
                logger.info(
                    f"{CYAN}[MQTT]{RESET}  Received HEALTH event: "
                    f"Reader {reader_id}…  "
                    f"all antennas OK  "
                    f"(buffer: {event_count} events)"
                )
        else:
            logger.debug(f"Received unknown packet type: {packet_type}")

    except json.JSONDecodeError:
        logger.warning(f"Could not parse MQTT message: {msg.payload[:100]}")
    except Exception as exc:
        logger.error(f"Error processing MQTT message: {exc}")


# ═══════════════════════════════════════════════════════════════════════════
# Analysis Loop
# ═══════════════════════════════════════════════════════════════════════════

def analysis_loop(store: EventStore, detector: AnomalyDetector, client: mqtt.Client):
    """
    Runs in a background thread.
    Checks every 5 seconds if it's time to run an analysis.

    When triggered, it:
    1. Grabs all events from the store
    2. Sends them to Claude for analysis
    3. Publishes any alerts to MQTT
    4. Clears the store for the next batch
    """
    logger.info(
        f"{MAGENTA}[AI]{RESET}  Analysis loop started. "
        f"Waiting for events to accumulate..."
    )

    while True:
        time.sleep(5)  # Check every 5 seconds

        if store.should_analyze():
            # Get events and summary
            events = store.get_all()
            summary = store.get_summary()

            logger.info(
                f"\n{MAGENTA}{'='*60}{RESET}\n"
                f"{MAGENTA}[AI]  ANALYSIS TRIGGERED{RESET}  "
                f"({summary['total_events']} events: "
                f"{summary['tag_events']} tags, "
                f"{summary['health_events']} health, "
                f"{summary['in_count']} IN, {summary['out_count']} OUT)\n"
                f"{MAGENTA}{'='*60}{RESET}"
            )

            # Send to Claude
            alerts = detector.analyze(events)

            # Publish alerts to MQTT
            if alerts:
                publish_alerts(client, alerts)

            # Log API usage
            logger.info(
                f"{MAGENTA}[AI]{RESET}  {detector.get_usage_report()}"
            )

            # Clear the store for next batch
            store.clear()


def publish_alerts(client: mqtt.Client, alerts: list[dict]):
    """
    Publish anomaly alerts back to MQTT so other systems can react.

    Alerts go to two places:
    1. The general AI alerts topic (for dashboards / monitoring)
    2. The specific gate reader's downlink topic (for that reader)
    """
    for alert in alerts:
        alert_message = {
            "TYP": "AI_ALERT",
            "TIMESTAMP": str(int(datetime.now(timezone.utc).timestamp() * 1000)),
            "ALERT_TYPE": alert.get("type", "UNKNOWN"),
            "SEVERITY": alert.get("severity", "UNKNOWN"),
            "GATE_READER_ID": alert.get("gate_reader_id", ""),
            "DESCRIPTION": alert.get("description", ""),
            "EPC_CODES": alert.get("epc_codes", []),
            "RECOMMENDATION": alert.get("recommendation", ""),
        }

        # Publish to the general AI alerts topic
        client.publish(
            config.MQTT_AI_ALERT_TOPIC,
            json.dumps(alert_message),
            qos=1,
        )

        # Also publish to the specific gate reader's downlink
        reader_id = alert.get("gate_reader_id", "")
        if reader_id:
            topic = f"{config.MQTT_DOWNLINK_PREFIX}/{reader_id}"
            client.publish(topic, json.dumps(alert_message), qos=1)

        severity = alert.get("severity", "?")
        alert_type = alert.get("type", "?")
        logger.info(
            f"{MAGENTA}[AI]{RESET}  Published alert: "
            f"[{severity}] {alert_type} → MQTT"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Startup Banner
# ═══════════════════════════════════════════════════════════════════════════

def print_banner(args):
    """Print a startup summary."""
    mode = "DEMO" if args.demo else "PRODUCTION"
    interval = (
        config.DEMO_ANALYSIS_INTERVAL_SECONDS
        if args.demo
        else config.ANALYSIS_INTERVAL_SECONDS
    )
    threshold = (
        config.DEMO_ANALYSIS_EVENT_THRESHOLD
        if args.demo
        else config.ANALYSIS_EVENT_THRESHOLD
    )

    print()
    print("=" * 60)
    print(f"  {MAGENTA}AI Anomaly Detection Layer{RESET}")
    print(f"  RFID Gate Intelligence Platform – Phase 4")
    print("=" * 60)
    print(f"  Mode          : {GREEN}{mode}{RESET}")
    print(f"  MQTT broker   : {config.MQTT_BROKER_HOST}:{config.MQTT_BROKER_PORT}")
    print(f"  MQTT user     : {config.MQTT_USER or 'anonymous (no auth)'}")
    print(f"  Listening on  : {config.MQTT_UPLINK_TOPIC}")
    print(f"  Alerts topic  : {config.MQTT_AI_ALERT_TOPIC}")
    print(f"  Claude model  : {config.CLAUDE_MODEL}")
    print(f"  Analyze every : {interval}s or {threshold} events")
    print(f"  API key       : {'✓ set' if config.ANTHROPIC_API_KEY else '✗ MISSING'}")
    print("=" * 60)
    print(f"  Press {YELLOW}Ctrl+C{RESET} to stop")
    print("=" * 60)
    print()


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="AI Anomaly Detection Layer for RFID Gate Intelligence"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Demo mode: analyze more frequently (every 30s or 5 events)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug-level logging",
    )
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    print_banner(args)

    # --- Check API key ---
    if not config.ANTHROPIC_API_KEY:
        logger.error(
            f"{RED}ERROR: ANTHROPIC_API_KEY environment variable not set!{RESET}\n"
            f"  Run this command first:\n"
            f"  export ANTHROPIC_API_KEY='sk-ant-your-key-here'"
        )
        sys.exit(1)

    # --- Create components ---
    store = EventStore(demo_mode=args.demo)
    detector = AnomalyDetector()

    # --- Set up MQTT client ---
    client = mqtt.Client(
        client_id="rfid-ai-layer",
        userdata={"store": store},
    )

    # Set MQTT credentials for secured broker
    if config.MQTT_USER:
        client.username_pw_set(config.MQTT_USER, config.MQTT_PASS)
        logger.info(f"MQTT auth: connecting as '{config.MQTT_USER}'")
    else:
        logger.warning("MQTT auth: no credentials set (anonymous mode)")

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    # --- Connect to MQTT broker ---
    try:
        logger.info(
            f"Connecting to MQTT broker at "
            f"{config.MQTT_BROKER_HOST}:{config.MQTT_BROKER_PORT}..."
        )
        client.connect(config.MQTT_BROKER_HOST, config.MQTT_BROKER_PORT, keepalive=60)
    except ConnectionRefusedError:
        logger.error(
            f"{RED}Cannot connect to MQTT broker!{RESET}\n"
            f"  Make sure Mosquitto is running:\n"
            f"  sudo systemctl start mosquitto"
        )
        sys.exit(1)
    except Exception as exc:
        logger.error(f"{RED}MQTT connection error:{RESET} {exc}")
        sys.exit(1)

    # --- Start the analysis loop in a background thread ---
    analysis_thread = threading.Thread(
        target=analysis_loop,
        args=(store, detector, client),
        daemon=True,
    )
    analysis_thread.start()

    # --- Start the MQTT event loop ---
    try:
        logger.info(f"{GREEN}AI Layer is running. Listening for RFID events...{RESET}\n")
        client.loop_forever()
    except KeyboardInterrupt:
        print()
        logger.info(f"{YELLOW}AI Layer stopped by user.{RESET}")
        logger.info(f"Final stats: {detector.get_usage_report()}")
        client.disconnect()
        sys.exit(0)


if __name__ == "__main__":
    main()