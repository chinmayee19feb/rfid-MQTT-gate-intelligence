"""
CTAgent Simulator Configuration
================================
Defines gate readers, EPC tag pools, read points, and timing settings.
All values based on the Intellistride C++ Integration with Reader and MQTT spec.
"""

# ---------------------------------------------------------------------------
# Middleware connection
# ---------------------------------------------------------------------------
MIDDLEWARE_URL = "http://localhost:4501/rfid/data"
# When running against the AWS app server, change to:
# MIDDLEWARE_URL = "http://100.54.32.242:4501"

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
# Health packets are sent every HEALTH_INTERVAL seconds.
# The spec says SAMPLE_PERIODICITY is in minutes; default = 15 min.
HEALTH_INTERVAL_SECONDS = 15 * 60          # 15 minutes (production)
HEALTH_INTERVAL_SECONDS_DEMO = 30          # 30 seconds  (demo / testing)

# Tag telemetry packets are sent at random intervals within this range.
TAG_MIN_INTERVAL_SECONDS = 3               # fastest gap between tag events
TAG_MAX_INTERVAL_SECONDS = 15              # slowest gap between tag events

# ---------------------------------------------------------------------------
# EPC tag pools
# ---------------------------------------------------------------------------
# Realistic 24-hex-char EPC codes grouped by asset type.
# The simulator randomly picks a subset for each telemetry event.
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

# How many EPC tags to include per telemetry packet (min, max).
TAGS_PER_EVENT_MIN = 1
TAGS_PER_EVENT_MAX = 8

# ---------------------------------------------------------------------------
# Direction weights
# ---------------------------------------------------------------------------
# Probability of IN vs OUT.  0.6 means 60 % of events are IN.
DIRECTION_IN_WEIGHT = 0.6

# ---------------------------------------------------------------------------
# Antenna failure simulation
# ---------------------------------------------------------------------------
# Probability that any single antenna reports "N" (not operational).
ANTENNA_FAILURE_PROBABILITY = 0.05         # 5 % chance per antenna