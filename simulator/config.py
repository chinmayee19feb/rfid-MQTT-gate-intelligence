"""
CTAgent Simulator Configuration
================================
Defines gate readers, EPC tag pools, read points, and timing settings.
All values based on the Intellistride C++ Integration with Reader and MQTT spec.
"""

import os

# ---------------------------------------------------------------------------
# Middleware connection
# ---------------------------------------------------------------------------
MIDDLEWARE_URL = "http://localhost:4501/rfid/data"
# When running against the AWS app server, change to:
# MIDDLEWARE_URL = "http://100.54.32.242:4501/rfid/data"

# API key for authenticating with the middleware
# Read from environment variable (set in .env file)
MIDDLEWARE_API_KEY = os.getenv("MIDDLEWARE_API_KEY", "")

# ---------------------------------------------------------------------------
# Gate reader definitions
# ---------------------------------------------------------------------------
# Each reader has a unique hex ID (like a real CTAgent device fingerprint),
# a plant/door read-point prefix, and the number of antennas installed.
GATE_READERS = [
    {
        "id": "f8e375cff9d1f97d",
        "readpoint_prefix": "PLANT_01_DOOR_01",
        "antennas": 4,
        "description": "Main entrance – Building A",
    },
    {
        "id": "a1b2c3d4e5f67890",
        "readpoint_prefix": "PLANT_01_DOOR_02",
        "antennas": 4,
        "description": "Shipping dock – Building A",
    },
    {
        "id": "1234abcd5678ef90",
        "readpoint_prefix": "PLANT_02_DOOR_01",
        "antennas": 4,
        "description": "Warehouse entrance – Building B",
    },
]

# ---------------------------------------------------------------------------
# Timing (seconds)
# ---------------------------------------------------------------------------
HEALTH_INTERVAL_SECONDS = 15 * 60          # 15 minutes (production)
HEALTH_INTERVAL_SECONDS_DEMO = 30          # 30 seconds  (demo / testing)

TAG_MIN_INTERVAL_SECONDS = 3               # fastest gap between tag events
TAG_MAX_INTERVAL_SECONDS = 15              # slowest gap between tag events

# ---------------------------------------------------------------------------
# EPC tag pools
# ---------------------------------------------------------------------------
FILE_EPCS = [
    "884D000EDF000000000001",
    "884D000EDF000000000002",
    "884D000EDF000000000003",
    "884D000EDF000000000004",
    "884D000EDF000000000005",
    "884D000EDF000000000006",
    "884D000EDF000000000007",
    "884D000EDF000000000008",
    "884D000EDF000000000009",
    "884D000EDF000000000010",
]

BOX_EPCS = [
    "884D000EDC0000000A0001",
    "884D000EDC0000000A0002",
    "884D000EDC0000000A0003",
    "884D000EDC0000000A0004",
    "884D000EDC0000000A0005",
]

CART_EPCS = [
    "884D000EDB0000000B0001",
    "884D000EDB0000000B0002",
    "884D000EDB0000000B0003",
]

TAGS_PER_EVENT_MIN = 1
TAGS_PER_EVENT_MAX = 8

# ---------------------------------------------------------------------------
# Direction weights
# ---------------------------------------------------------------------------
DIRECTION_IN_WEIGHT = 0.6

# ---------------------------------------------------------------------------
# Antenna failure simulation
# ---------------------------------------------------------------------------
ANTENNA_FAILURE_PROBABILITY = 0.05         # 5 % chance per antenna