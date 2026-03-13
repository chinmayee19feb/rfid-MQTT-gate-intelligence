"""
Anomaly Detector
=================
This is the "brain" of the AI layer.

It takes a batch of recent RFID events, builds a structured prompt,
sends it to Claude (via Bedrock or direct API), and parses the response.

Supports two providers:
  - "bedrock"  → AWS Bedrock (uses IAM role, no API key needed)
  - "direct"   → api.anthropic.com (uses ANTHROPIC_API_KEY)

What kind of anomalies does it detect?
--------------------------------------
1. MISSING_IN_SCAN   — Tag seen going OUT but never came IN
2. MISSING_OUT_SCAN  — Tag came IN but never went OUT
3. RAPID_MOVEMENT    — Same tag at two gates impossibly fast
4. ANTENNA_FAILURE   — Health packet shows antenna down
5. UNUSUAL_VOLUME    — Abnormal scan count at a gate
"""

import json
import logging
import sys
import time

import boto3
import requests

import config

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("anomaly_detector")

RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
RESET = "\033[0m"


# ---------------------------------------------------------------------------
# The prompt template (same for both providers)
# ---------------------------------------------------------------------------

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
    Sends RFID events to Claude for anomaly analysis.
    Supports both AWS Bedrock and direct Anthropic API.
    """

    def __init__(self):
        self.provider = config.AI_PROVIDER
        self.max_tokens = config.CLAUDE_MAX_TOKENS

        # Track API usage
        self.total_api_calls = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0

        # Initialize the correct provider
        if self.provider == "bedrock":
            self._init_bedrock()
        else:
            self._init_direct()

    def _init_bedrock(self):
        """Initialize AWS Bedrock client."""
        try:
            self.bedrock_client = boto3.client(
                "bedrock-runtime",
                region_name=config.AWS_REGION,
            )
            self.model_id = config.BEDROCK_MODEL_ID
            logger.info(
                f"{MAGENTA}[AI]{RESET}  Provider: AWS Bedrock "
                f"(model: {self.model_id}, region: {config.AWS_REGION})"
            )
        except Exception as exc:
            logger.error(f"{RED}Failed to initialize Bedrock client:{RESET} {exc}")
            logger.info("Falling back to direct API...")
            self.provider = "direct"
            self._init_direct()

    def _init_direct(self):
        """Initialize direct Anthropic API."""
        self.api_key = config.ANTHROPIC_API_KEY
        self.model_id = config.DIRECT_MODEL
        if not self.api_key:
            logger.error(
                f"{RED}ANTHROPIC_API_KEY not set!{RESET} "
                "Run: export ANTHROPIC_API_KEY='sk-ant-your-key'"
            )
        logger.info(
            f"{MAGENTA}[AI]{RESET}  Provider: Direct Anthropic API "
            f"(model: {self.model_id})"
        )

    def analyze(self, events: list[dict]) -> list[dict]:
        """
        Send a batch of events to Claude for anomaly analysis.
        Routes to Bedrock or direct API based on config.
        """
        if not events:
            logger.info("No events to analyze.")
            return []

        # Build the prompt
        events_json = json.dumps(events, indent=2)
        reader_ids = set(e.get("GATE_READER_ID", "") for e in events)

        user_prompt = ANALYSIS_PROMPT_TEMPLATE.format(
            event_count=len(events),
            time_window=self._calculate_time_window(events),
            reader_count=len(reader_ids),
            events_json=events_json,
        )

        # Call the appropriate provider
        logger.info(
            f"{MAGENTA}[AI]{RESET}  Sending {len(events)} events to Claude "
            f"via {self.provider} ({self.model_id})..."
        )

        start_time = time.time()

        if self.provider == "bedrock":
            response = self._call_bedrock(user_prompt)
        else:
            response = self._call_direct(user_prompt)

        elapsed = time.time() - start_time

        if response is None:
            return []

        logger.info(
            f"{MAGENTA}[AI]{RESET}  Claude responded in {elapsed:.1f}s "
            f"(input: {self.total_input_tokens} tokens, "
            f"output: {self.total_output_tokens} tokens)"
        )

        # Parse the response
        alerts = self._parse_response(response)
        return alerts

    def _call_bedrock(self, user_prompt: str) -> dict | None:
        """
        Call Claude via AWS Bedrock.
        
        Uses the InvokeModel API with Anthropic's message format.
        No API key needed — authentication is handled by the IAM role.
        """
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": self.max_tokens,
            "system": SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": user_prompt}
            ],
        })

        try:
            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=body,
                contentType="application/json",
                accept="application/json",
            )

            # Read and parse the response body
            result = json.loads(response["body"].read())
            self.total_api_calls += 1

            # Track token usage
            usage = result.get("usage", {})
            self.total_input_tokens = usage.get("input_tokens", 0)
            self.total_output_tokens = usage.get("output_tokens", 0)

            return result

        except self.bedrock_client.exceptions.AccessDeniedException:
            logger.error(
                f"{RED}Bedrock access denied.{RESET} "
                "Check IAM permissions (AmazonBedrockFullAccess)."
            )
            return None
        except self.bedrock_client.exceptions.ValidationException as exc:
            logger.error(f"{RED}Bedrock validation error:{RESET} {exc}")
            return None
        except Exception as exc:
            logger.error(f"{RED}Bedrock error:{RESET} {exc}")
            return None

    def _call_direct(self, user_prompt: str) -> dict | None:
        """
        Call Claude via direct Anthropic API.
        Requires ANTHROPIC_API_KEY environment variable.
        """
        if not self.api_key:
            logger.error(f"{RED}Cannot analyze — API key not set.{RESET}")
            return None

        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        body = {
            "model": self.model_id,
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
                usage = data.get("usage", {})
                self.total_input_tokens = usage.get("input_tokens", 0)
                self.total_output_tokens = usage.get("output_tokens", 0)
                return data
            elif resp.status_code == 401:
                logger.error(f"{RED}API key invalid or expired.{RESET}")
            elif resp.status_code == 429:
                logger.warning(f"{YELLOW}Rate limited by Claude API.{RESET}")
            else:
                logger.error(
                    f"{RED}Claude API error {resp.status_code}:{RESET} "
                    f"{resp.text[:200]}"
                )
            return None

        except requests.ConnectionError:
            logger.error(f"{RED}Cannot reach Claude API.{RESET}")
            return None
        except requests.Timeout:
            logger.error(f"{RED}Claude API timed out.{RESET}")
            return None
        except Exception as exc:
            logger.error(f"{RED}Unexpected error:{RESET} {exc}")
            return None

    def _parse_response(self, api_response: dict) -> list[dict]:
        """
        Extract anomaly alerts from Claude's response.
        Response format is identical for both Bedrock and direct API.
        """
        try:
            content = api_response.get("content", [])
            if not content:
                logger.warning("Empty response from Claude.")
                return []

            text = content[0].get("text", "")

            # Strip markdown code fences if present
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
            return []
        except Exception as exc:
            logger.error(f"{RED}Error parsing Claude response:{RESET} {exc}")
            return []

    def _calculate_time_window(self, events: list[dict]) -> int:
        """Calculate the time span in seconds covered by the events."""
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
        return (max(timestamps) - min(timestamps)) // 1000

    def get_usage_report(self) -> str:
        """Return a summary of API usage."""
        return (
            f"Provider: {self.provider} | "
            f"API calls: {self.total_api_calls} | "
            f"Last request — input: {self.total_input_tokens} tokens, "
            f"output: {self.total_output_tokens} tokens"
        )