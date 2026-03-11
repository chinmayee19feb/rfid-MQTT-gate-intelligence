# Phase 3 – CTAgent Simulator

Simulates multiple RFID gate readers (CTAgent devices) sending data to the
middleware over HTTP, exactly as real Intellistride hardware would.

## What it sends

| Packet | Type | Frequency | Description |
|--------|------|-----------|-------------|
| Health | `GRHBPKT` | Every 15 min (30 s in demo) | Antenna status for each reader |
| Tag telemetry | `GRTAGDATA` | Every 3–15 s | EPC tags detected at a gate crossing |

## Simulated gate readers

| Reader ID | Location | Read-point prefix |
|-----------|----------|-------------------|
| `f8e375cf…` | Main entrance – Building A | `PLANT_01_DOOR_01` |
| `a1b2c3d4…` | Shipping dock – Building A | `PLANT_01_DOOR_02` |
| `1234abcd…` | Warehouse entrance – Building B | `PLANT_02_DOOR_01` |

## Quick start

```bash
# 1. Install dependency
pip install requests

# 2. Validate packets offline (no middleware needed)
python test_packets.py

# 3. Start the middleware first (in another terminal)
#    cd ../middleware && python app.py

# 4. Run the simulator in demo mode
python ctagent_simulator.py --demo
```

## CLI options

```
python ctagent_simulator.py [OPTIONS]

  --demo            Health every 30 s, tags every 2–5 s (fast for testing)
  --url URL         Middleware URL (default: http://localhost:4501)
  --max-events N    Stop after N tag events (0 = unlimited)
  --verbose         Show debug-level logs
```

## Running with Docker

```bash
# Build
docker build -t ctagent-simulator .

# Run (points to middleware container on the same Docker network)
docker run --rm --network rfid-net ctagent-simulator --demo

# Or point to a custom URL
docker run --rm ctagent-simulator --demo --url http://host.docker.internal:4501
```

## Files

| File | Purpose |
|------|---------|
| `ctagent_simulator.py` | Main simulator – generates packets and sends HTTP POST |
| `config.py` | All configuration: readers, EPC pools, timing, probabilities |
| `test_packets.py` | Offline validation – run before connecting to middleware |
| `Dockerfile` | Container build for Docker Compose integration |
| `requirements.txt` | Python dependencies |

## How it works

1. On startup, each gate reader sends an **initial health packet** immediately
2. **Health threads** (one per reader) then send `GRHBPKT` at the configured interval
3. **Tag threads** (one per reader) continuously generate `GRTAGDATA` with:
   - Random direction (60% IN / 40% OUT by default)
   - Random selection of 1–8 EPC tags from the pool
   - Random interval between events
4. Each packet is HTTP POSTed to port 4501
5. The middleware responds with an ACK (`GRHBACK` or `GRTAGDATACK`) containing an error code
6. The simulator logs colour-coded output showing packet type, reader, direction, and ACK status

## Customisation

Edit `config.py` to:
- Add/remove gate readers
- Change EPC tag pools
- Adjust timing intervals
- Change direction probability (IN vs OUT)
- Change antenna failure probability

## Expected middleware ACK codes

| Code | Meaning | Simulator behaviour |
|------|---------|---------------------|
| 4000 | Success | Green ✓ in output |
| 4001 | Validation failed | Red warning |
| 4002 | DB insert failed | Red warning |
| 4010 | Unknown | Yellow warning |

## Next phase

After confirming the simulator generates correct traffic, move on to
**Phase 4 – Claude AI anomaly detection layer**.