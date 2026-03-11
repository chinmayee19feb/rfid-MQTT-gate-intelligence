"""
Anomaly Detector
=================
This is the "brain" of the AI layer.

It takes a batch of recent RFID events, builds a structured prompt,
sends it to Claude, and parses Claude's response into actionable alerts.

What kind of anomalies does it detect?
--------------------------------------
1. MISSING_IN_SCAN   — A tag was seen going OUT but never came IN.
                        Could indicate theft or a bypassed entrance.

2. MISSING_OUT_SCAN  — A tag came IN but never went OUT.
                        Could indicate the item is still inside, or
                        the OUT gate is malfunctioning.

3. RAPID_MOVEMENT    — The same tag was scanned at two different gates
                        within an impossibly short time (e.g. 5 seconds).
                        Could indicate cloned RFID tags.

4. ANTENNA_FAILURE   — A health packet shows one or more antennas
                        reporting "N" (not operational).
                        Needs maintenance attention.

5. UNUSUAL_VOLUME    — An abnormally high or low number of scans
                        at a particular gate. Could indicate a problem
                        or unusual activity.

How it works:
    events = [...]  # list of recent RFID events
    detector = AnomalyDetector()
    alerts = detector.analyze(events)
    # alerts is a list of dicts, each describing one anomaly
"""

import json
import logging
import sys
import time

import requests

import config

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("anomaly_detector")

# Colours for terminal output
RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
RESET = "\033[0m"


# ---------------------------------------------------------------------------
# The prompt template
# ---------------------------------------------------------------------------
# This is what we send to Claude along with the RFID events.
# It's structured so Claude knows exactly what to look for and how to respond.

SYSTEM_PROMPT = """You are an RFID Gate Security Analyst AI. You monitor RFID gate reader 
events in a warehouse/logistics facility and detect anomalies.

You will receive a batch of recent RFID events in JSON format. Each event is either:
- GRHBPKT (health status) — shows antenna status for a gate reader
- GRTAGDATA (tag telemetry) — shows RFID tags detected at a gate crossing

Your job is to analyze these events and identify anomalies. Look for:

1. MISSING_IN_SCAN: A tag EPC appears in an OUT event but was never seen in an IN event.
   This could indicate theft, unauthorized removal, or a malfunctioning IN gate.

2. MISSING_OUT_SCAN: A tag EPC appears in an IN event but never appears in an OUT event 
   within the analysis window. Less urgent but worth noting.

3. RAPID_MOVEMENT: The same tag EPC appears at two different gate readers within a very 
   short time (under 60 seconds). This is physically unlikely and could indicate 
   cloned RFID tags.

4. ANTENNA_FAILURE: A health packet shows one or more antennas with status "N". 
   This means the antenna is not operational and needs maintenance.

5. UNUSUAL_VOLUME: A gate reader has an unusually high or low number of events 
   compared to others. Could indicate a problem or suspicious activity.

IMPORTANT RULES:
- Only report anomalies you actually find in the data. Do NOT invent problems.
- If the data looks normal with no anomalies, say so clearly.
- Be specific: mention exact EPC codes, gate reader IDs, and timestamps.
- Keep your analysis concise and actionable.

Respond ONLY with a JSON object in this exact format (no other text):
{
  "anomalies_found": true or false,
  "anomaly_count": number,
  "alerts": [
    {
      "type": "MISSING_IN_SCAN | MISSING_OUT_SCAN | RAPID_MOVEMENT | ANTENNA_FAILURE | UNUSUAL_VOLUME",
      "severity": "HIGH | MEDIUM | LOW",
      "gate_reader_id": "the reader ID involved",
      "description": "Clear explanation of what was detected",
      "epc_codes": ["list of EPC codes involved, if applicable"],
      "recommendation": "What action should be taken"
    }
  ],
  "summary": "One paragraph summary of the overall gate activity"
}"""


ANALYSIS_PROMPT_TEMPLATE = """Analyze the following batch of {event_count} RFID events 
collected over the last {time_window} seconds from {reader_count} gate reader(s).

Events:
{events_json}

Analyze these events for anomalies and respond with the JSON format specified."""


class AnomalyDetector:
    """
    Sends RFID events to Claude API and parses anomaly alerts.

    Usage:
        detector = AnomalyDetector()
        alerts = detector.analyze(events_list)
    """

    def __init__(self):
        self.api_key = config.ANTHROPIC_API_KEY
        self.model = config.CLAUDE_MODEL
        self.max_tokens = config.CLAUDE_MAX_TOKENS

        # Track API usage for cost monitoring
        self.total_api_calls = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0

        if not self.api_key:
            logger.error(
                f"{RED}ANTHROPIC_API_KEY not set!{RESET} "
                "Run: export ANTHROPIC_API_KEY='sk-ant-your-key'"
            )

    def analyze(self, events: list[dict]) -> list[dict]:
        """
        Send a batch of events to Claude for anomaly analysis.

        Parameters:
            events: List of RFID event dicts (GRHBPKT and GRTAGDATA)

        Returns:
            List of alert dicts, each describing one anomaly found.
            Returns empty list if no anomalies or if the API call fails.
        """
        if not events:
            logger.info("No events to analyze.")
            return []

        if not self.api_key:
            logger.error(f"{RED}Cannot analyze — API key not set.{RESET}")
            return []

        # --- Build the prompt ---
        events_json = json.dumps(events, indent=2)
        reader_ids = set(e.get("GATE_READER_ID", "") for e in events)

        user_prompt = ANALYSIS_PROMPT_TEMPLATE.format(
            event_count=len(events),
            time_window=self._calculate_time_window(events),
            reader_count=len(reader_ids),
            events_json=events_json,
        )

        # --- Call Claude API ---
        logger.info(
            f"{MAGENTA}[AI]{RESET}  Sending {len(events)} events to Claude "
            f"({self.model})..."
        )

        start_time = time.time()
        response = self._call_claude_api(user_prompt)
        elapsed = time.time() - start_time

        if response is None:
            return []

        logger.info(
            f"{MAGENTA}[AI]{RESET}  Claude responded in {elapsed:.1f}s "
            f"(input: {self.total_input_tokens} tokens, "
            f"output: {self.total_output_tokens} tokens)"
        )

        # --- Parse the response ---
        alerts = self._parse_response(response)
        return alerts

    def _call_claude_api(self, user_prompt: str) -> dict | None:
        """
        Make the actual HTTP request to the Anthropic Messages API.

        This uses the REST API directly (with the requests library)
        rather than the Anthropic Python SDK, so we don't need
        an extra dependency.
        """
        url = "https://api.anthropic.com/v1/messages"

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        body = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": user_prompt}
            ],
        }

        try:
            resp = requests.post(url, headers=headers, json=body, timeout=30)

            if resp.status_code == 200:
                data = resp.json()
                self.total_api_calls += 1

                # Track token usage for cost monitoring
                usage = data.get("usage", {})
                self.total_input_tokens = usage.get("input_tokens", 0)
                self.total_output_tokens = usage.get("output_tokens", 0)

                return data

            elif resp.status_code == 401:
                logger.error(
                    f"{RED}API key invalid or expired.{RESET} "
                    "Check your ANTHROPIC_API_KEY."
                )
            elif resp.status_code == 429:
                logger.warning(
                    f"{YELLOW}Rate limited by Claude API.{RESET} "
                    "Will retry on next cycle."
                )
            else:
                logger.error(
                    f"{RED}Claude API error {resp.status_code}:{RESET} "
                    f"{resp.text[:200]}"
                )

            return None

        except requests.ConnectionError:
            logger.error(
                f"{RED}Cannot reach Claude API.{RESET} "
                "Check your internet connection."
            )
            return None
        except requests.Timeout:
            logger.error(f"{RED}Claude API timed out (30s).{RESET}")
            return None
        except Exception as exc:
            logger.error(f"{RED}Unexpected error calling Claude:{RESET} {exc}")
            return None

    def _parse_response(self, api_response: dict) -> list[dict]:
        """
        Extract the anomaly alerts from Claude's response.

        Claude should return a JSON object, but sometimes it adds
        markdown formatting or extra text. We handle that gracefully.
        """
        try:
            # Get the text content from Claude's response
            content = api_response.get("content", [])
            if not content:
                logger.warning("Empty response from Claude.")
                return []

            text = content[0].get("text", "")

            # Claude sometimes wraps JSON in ```json ... ``` blocks
            # Strip those if present
            text = text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            # Parse the JSON
            result = json.loads(text)

            # Log the results
            anomalies_found = result.get("anomalies_found", False)
            anomaly_count = result.get("anomaly_count", 0)
            summary = result.get("summary", "")
            alerts = result.get("alerts", [])

            if anomalies_found:
                logger.info(
                    f"{RED}[AI]  ⚠ {anomaly_count} anomaly(ies) detected!{RESET}"
                )
                for alert in alerts:
                    severity = alert.get("severity", "?")
                    alert_type = alert.get("type", "?")
                    description = alert.get("description", "")

                    # Colour by severity
                    if severity == "HIGH":
                        colour = RED
                    elif severity == "MEDIUM":
                        colour = YELLOW
                    else:
                        colour = GREEN

                    logger.info(
                        f"  {colour}[{severity}]{RESET} {alert_type}: "
                        f"{description}"
                    )
            else:
                logger.info(
                    f"{GREEN}[AI]  ✓ No anomalies detected — "
                    f"all gate activity looks normal.{RESET}"
                )

            if summary:
                logger.info(f"{CYAN}[AI]  Summary:{RESET} {summary}")

            return alerts

        except json.JSONDecodeError as exc:
            logger.error(
                f"{RED}Failed to parse Claude's response as JSON:{RESET} {exc}"
            )
            logger.debug(f"Raw response: {text[:500]}")
            return []
        except Exception as exc:
            logger.error(f"{RED}Error parsing Claude response:{RESET} {exc}")
            return []

    def _calculate_time_window(self, events: list[dict]) -> int:
        """
        Calculate the time span (in seconds) covered by the events.
        Uses TIMESTAMP (for health) or EVENTTIME (for tag) fields.
        """
        timestamps = []
        for event in events:
            ts = event.get("TIMESTAMP") or event.get("EVENTTIME")
            if ts:
                try:
                    timestamps.append(int(ts))
                except (ValueError, TypeError):
                    pass

        if len(timestamps) < 2:
            return 0

        # Timestamps are in milliseconds, convert to seconds
        return (max(timestamps) - min(timestamps)) // 1000

    def get_usage_report(self) -> str:
        """Return a summary of API usage for cost tracking."""
        return (
            f"API calls: {self.total_api_calls} | "
            f"Last request — input: {self.total_input_tokens} tokens, "
            f"output: {self.total_output_tokens} tokens"
        )