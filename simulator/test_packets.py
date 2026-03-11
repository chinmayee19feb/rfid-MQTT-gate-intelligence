#!/usr/bin/env python3
"""
Test script – validates packet generation without a running middleware.
Run this first to make sure your packets look correct before hitting the real middleware.

Usage:
    python test_packets.py
"""

import json
import sys

# Add parent dir so we can import config
sys.path.insert(0, ".")
import config
from ctagent_simulator import generate_health_packet, generate_tag_packet, epoch_ms_now


def separator(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def validate_health_packet(packet: dict) -> list[str]:
    """Return a list of validation errors (empty = valid)."""
    errors = []
    if packet.get("TYP") != "GRHBPKT":
        errors.append(f"TYP should be 'GRHBPKT', got '{packet.get('TYP')}'")
    if not packet.get("GATE_READER_ID"):
        errors.append("Missing GATE_READER_ID")
    if not isinstance(packet.get("SAMPLE_PERIODICITY"), int):
        errors.append("SAMPLE_PERIODICITY should be an integer")
    if not packet.get("TIMESTAMP"):
        errors.append("Missing TIMESTAMP")
    if not isinstance(packet.get("HLTH_STAT_REQ"), list):
        errors.append("HLTH_STAT_REQ should be a list")
    else:
        for item in packet["HLTH_STAT_REQ"]:
            if not isinstance(item, dict) or len(item) != 1:
                errors.append(f"Invalid antenna entry: {item}")
            else:
                val = list(item.values())[0]
                if val not in ("Y", "N"):
                    errors.append(f"Antenna value should be Y/N, got '{val}'")
    return errors


def validate_tag_packet(packet: dict) -> list[str]:
    """Return a list of validation errors (empty = valid)."""
    errors = []
    if packet.get("TYP") != "GRTAGDATA":
        errors.append(f"TYP should be 'GRTAGDATA', got '{packet.get('TYP')}'")
    if not packet.get("GATE_READER_ID"):
        errors.append("Missing GATE_READER_ID")
    readpoint = packet.get("READPOINT", "")
    if not readpoint.endswith(".IN") and not readpoint.endswith(".OUT"):
        errors.append(f"READPOINT should end with .IN or .OUT, got '{readpoint}'")
    if not packet.get("EVENTTIME"):
        errors.append("Missing EVENTTIME")
    epc_list = packet.get("FILE_EPCList")
    if not isinstance(epc_list, list) or len(epc_list) == 0:
        errors.append("FILE_EPCList should be a non-empty list")
    else:
        for item in epc_list:
            if not isinstance(item, dict) or len(item) != 1:
                errors.append(f"Invalid EPC entry: {item}")
    return errors


def main():
    print("\n🧪  CTAgent Simulator – Packet Validation Test\n")

    all_passed = True

    # --- Test health packets for each reader ---
    separator("HEALTH PACKETS (GRHBPKT)")
    for reader in config.GATE_READERS:
        packet = generate_health_packet(reader)
        print(f"Reader: {reader['id'][:8]}…  ({reader['description']})")
        print(json.dumps(packet, indent=2))

        errors = validate_health_packet(packet)
        if errors:
            print(f"  ❌ FAIL: {errors}")
            all_passed = False
        else:
            print(f"  ✅ PASS – valid GRHBPKT packet")
        print()

    # --- Test tag packets for each reader (generate 3 each) ---
    separator("TAG TELEMETRY PACKETS (GRTAGDATA)")
    for reader in config.GATE_READERS:
        for i in range(3):
            packet = generate_tag_packet(reader)
            direction = packet["READPOINT"].split(".")[-1]
            num_tags = len(packet["FILE_EPCList"])
            print(
                f"Reader: {reader['id'][:8]}…  "
                f"direction={direction}  tags={num_tags}"
            )
            print(json.dumps(packet, indent=2))

            errors = validate_tag_packet(packet)
            if errors:
                print(f"  ❌ FAIL: {errors}")
                all_passed = False
            else:
                print(f"  ✅ PASS – valid GRTAGDATA packet")
            print()

    # --- Summary ---
    separator("SUMMARY")
    print(f"  Gate readers configured : {len(config.GATE_READERS)}")
    print(f"  Total EPC tags in pool  : {len(config.FILE_EPCS) + len(config.BOX_EPCS) + len(config.CART_EPCS)}")
    print(f"  Directions              : IN ({config.DIRECTION_IN_WEIGHT*100:.0f}%) / OUT ({(1-config.DIRECTION_IN_WEIGHT)*100:.0f}%)")
    print(f"  Antenna failure rate    : {config.ANTENNA_FAILURE_PROBABILITY*100:.0f}%")
    print()

    if all_passed:
        print("  🎉  All packet validations PASSED!")
        print("  You are ready to run:  python ctagent_simulator.py --demo")
    else:
        print("  ⚠️   Some validations FAILED – check errors above.")

    print()
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())