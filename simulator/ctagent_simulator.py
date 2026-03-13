#!/usr/bin/env python3
"""
CTAgent Simulator  –  Phase 3 of the RFID Gate Intelligence Platform
=====================================================================
Simulates multiple RFID gate readers (CTAgent devices) that send:
  • GRHBPKT   – health status packets      (every 15 min, or 30 s in demo mode)
  • GRTAGDATA – tag telemetry packets       (continuous, random interval)

Packets are HTTP-POSTed to the Flask middleware on port 4501, exactly as
a real CTAgent would.  The middleware then validates, stores to DynamoDB,
and publishes to MQTT.

Usage
-----
    # Normal mode (health every 15 min, tags every 3-15 s):
    python ctagent_simulator.py

    # Demo / testing mode (health every 30 s, tags every 2-5 s):
    python ctagent_simulator.py --demo

    # Custom middleware URL:
    python ctagent_simulator.py --url http://100.54.32.242:4501

    # Send only 20 tag events then stop:
    python ctagent_simulator.py --demo --max-events 20

    # Run with verbose logging:
    python ctagent_simulator.py --demo --verbose
"""

import argparse
import json
import logging
import random
import sys
import threading
import time
from datetime import datetime, timezone

import requests

import config

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logger = logging.getLogger("ctagent_simulator")
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(
    "%(asctime)s  [%(levelname)s]  %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Colour helpers (for readable terminal output)
# ---------------------------------------------------------------------------
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
RESET = "\033[0m"


# ═══════════════════════════════════════════════════════════════════════════
# Packet generators
# ═══════════════════════════════════════════════════════════════════════════

def epoch_ms_now() -> str:
    """Return current UTC time as epoch milliseconds string."""
    return str(int(datetime.now(timezone.utc).timestamp() * 1000))


def generate_health_packet(reader: dict, sample_periodicity: int = 15) -> dict:
    """
    Build a GRHBPKT health status packet for one gate reader.

    Fields per Intellistride spec §2.1 / §3.1:
      TYP               – always "GRHBPKT"
      GATE_READER_ID    – unique device hex ID
      SAMPLE_PERIODICITY– health interval in minutes
      TIMESTAMP         – UTC epoch ms
      HLTH_STAT_REQ     – list of antenna statuses (Y/N)
    """
    antenna_statuses = []
    for i in range(1, reader["antennas"] + 1):
        # Each antenna has a small chance of being down
        status = "N" if random.random() < config.ANTENNA_FAILURE_PROBABILITY else "Y"
        antenna_statuses.append({f"Antenna{i}": status})

    packet = {
        "TYP": "GRHBPKT",
        "GATE_READER_ID": reader["id"],
        "SAMPLE_PERIODICITY": sample_periodicity,
        "TIMESTAMP": epoch_ms_now(),
        "HLTH_STAT_REQ": antenna_statuses,
    }
    return packet


def generate_tag_packet(reader: dict) -> dict:
    """
    Build a GRTAGDATA tag telemetry packet for one gate reader.

    Fields per Intellistride spec §2.2 / §3.3:
      TYP             – always "GRTAGDATA"
      GATE_READER_ID  – unique device hex ID
      READPOINT       – "<prefix>.IN" or "<prefix>.OUT"
      EVENTTIME       – UTC epoch ms
      FILE_EPCList    – list of EPC tag codes detected in this crossing
    """
    # Pick direction (IN or OUT)
    direction = "IN" if random.random() < config.DIRECTION_IN_WEIGHT else "OUT"
    readpoint = f"{reader['readpoint_prefix']}.{direction}"

    # Pick a random number of EPC tags from the combined pool
    all_epcs = config.FILE_EPCS + config.BOX_EPCS + config.CART_EPCS
    num_tags = random.randint(config.TAGS_PER_EVENT_MIN, config.TAGS_PER_EVENT_MAX)
    num_tags = min(num_tags, len(all_epcs))
    selected_epcs = random.sample(all_epcs, num_tags)

    epc_list = [{str(i): epc} for i, epc in enumerate(selected_epcs)]

    packet = {
        "TYP": "GRTAGDATA",
        "GATE_READER_ID": reader["id"],
        "READPOINT": readpoint,
        "EVENTTIME": epoch_ms_now(),
        "FILE_EPCList": epc_list,
    }
    return packet


# ═══════════════════════════════════════════════════════════════════════════
# HTTP sender
# ═══════════════════════════════════════════════════════════════════════════

def send_packet(url: str, packet: dict, verbose: bool = False) -> dict | None:
    """
    POST a JSON packet to the middleware and return the parsed response.

    The real CTAgent sends HTTP POST to port 4501.  The middleware responds
    with an ACK packet containing an error code:
      4000 – success
      4001 – validation failed
      4002 – DB insert failed
      4010 – unknown error
    """
    try:
        # Build headers — include API key if configured
        headers = {"Content-Type": "application/json"}
        if config.MIDDLEWARE_API_KEY:
            headers["X-API-Key"] = config.MIDDLEWARE_API_KEY

        resp = requests.post(url, json=packet, headers=headers, timeout=10)

        if verbose:
            logger.debug(f"→ POST {url}  status={resp.status_code}")

        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 401:
            logger.error(f"{RED}Rejected — missing API key{RESET}")
            return None
        elif resp.status_code == 403:
            logger.error(f"{RED}Rejected — invalid API key{RESET}")
            return None
        else:
            logger.warning(f"HTTP {resp.status_code} from middleware: {resp.text[:200]}")
            return None

    except requests.ConnectionError:
        logger.error(
            f"{RED}Connection refused{RESET} – is the middleware running on {url}?"
        )
        return None
    except requests.Timeout:
        logger.error(f"{RED}Timeout{RESET} – middleware did not respond within 10 s")
        return None
    except Exception as exc:
        logger.error(f"{RED}Unexpected error:{RESET} {exc}")
        return None

# ═══════════════════════════════════════════════════════════════════════════
# Pretty-print helpers
# ═══════════════════════════════════════════════════════════════════════════

def log_health_packet(packet: dict, response: dict | None, reader: dict):
    """Log a health packet send with colour-coded output."""
    antennas = packet["HLTH_STAT_REQ"]
    antenna_str = "  ".join(
        f"{'🟢' if list(a.values())[0] == 'Y' else '🔴'}{list(a.keys())[0]}"
        for a in antennas
    )
    ts = datetime.fromtimestamp(
        int(packet["TIMESTAMP"]) / 1000, tz=timezone.utc
    ).strftime("%H:%M:%S UTC")

    status = format_ack(response)
    logger.info(
        f"{CYAN}[HEALTH]{RESET}  Reader {packet['GATE_READER_ID'][:8]}… "
        f"({reader['description']})  {antenna_str}  "
        f"@ {ts}  →  {status}"
    )


def log_tag_packet(packet: dict, response: dict | None, reader: dict):
    """Log a tag telemetry packet send with colour-coded output."""
    direction = packet["READPOINT"].split(".")[-1]
    dir_icon = "📥 IN " if direction == "IN" else "📤 OUT"
    num_tags = len(packet["FILE_EPCList"])
    ts = datetime.fromtimestamp(
        int(packet["EVENTTIME"]) / 1000, tz=timezone.utc
    ).strftime("%H:%M:%S UTC")

    status = format_ack(response)
    logger.info(
        f"{YELLOW}[TAG]   {RESET}  Reader {packet['GATE_READER_ID'][:8]}… "
        f"({reader['description']})  {dir_icon}  "
        f"{num_tags} tag{'s' if num_tags != 1 else ''}  "
        f"@ {ts}  →  {status}"
    )


def format_ack(response: dict | None) -> str:
    """Format the middleware ACK response for display."""
    if response is None:
        return f"{RED}NO RESPONSE{RESET}"

    # The ACK may have MSG_ACK_STATUS at top level or nested
    ack = response.get("MSG_ACK_STATUS", response)
    code = ack.get("Error_Code", ack.get("Error Code", "?"))
    desc = ack.get("Error_Descr", "")

    if str(code) == "4000":
        return f"{GREEN}ACK 4000 ✓{RESET}"
    elif str(code) == "4001":
        return f"{RED}ACK 4001 – validation fail{RESET}"
    elif str(code) == "4002":
        return f"{RED}ACK 4002 – DB insert fail{RESET}"
    else:
        return f"{YELLOW}ACK {code} – {desc}{RESET}"


# ═══════════════════════════════════════════════════════════════════════════
# Worker threads
# ═══════════════════════════════════════════════════════════════════════════

class HealthWorker(threading.Thread):
    """
    Sends periodic GRHBPKT health packets for one gate reader.
    Runs as a daemon thread so it stops when the main thread exits.
    """

    def __init__(self, reader: dict, url: str, interval: int, verbose: bool = False):
        super().__init__(daemon=True)
        self.reader = reader
        self.url = url
        self.interval = interval
        self.verbose = verbose
        self.name = f"health-{reader['id'][:8]}"

    def run(self):
        sample_periodicity = self.interval // 60 or 1
        while True:
            packet = generate_health_packet(self.reader, sample_periodicity)
            response = send_packet(self.url, packet, self.verbose)
            log_health_packet(packet, response, self.reader)
            time.sleep(self.interval)


class TagWorker(threading.Thread):
    """
    Sends continuous GRTAGDATA tag telemetry packets for one gate reader.
    The interval between events is randomised to simulate real-world traffic.
    """

    def __init__(
        self,
        reader: dict,
        url: str,
        min_interval: float,
        max_interval: float,
        verbose: bool = False,
        max_events: int = 0,
        counter: dict | None = None,
    ):
        super().__init__(daemon=True)
        self.reader = reader
        self.url = url
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.verbose = verbose
        self.max_events = max_events
        self.counter = counter  # shared mutable dict {"count": n, "lock": Lock}
        self.name = f"tag-{reader['id'][:8]}"

    def run(self):
        while True:
            # Check if we've hit the event limit
            if self.max_events and self.counter:
                with self.counter["lock"]:
                    if self.counter["count"] >= self.max_events:
                        return
                    self.counter["count"] += 1

            packet = generate_tag_packet(self.reader)
            response = send_packet(self.url, packet, self.verbose)
            log_tag_packet(packet, response, self.reader)

            delay = random.uniform(self.min_interval, self.max_interval)
            time.sleep(delay)


# ═══════════════════════════════════════════════════════════════════════════
# Startup banner
# ═══════════════════════════════════════════════════════════════════════════

def print_banner(args, readers):
    """Print a nice startup summary."""
    mode = "DEMO" if args.demo else "PRODUCTION"
    health_int = (
        config.HEALTH_INTERVAL_SECONDS_DEMO
        if args.demo
        else config.HEALTH_INTERVAL_SECONDS
    )

    print()
    print("=" * 66)
    print(f"  {CYAN}CTAgent Simulator{RESET}  –  RFID Gate Intelligence Platform")
    print("=" * 66)
    print(f"  Mode        : {GREEN}{mode}{RESET}")
    print(f"  Middleware   : {args.url}")
    print(f"  Health every : {health_int} seconds")
    print(f"  Tag interval : {config.TAG_MIN_INTERVAL_SECONDS}–{config.TAG_MAX_INTERVAL_SECONDS} s")
    if args.max_events:
        print(f"  Max events   : {args.max_events}")
    print(f"  Gate readers : {len(readers)}")
    for r in readers:
        print(f"    • {r['id'][:8]}…  {r['readpoint_prefix']}  ({r['description']})")
    print("=" * 66)
    print(f"  Press {YELLOW}Ctrl+C{RESET} to stop the simulator")
    print("=" * 66)
    print()


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="CTAgent Simulator – generates realistic RFID gate reader traffic"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Demo mode: health every 30 s instead of 15 min",
    )
    parser.add_argument(
        "--url",
        default=config.MIDDLEWARE_URL,
        help=f"Middleware URL (default: {config.MIDDLEWARE_URL})",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=0,
        help="Stop after N tag events (0 = unlimited)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug-level logging",
    )
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    readers = config.GATE_READERS
    print_banner(args, readers)

    # --- Health interval ---
    health_interval = (
        config.HEALTH_INTERVAL_SECONDS_DEMO
        if args.demo
        else config.HEALTH_INTERVAL_SECONDS
    )

    # --- Tag interval (slightly faster in demo mode) ---
    tag_min = 2 if args.demo else config.TAG_MIN_INTERVAL_SECONDS
    tag_max = 5 if args.demo else config.TAG_MAX_INTERVAL_SECONDS

    # --- Shared counter for --max-events ---
    counter = {"count": 0, "lock": threading.Lock()} if args.max_events else None

    # --- Send an initial health packet from each reader immediately ---
    logger.info("Sending initial health check from all readers …")
    for reader in readers:
        packet = generate_health_packet(reader)
        response = send_packet(args.url, packet, args.verbose)
        log_health_packet(packet, response, reader)

    print()

    # --- Start worker threads ---
    threads = []
    for reader in readers:
        hw = HealthWorker(reader, args.url, health_interval, args.verbose)
        hw.start()
        threads.append(hw)

        tw = TagWorker(
            reader, args.url, tag_min, tag_max, args.verbose, args.max_events, counter
        )
        tw.start()
        threads.append(tw)

    # --- Wait ---
    try:
        if args.max_events:
            # Poll until all tag events are sent
            while True:
                with counter["lock"]:
                    if counter["count"] >= args.max_events:
                        break
                time.sleep(0.5)
            logger.info(
                f"\n{GREEN}✓ Sent {args.max_events} tag events – simulator complete.{RESET}"
            )
        else:
            # Run forever until Ctrl+C
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        print()
        logger.info(f"{YELLOW}Simulator stopped by user.{RESET}")
        sys.exit(0)


if __name__ == "__main__":
    main()