"""Central configuration — model name, paths, thresholds, keyword lists.

No magic numbers scattered across files. Everything tunable lives here so the
pipeline can be re-pointed at a different model, format, or noise policy without
touching logic. The prefilter keyword lists are surfaced from Member 1's defaults
so there is a single source of truth that M4 can still override.
"""

from member1_ingest.prefilter import (
    DEFAULT_KEEP_KEYWORDS,
    DEFAULT_REJECT_KEYWORDS,
)

# --- LLM (Member 2) ---
MODEL = "gemma2:2b"
LLM_RETRIES = 3

# --- Validation / repair (Member 3 + 4) ---
#: Extra attempts to re-run remediation and re-validate before dead-lettering.
VALIDATION_REPAIR_RETRIES = 1

# --- Pre-filter (Member 1) noise policy ---
KEEP_KEYWORDS = DEFAULT_KEEP_KEYWORDS
REJECT_KEYWORDS = DEFAULT_REJECT_KEYWORDS

# --- Output / dead-letter ---
#: Default output is stdout (``None``); ``--output`` overrides per run.
DEFAULT_OUTPUT_PATH = None
#: Where events that fail validation after repair are recorded (never dropped).
DEAD_LETTER_PATH = "dead_letter.ndjson"
