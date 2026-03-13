# ============================================================
# MQTT CLIENT
# Handles connection to Mosquitto broker
# Publishes uplink messages, subscribes to downlink ACKs
# QoS=1 = guaranteed at-least-once delivery
# Now with authentication support for secured broker
# ============================================================

import json
import logging
import os
import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MQTT settings from environment variables
UPLINK_TOPIC   = os.getenv("MQTT_UPLINK_TOPIC",   "Intellidb/rfid/gr/uplink")
DOWNLINK_TOPIC = os.getenv("MQTT_DOWNLINK_TOPIC",  "Intellidb/rfid/gr/downlink")
BROKER_HOST    = os.getenv("MQTT_BROKER_HOST",     "localhost")
BROKER_PORT    = int(os.getenv("MQTT_BROKER_PORT", "1883"))
MQTT_USER      = os.getenv("MQTT_MIDDLEWARE_USER", "")
MQTT_PASS      = os.getenv("MQTT_MIDDLEWARE_PASS", "")


class MQTTClient:
    def __init__(self):
        self.client = mqtt.Client(client_id="rfid-middleware")
        self.connected = False

        # Assign callback functions
        self.client.on_connect    = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message    = self._on_message
        self.client.on_publish    = self._on_publish

    def _on_connect(self, client, userdata, flags, rc):
        """Called automatically when broker connection is established"""
        if rc == 0:
            self.connected = True
            logger.info(f"Connected to MQTT broker at {BROKER_HOST}:{BROKER_PORT}")
            # Subscribe to all downlink topics using wildcard #
            client.subscribe(f"{DOWNLINK_TOPIC}/#", qos=1)
            logger.info(f"Subscribed to {DOWNLINK_TOPIC}/#")
        elif rc == 5:
            logger.error("MQTT connection refused: not authorised. Check MQTT_MIDDLEWARE_USER and MQTT_MIDDLEWARE_PASS.")
        else:
            logger.error(f"Failed to connect, return code: {rc}")

    def _on_disconnect(self, client, userdata, rc):
        """Called automatically when disconnected from broker"""
        self.connected = False
        logger.warning(f"Disconnected from broker, return code: {rc}")

    def _on_message(self, client, userdata, message):
        """Called automatically when a downlink ACK is received"""
        try:
            payload = json.loads(message.payload.decode())
            logger.info(f"ACK received on {message.topic}: {payload}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")

    def _on_publish(self, client, userdata, mid):
        """Called automatically when message is published successfully"""
        logger.info(f"Message published (mid={mid})")

    def connect(self):
        """Connect to MQTT broker and start background network thread"""
        try:
            # Set credentials if provided (for secured broker)
            if MQTT_USER:
                self.client.username_pw_set(MQTT_USER, MQTT_PASS)
                logger.info(f"MQTT auth: connecting as '{MQTT_USER}'")
            else:
                logger.warning("MQTT auth: no credentials set (anonymous mode)")

            self.client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
            self.client.loop_start()  # Background thread for network traffic
            logger.info(f"Connecting to MQTT broker at {BROKER_HOST}:{BROKER_PORT}")
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            raise

    def publish(self, topic, payload):
        """
        Publish a message to MQTT with QoS=1 (guaranteed delivery)
        Returns True if successful, False otherwise
        """
        try:
            message = json.dumps(payload)
            result  = self.client.publish(topic, message, qos=1)

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"Published to {topic}: {message}")
                return True
            else:
                logger.error(f"Publish failed, rc={result.rc}")
                return False
        except Exception as e:
            logger.error(f"Publish error: {e}")
            return False

    def disconnect(self):
        """Cleanly disconnect from broker"""
        self.client.loop_stop()
        self.client.disconnect()


# Single shared instance used across the whole app
mqtt_client = MQTTClient()