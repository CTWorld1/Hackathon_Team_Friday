import json
import logging
import time
from collections.abc import Mapping

import ollama

MODEL = "gemma2:2b"

logger = logging.getLogger(__name__)

# Model-level payload (what the LLM returns). The external pipeline contract
# {suggested_remediation, severity_mismatch} is derived from this in `remediate`.
FALLBACK = {
    "suggested_remediation": "investigation_required",
    "is_failure": False
}

REQUIRED_KEYS = {"suggested_remediation", "is_failure"}


def _strip_code_fences(raw: str) -> str:
    raw = raw.strip()
    if not raw.startswith("```"):
        return raw

    raw = raw.split("\n", 1)[-1]
    return raw.rsplit("```", 1)[0].strip()


def _normalize_payload(payload: object) -> dict:
    if not isinstance(payload, Mapping):
        raise ValueError("LLM output must be a JSON object")

    if set(payload.keys()) != REQUIRED_KEYS:
        raise ValueError("LLM output must contain exactly the required keys")

    remediation = payload["suggested_remediation"]
    is_failure = payload["is_failure"]

    if not isinstance(remediation, str) or not remediation.strip():
        raise ValueError("suggested_remediation must be a non-empty string")

    if not isinstance(is_failure, bool):
        raise ValueError("is_failure must be a boolean")

    return {
        "suggested_remediation": remediation.strip(),
        "is_failure": is_failure,
    }


def chat_json(messages: list[dict], model: str = MODEL, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            response = ollama.chat(
                model=model,
                messages=messages,
                format="json",
                options={"temperature": 0},
            )
            raw = response["message"]["content"]
            parsed = json.loads(_strip_code_fences(raw))
            return _normalize_payload(parsed)
        except json.JSONDecodeError:
            if attempt < retries - 1:
                time.sleep(0.5)
            continue
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("[client] Invalid LLM payload on attempt %s: %s", attempt + 1, e)
            if attempt < retries - 1:
                time.sleep(0.5)
            continue
        except ollama.ResponseError as e:
            logger.warning("[client] Ollama error on attempt %s: %s", attempt + 1, e)
            if attempt < retries - 1:
                time.sleep(1)
            continue
        except Exception as e:
            logger.warning("[client] Unexpected error on attempt %s: %s", attempt + 1, e)
            break
    return dict(FALLBACK)