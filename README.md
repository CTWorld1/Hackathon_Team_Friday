# Raw Log Triage Pipeline (Track 2)

Turn a raw, noisy log stream into clean, validated, **webhook-ready JSON** — one
JSON object per anomalous event, ready for injection into a downstream DB/alerting
system.

The design is **hybrid**: a cheap deterministic pre-filter + regex does most of the
work, and a small local LLM (`gemma2:2b` via Ollama) is used *only* for
`suggested_remediation` and a single severity sanity-check. This keeps the pipeline
fast, streaming, and robust even when the model misbehaves or is offline.

---

## What it does

Given a log file like the HDFS sample:

```
081109 203615 148 INFO  dfs.DataNode$PacketResponder: PacketResponder 1 ... terminating
081109 210000 512 WARN  dfs.DataNode$DataXceiver: Got exception while serving blk_3 to peer
```

it emits NDJSON (one object per line) for the events worth attention:

```json
{"service_name":"dfs.DataNode$DataXceiver","timestamp":"2008-11-09T21:00:00","error_severity":"WARN","suggested_remediation":"Investigate the exception and determine the cause of service failure."}
```

- **INFO/DEBUG/healthcheck/heartbeat noise is dropped** before it ever reaches the LLM.
- **3 of the 4 fields are extracted deterministically by regex** (`service_name`,
  `timestamp`, `error_severity`); only `suggested_remediation` + a severity check
  come from the LLM.
- **Nothing is silently lost**: lines that don't match still flow through as
  `service_name="unknown"`, and events that fail validation are written to a
  dead-letter log.

---

## Workflow

```
raw log stream
   │
   ▼
[M1] reader ──► prefilter ──► parser
   │   stream lines      drop INFO/noise      regex-extract 3 fields
   ▼
Event (dict)  { raw_text, line_number, service_name, raw_timestamp, severity, message }
   │
   ▼
[M2] LLM (gemma2:2b, temp=0, stateless)
   │   in: message + severity      out: { suggested_remediation, severity_mismatch }
   │   on LLM failure → { "investigation_required", false }   (pipeline survives)
   ▼
[M3] assemble + validate (pydantic)
   │   parse timestamp → ISO 8601 · map severity → enum · apply mismatch policy
   │   on validation failure → repair retry ×1 → dead-letter
   ▼
validated event  { service_name, timestamp, error_severity, suggested_remediation }
   │
   ▼
[M4] output ──► NDJSON ──► stdout / file ──► webhook DB injection
```

The entire chain is a **streaming generator** — events flow one at a time, so memory
stays flat regardless of input size.

---

## File structure

```
Hackathon_Team_Friday/
├── shared/
│   └── interfaces.py        # Event contract (TypedDict) shared across all stages
│
├── member1_ingest/          # M1 — Ingestion, pre-filter & parsing
│   ├── reader.py            # streaming (line_number, raw_text) generator
│   ├── prefilter.py         # keyword/severity noise rejection (default: KEEP)
│   ├── parser.py            # regex → Event dict (3 deterministic fields)
│   ├── patterns.py          # SWAPPABLE compiled regex (format not hardcoded)
│   └── tests/               # test_parser.py (incl. pid-is-not-timestamp), test_prefilter.py
│
├── member2_llm/             # M2 — LLM layer (Ollama / gemma2:2b)
│   ├── client.py            # ollama wrapper: retries, JSON repair, safe fallback
│   ├── prompt.py            # remediation + severity-verify prompt (few-shot)
│   └── remediate.py         # Event → { suggested_remediation, severity_mismatch }
│
├── member3_validate/        # M3 — Schema & validation
│   ├── schema.py            # pydantic ValidatedLogEvent model
│   ├── enums.py             # SeverityEnum (DEBUG/INFO/WARN/ERROR/FATAL/CRITICAL/UNKNOWN)
│   ├── timestamp.py         # non-ISO → ISO 8601 (swappable; safe fallback)
│   ├── validator.py         # assemble M1+M2 fields, validate, mismatch policy
│   └── tests/               # test_validator.py, test_timestamp.py
│
├── member4_pipeline/        # M4 — Orchestration, CLI & output
│   ├── main.py              # CLI entry + run_pipeline() generator chain
│   ├── output.py            # NDJSON serialization (orjson)
│   ├── config.py            # model name, retries, keyword lists, paths
│   ├── deadletter.py        # append-only NDJSON log of failed events
│   └── tests/               # test_e2e.py (live-Ollama end-to-end)
│
├── Data/HDFS_2k.log         # sample input log (2000 lines)
├── Docs/Group_Roles.md      # full design, team split & per-member instructions
├── requirements.txt
└── README.md
```

---

## Setup

**Prerequisites:** Python 3.9+, and [Ollama](https://ollama.com) with the `gemma2:2b`
model for the remediation step.

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Pull and start the LLM (separate terminal)
ollama pull gemma2:2b
ollama serve                       # if not already running as a service
```

> **The LLM is optional to run.** If Ollama isn't available, the pipeline still
> produces valid output — `suggested_remediation` falls back to
> `"investigation_required"` for every event. 3 of the 4 fields don't need the LLM.

---

## How to run

One command, input file in:

```bash
python -m member4_pipeline.main Data/HDFS_2k.log
```

Options:

| Flag | Default | Meaning |
|------|---------|---------|
| `<input_file>` | *(required)* | Path to the raw log file to triage |
| `--output`, `-o` | stdout | Write NDJSON to a file instead of stdout |
| `--dead-letter` | `dead_letter.ndjson` | Where failed events are recorded |
| `--model` | `gemma2:2b` | Ollama model name |

Examples:

```bash
# Stream NDJSON to stdout, pipe into something
python -m member4_pipeline.main Data/HDFS_2k.log | jq .

# Write to a file
python -m member4_pipeline.main Data/HDFS_2k.log -o triage.ndjson
```

A run summary is printed to **stderr** (so it never pollutes the NDJSON on stdout):

```
[member4] wrote 80 event(s); 0 dead-lettered.
```

---

## Where the output goes

- **Validated events → stdout** as NDJSON (one JSON object per line), or to the
  `--output` file. Each line is a standalone, webhook-ready JSON object with exactly:
  `service_name`, `timestamp` (ISO 8601), `error_severity`, `suggested_remediation`.
- **Failed events → the dead-letter log** (`dead_letter.ndjson` by default), as NDJSON
  `{"reason": ..., "event": {...}}`. A clean run creates no dead-letter file.
- **Run summary → stderr.**

---

## Testing

```bash
# Everything (M1, M3 unit tests + M4 e2e)
python -m pytest

# A single member
python -m pytest member1_ingest
```

The end-to-end test (`member4_pipeline/tests/test_e2e.py`) calls the **real**
`gemma2:2b` and is **automatically skipped** if Ollama/the model isn't available.

---

## Related documents

- **[Docs/Group_Roles.md](Docs/Group_Roles.md)** — the full design doc: architectural
  decisions, the hybrid rationale, library choices, the 4-person team split, and
  detailed per-member instructions. Start here to understand *why* the pipeline is
  shaped this way.
- **[shared/interfaces.py](shared/interfaces.py)** — the `Event` contract every stage
  codes against (the seam that holds the system together).
- **[requirements.txt](requirements.txt)** — dependencies, annotated by owner.

---

## Design notes / gotchas

- **The pid is not part of the timestamp.** In `081109 203615 148 INFO ...`, the `148`
  is the process id, *not* part of the timestamp. The parser captures it in its own
  regex group specifically so it can be discarded — this is the #1 parsing bug and is
  tested explicitly.
- **The regex is swappable.** Production logs won't match the HDFS format. The pattern
  lives only in `member1_ingest/patterns.py` and can be swapped via config without
  touching parsing logic.
- **One type end to end.** `Event` is a `TypedDict` (a plain `dict` at runtime), so M1
  → M2 → M3 all speak dicts and M4 needs no conversion at the seam.
- **Severity mismatch policy.** If the LLM flags that an `INFO`-tagged line actually
  describes a failure, M3 escalates the severity to at least `WARN` rather than
  trusting the regex level.
```
