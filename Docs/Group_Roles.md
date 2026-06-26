# Track 2: Raw Log Triage Pipeline (Log-to-JSON)

Execution plan, team split, folder structure, and role instructions.

---

## ⚠️ Read This First — Architectural Notes

**1. Don't use the LLM as a regex engine.** A cheap deterministic pre-filter eliminates benign noise (INFO/DEBUG dominate these logs) *before* the LLM. With the **hybrid design**, regex also extracts 3 of the 4 fields, so the LLM runs on a tiny fraction of lines and only for remediation. This is what makes the pipeline fast and robust.

**2. Single-line scope.** These logs are single-line structured events (no multi-line stack traces). Each line is an independent event — which literally satisfies "each line treated independently, no interference." **No event grouper is needed.**

**3. gemma2:2b is small** — it hallucinates and emits malformed JSON. But in the hybrid design it's off the critical path for 3 fields; on LLM failure, remediation falls back to `investigation_required` and the record is still valid and useful. Validation + a 1–2 retry repair loop still applies.

---

## Decisions — Status

✅ **Language: Python.**
✅ **Output: NDJSON** (one JSON object per line).
✅ **Log shape: single-line structured events.** No multi-line stack traces in scope. **The event grouper is CUT** — see note below.
✅ **LLM role: HYBRID.** Regex extracts `service_name`, `timestamp`, `error_severity`. The LLM (gemma2:2b) only generates `suggested_remediation` and performs **one** verification check (below).
✅ **Sample logs available** — but see the ⚠️ on error coverage.

### Reference format (HDFS-style — DO NOT hardcode; production will differ)

```
081109 203615 148 INFO dfs.DataNode$PacketResponder: PacketResponder 1 for block blk_X terminating
└──┬──┘ └──┬──┘ └┬┘ └─┬┘ └──────────┬──────────┘  └──────────────┬──────────────┘
 date   time   pid  level        component                     message
yyMMdd HHmmss        ENUM      → service_name                  → message body
```

- **Timestamp is non-ISO:** `081109 203615` = `yyMMdd HHmmss`, no timezone, no millis, 2-digit year. Must be parsed to ISO 8601 (`2008-11-09T20:36:15`). The `148` after the time is the **pid, NOT part of the timestamp** — a guaranteed bug if someone parses `203615 148` as one value.
- **service_name** = the component field (`dfs.DataNode$PacketResponder`).
- **error_severity** = the level token (`INFO`/`WARN`/`ERROR`/`FATAL`) — regex-extracted, then verified by LLM.
- Write the regex to be **swappable** (in `patterns.py` / config), since production format will not match this exactly.


### "LLM verifies" — scoped

`verify` means exactly one thing: **sanity-check the regex-derived severity against the message text.** E.g., regex tagged a line `INFO` but the message contains `Exception`/`failed`/`corrupt` → LLM flags a mismatch. This is a yes/no question, which gemma2:2b handles well. Do **not** expand "verify" beyond this — broader verification on a 2B model produces noise.

---

## Libraries

| Library | Purpose |
|---|---|
| **pydantic** (v2) | JSON schema definition + validation. This is what makes output "validated." Non-negotiable. |
| **ollama** (official python client) | LLM calls. Use `format="json"` structured output to force JSON. |
| **orjson** | Fast JSON serialization for the final webhook payload. |
| **typer** *or* **argparse** | CLI entry point. (typer for clean UX, argparse to avoid a dependency.) |
| **rich** | Optional — log/progress visibility during dev. |
| **pytest** | Testing. |
| **regex** | Only if you need named groups with overlapping matches; otherwise stdlib `re` is fine. |

**Skip:** `pandas` (overkill for streaming text), `langchain` (unnecessary abstraction over a single ollama call; adds failure surface).

---

## Team Split — 4 People

> 4 is the right call. A 5th person just creates a coordination seam with nothing real to own. If you *must* do 5, split Member 4 into "validation support" and "webhook formatting" — but those are tightly coupled and 5 risks idle hands.

---

### Member 1 — Ingestion, Pre-Filter & Parsing
**Most important role.** Owns reading the stream, killing noise *before* the LLM, and regex-extracting the 3 deterministic fields.

```
member1_ingest/
├── reader.py          # streaming line reader (never load full file into memory)
├── prefilter.py       # keyword/severity noise rejection
├── parser.py          # regex-extract service_name, raw timestamp, severity, message
├── patterns.py        # SWAPPABLE compiled regex (format not hardcoded)
└── tests/
    ├── test_prefilter.py
    └── test_parser.py    # incl. the pid-is-not-timestamp trap
```

**Instructions:**
- `reader.py`: Read with a **generator** yielding lines. Never `f.read()` the whole file. Use `for line in open(path)`.
- `prefilter.py`:
  - Reject `INFO`/`DEBUG`/healthcheck/heartbeat lines.
  - Keep `WARN`/`ERROR`/`FATAL`/`CRITICAL`/`Exception`/`panic`/`failed`/`corrupt` etc.
  - **Default on ambiguous: KEEP.** Missing a crash is worse than wasting an LLM call.
- `parser.py` — extract per line, deterministically (no LLM):
  - `service_name` ← component field (e.g. `dfs.DataNode$PacketResponder`)
  - `raw_timestamp` ← date + time tokens **only** (e.g. `081109 203615`). **Do NOT swallow the pid** (the number after the time). This is the #1 parsing bug — test it explicitly.
  - `severity` ← level token
  - `message` ← remainder after the colon
  - On a line that doesn't match the pattern: emit it with `service_name="unknown"` and let it flow through — do not drop it.
- `patterns.py`: regex lives here and is **swappable via config**. Production format will differ from the HDFS sample; do not bake the sample format into logic elsewhere.
- **Output:** a generator of event objects: `{raw_text, line_number, service_name, raw_timestamp, severity, message}`.
- **No grouper.** Single-line scope — each line is its own independent event. This is what satisfies "each line treated independently, no interference."

---

### Member 2 — LLM Layer (Gemma / Ollama)
Owns model interaction. **Scope narrowed: the LLM does NOT extract the 4 fields.** It only (a) generates `suggested_remediation` and (b) verifies severity.

```
member2_llm/
├── client.py          # ollama wrapper, model="gemma2:2b"
├── prompt.py          # remediation + verification prompt templates
├── remediate.py       # event -> {suggested_remediation, severity_mismatch: bool}
└── tests/
    └── test_remediate.py
```

**Instructions:**
- `client.py`:
  - `ollama.chat(model="gemma2:2b", format="json", messages=[...])`, `options={"temperature": 0}`.
  - Timeout + max-retries wrapper. **On total LLM failure, return `{"suggested_remediation": "investigation_required", "severity_mismatch": false}`** — the pipeline must survive gemma being down, since 3 of 4 fields don't need it.
- **Concurrency:** gemma2:2b serves serially per instance. With the hybrid design the LLM runs on *far fewer* lines (only filtered anomalies), so throughput is much less of a concern. Benchmark before adding threads.
- **Non-interference:** each call sends ONLY one event's message text. No history, no context. String in, dict out, no memory. State this in code.
- `prompt.py` — the model gets the message text + the regex-derived severity, and must return JSON with exactly two keys:
  - `suggested_remediation`: one sentence, **only** from evidence in the message; if unknown → `investigation_required`.
  - `severity_mismatch`: `true` if the message text contradicts the given severity (e.g. severity says INFO but text says "Exception"/"failed"/"corrupt"), else `false`.
  - Include 2–3 few-shot examples — gemma2:2b needs them.
- **Do not let "verify" expand** beyond the severity yes/no check. Broader verification on a 2B model is noise.
- **Hard truth:** gemma2:2b will still occasionally fail. The job is *predictable* output Member 3 can validate, plus a safe fallback.

---

### Member 3 — Schema & Validation
Owns correctness of the final object. This is where "syntactically perfect JSON" is actually enforced.

```
member3_validate/
├── schema.py          # pydantic models
├── timestamp.py       # non-ISO -> ISO 8601 parser (swappable)
├── validator.py       # assemble regex+LLM fields, validate, repair/retry hook
├── enums.py           # error_severity enum
└── tests/
    ├── test_validator.py
    └── test_timestamp.py
```

**Instructions:**
- `schema.py` — pydantic model, assembled from **regex fields (M1) + LLM fields (M2)**:
  - `service_name: str` ← from M1 regex
  - `timestamp: datetime` ← from M1 `raw_timestamp`, parsed by `timestamp.py`
  - `error_severity: SeverityEnum` ← from M1, **overridden/flagged** if M2 returned `severity_mismatch=true`
  - `suggested_remediation: str` ← from M2
- `timestamp.py`: convert the non-ISO format to ISO 8601. For the HDFS sample: `strptime("%y%m%d %H%M%S")` on `081109 203615` → `2008-11-09T20:36:15`. **Must be swappable** — production format differs. If parsing fails, fall back to file ingestion time and set a flag, never crash.
- `error_severity` **must be an Enum** (`DEBUG`/`INFO`/`WARN`/`ERROR`/`FATAL`), not free text.
- **Severity-mismatch handling:** if M2 flagged a mismatch, decide policy and write it down — recommended: escalate severity to at least `WARN` and add a marker, rather than trusting the regex level. Don't silently ignore the mismatch flag; it's the whole point of the verify step.
- `validator.py`:
  - Validate the assembled object against the schema.
  - On failure, one-shot repair via M2's layer, cap retries 1–2, then **dead-letter**. Never silently drop.
- **Owns the seams.** Lock the field contract with M1 (regex fields in) and M2 (LLM fields in) and M4 (validated object out) early.

---

### Member 4 — Orchestration, CLI & Webhook Output
Owns gluing it together and the final deliverable.

```
member4_pipeline/
├── main.py            # CLI entry, wires reader->prefilter->llm->validate->output
├── output.py          # serialize to webhook-ready JSON string
├── config.py          # model name, paths, thresholds
├── deadletter.py      # failed events log
└── tests/
    └── test_e2e.py
```

**Instructions:**
- `main.py`: The pipeline is a **generator chain** — `reader → prefilter → grouper → llm → validate → output`. Keep it streaming end-to-end so memory stays flat regardless of input size. Don't break it by collecting everything into a list.
- `output.py`: Emit each validated event as a standalone JSON string (use `orjson`). "Ready for webhook injection" means one valid JSON object per event. Confirm with the DB owner: **NDJSON** (one object per line) vs **batched array**. Default to NDJSON.
- `config.py`: Centralize model string, prefilter keyword lists, retry counts. No magic numbers scattered across files.
- **Owns integration testing** with a real, messy multi-service log. Don't test only on clean synthetic data — gemma's failures show up on real noise. Source this log early.

---

## Repo Root Structure

```
log-triage/
├── member1_ingest/
├── member2_llm/
├── member3_validate/
├── member4_pipeline/
├── shared/
│   └── interfaces.py   # dataclass/Protocol contracts between stages
├── sample_logs/
├── requirements.txt
└── README.md
```

---

## The Thing That Will Actually Sink You

It won't be code — it's the **interface contracts** between members.

Define `shared/interfaces.py` **in hour one**. The two shapes everyone codes against:
- **Event (M1 → M2/M3):** `{raw_text, line_number, service_name, raw_timestamp, severity, message}`
- **Validated output (M3 → M4):** `{service_name, timestamp, error_severity, suggested_remediation}`

All four agree, then work in parallel. Skip this and you'll spend day two reconciling incompatible dict formats.

---

## Pipeline Flow Summary

```
raw log stream
   │
   ▼
[M1] reader ──► prefilter ──► parser
   │ (drops INFO/noise; regex-extracts service_name, raw_timestamp, severity, message)
   ▼
event  { raw_text, line_number, service_name, raw_timestamp, severity, message }
   │
   ▼
[M2] LLM (gemma2:2b, temp=0, format=json, stateless)
   │  in:  message + severity     out: { suggested_remediation, severity_mismatch }
   │  on failure: { "investigation_required", false }  ← pipeline survives
   ▼
[M3] assemble (regex fields + LLM fields)
   │  timestamp.py: 081109 203615 -> 2008-11-09T20:36:15
   │  apply severity_mismatch policy
   ▼
   pydantic validate ──► (repair retry ×1–2) ──► dead-letter on final fail
   │
   ▼
validated event object
   │
   ▼
[M4] output ──► NDJSON ──► webhook DB injection
```