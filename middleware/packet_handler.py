# ============================================================
# PACKET HANDLER
# Validates and formats incoming RFID packets
# Based on Intellistride spec:
#   GRHBPKT   = Health Status packet
#   GRTAGDATA = Tag Telemetry packet
# ============================================================

import json

# Error codes from the Intellistride spec
ERROR_CODES = {
    4000: "Successful in Middleware",
    4001: "Data validation failed in Middleware",
    4002: "Data Insertion issue with Middleware local DB",
    4010: "Unknown"
}


def validate_health_packet(data):
    """
    Validates a GRHBPKT health status packet.
    Required fields: TYP, GATE_READER_ID, TIMESTAMP, HLTH_STAT_REQ
    Returns: (is_valid, error_message)
    """
    required_fields = ["TYP", "GATE_READER_ID", "TIMESTAMP", "HLTH_STAT_REQ"]

    # Check all required fields exist
    for field in required_fields:
        if field not in data:
            return False, f"Missing required field: {field}"

    # Check packet type is correct
    if data["TYP"].strip() != "GRHBPKT":
        return False, f"Invalid packet type: {data['TYP']}"

    # Check antenna status is a list
    if not isinstance(data["HLTH_STAT_REQ"], list):
        return False, "HLTH_STAT_REQ must be a list"

    return True, None


def validate_tag_packet(data):
    """
    Validates a GRTAGDATA tag telemetry packet.
    Required fields: TYP, GATE_READER_ID, READPOINT, EVENTTIME
    Returns: (is_valid, error_message)
    """
    required_fields = ["TYP", "GATE_READER_ID", "READPOINT", "EVENTTIME"]

    # Check all required fields exist
    for field in required_fields:
        if field not in data:
            return False, f"Missing required field: {field}"

    # Check packet type is correct
    if data["TYP"].strip() != "GRTAGDATA":
        return False, f"Invalid packet type: {data['TYP']}"

    # Check READPOINT contains direction (must end in .IN or .OUT)
    readpoint = data["READPOINT"]
    if not (readpoint.endswith(".IN") or readpoint.endswith(".OUT")):
        return False, f"READPOINT must end with .IN or .OUT, got: {readpoint}"

    return True, None


def format_health_ack(gate_reader_id, timestamp, error_code=4000):
    """
    Builds the MQTT downlink ACK for a health packet (GRHBACK).
    Published back to gate reader to confirm receipt.
    """
    return {
        "TYP": "GRHBACK",
        "GATE_READER_ID": gate_reader_id,
        "TIMESTAMP": timestamp,
        "MSG_ACK_STATUS": {
            "Error_Code": error_code,
            "Error_Descr": ERROR_CODES.get(error_code, "Unknown")
        }
    }


def format_tag_ack(gate_reader_id, readpoint, timestamp, error_code=4000):
    """
    Builds the MQTT downlink ACK for a tag packet (GRTAGDATACK).
    Published back to gate reader to confirm receipt.
    """
    return {
        "TYP": "GRTAGDATACK",
        "GATE_READER_ID": gate_reader_id,
        "READPOINT": readpoint,
        "TIMESTAMP": timestamp,
        "MSG_ACK_STATUS": {
            "Error_Code": error_code,
            "Error_Descr": ERROR_CODES.get(error_code, "Unknown")
        }
    }


def extract_direction(readpoint):
    """
    Extracts IN or OUT from readpoint string.
    Example: "PLANT_01_DOOR_03.IN" → "IN"
    """
    if readpoint.endswith(".IN"):
        return "IN"
    elif readpoint.endswith(".OUT"):
        return "OUT"
    return "UNKNOWN"