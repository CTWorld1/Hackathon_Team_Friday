# Track 2: Raw Log Triage Pipeline (Log-to-JSON)

Execution plan, team split, folder structure, and role instructions.

---

## ⚠️ Read This First — Two Architectural Risks

**1. Per-line independent LLM calls on gigabytes of logs is a non-starter.**
Sending every line to `gemma2:2b` independently on a 1GB log (~5–10M lines) at even 50ms/call is *days* of runtime, and 99.9% of those lines are benign noise. That uses an LLM as a regex engine and defeats the stated friction.

**Fix:** A cheap **deterministic pre-filter** must eliminate benign noise *before* the LLM sees anything. The LLM only runs on candidate anomaly lines. This is not optional.

**2. "Each line independent, no interference" conflicts with finding the crash line.**
Multi-line stack traces are a *single logical event* spanning many lines. Strict per-line independence shreds a Java/Python traceback into ~40 meaningless fragments and loses the actual root-cause line.

**Resolution:** Work at the **event level**, not the line level.
- "Independent" means *events do not share state or context across LLM calls* — each call holds no memory of any other.
- It does **not** mean cutting stack traces apart. A grouped multi-line event is the unit of independence.

**3. `gemma2:2b` is small.** It will hallucinate `suggested_remediation` and sometimes emit malformed JSON. The validation layer is load-bearing and needs a retry + repair loop. Do not treat it as a nice-to-have.

---

## Two Decisions to Make Before Anyone Writes Code

1. **Line-level vs event-level** → Pick **event-level**, or the crash root-cause line gets shredded.
2. **NDJSON vs JSON array output** → Ask the DB / webhook consumer. Default to **NDJSON** (one object per line) for streaming.

Both block downstream work. Lock them in hour one.

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

### Member 1 — Ingestion & Pre-Filter
**Most important role. Assign your strongest person.** Owns reading the stream and killing noise *before* the LLM.

```
member1_ingest/
├── reader.py          # streaming line reader (never load full file into memory)
├── prefilter.py       # regex/keyword noise rejection + severity heuristics
├── event_grouper.py   # groups multi-line stack traces into single events
├── patterns.py        # compiled regex constants
└── tests/
    └── test_prefilter.py
```

**Instructions:**
- `reader.py`: Read with a **generator** yielding lines/chunks. Never `f.read()` the whole file — that's the gigabytes trap. Use `for line in open(path)`.
- `prefilter.py`:
  - Rejection list: `INFO`, `DEBUG`, healthcheck pings, heartbeat lines.
  - Inclusion list: `ERROR`, `FATAL`, `CRITICAL`, `Exception`, `panic`, `OOMKilled`, `segfault`, traceback markers.
  - **Default on ambiguous lines: KEEP.** False negatives (missing a crash) are worse than false positives (wasting an LLM call).
- `event_grouper.py`: This resolves the per-line vs per-event conflict.
  - Detect continuation lines: leading whitespace, `at com.x.y`, `Caused by:`, `File "..."`, etc.
  - Attach them to the preceding error line as **one event**.
  - **Output of this module is the unit of "independence."**
- **Output:** a generator of candidate event objects: `{raw_text, line_number, prelim_severity}`.

---

### Member 2 — LLM Layer (Gemma / Ollama)
Owns model interaction and the prompt.

```
member2_llm/
├── client.py          # ollama wrapper, model="gemma2:2b"
├── prompt.py          # system + few-shot prompt templates
├── extractor.py       # takes one event -> raw model JSON dict
└── tests/
    └── test_extractor.py
```

**Instructions:**
- `client.py`:
  - Use `ollama.chat(model="gemma2:2b", format="json", messages=[...])`.
  - Set `options={"temperature": 0}` — you want deterministic extraction, not creativity.
  - Wrap in a timeout + max-retries handler.
- **Concurrency reality check:** `gemma2:2b` on ollama serves requests serially per model instance. Don't promise parallelism you can't deliver. If you want throughput, use a bounded `concurrent.futures.ThreadPoolExecutor` feeding ollama — but **benchmark first**, local ollama may queue anyway.
- **Non-interference guarantee:** Each call sends ONLY one event's text. No conversation history, no prior context. The function takes a string, returns a dict, holds no memory. State this explicitly in the code.
- `prompt.py` — the system prompt must:
  - (a) state the exact 4 fields,
  - (b) include 2–3 few-shot examples (`gemma2:2b` badly needs them),
  - (c) instruct output of **ONLY** JSON.
  - For `suggested_remediation`, constrain it: *"one sentence, only from evidence in the log line; if unknown, return `investigation_required`."* This curbs hallucination.
- **Hard truth:** `gemma2:2b` will sometimes still fail. The job isn't perfect output — it's *predictable* output that Member 3 can validate and reject.

---

### Member 3 — Schema & Validation
Owns correctness of the final object. This is where "syntactically perfect JSON" is actually enforced.

```
member3_validate/
├── schema.py          # pydantic models
├── validator.py       # parse model output, validate, repair/retry hook
├── enums.py           # error_severity enum
└── tests/
    └── test_validator.py
```

**Instructions:**
- `schema.py` — pydantic model:
  - `service_name: str`
  - `timestamp: datetime` (validate ISO 8601; if model returns garbage, fall back to the ingestion timestamp from Member 1)
  - `error_severity: SeverityEnum`
  - `suggested_remediation: str`
- `error_severity` **must be an Enum** (`DEBUG` / `INFO` / `WARN` / `ERROR` / `FATAL`), not free text — otherwise gemma invents "kinda bad" and the DB schema breaks.
- `validator.py`:
  - Wrap parsing in try/except.
  - On validation failure, do a **one-shot repair**: send the malformed output back through Member 2's layer with "fix this to match schema." Cap retries at 1–2, then route to a **dead-letter list**.
  - **Never silently drop failures** — that's how you lose the one crash that mattered.
- **Owns the seams.** Coordinate the interface contract with Member 2 (incoming dict shape) and Member 4 (outgoing validated object) early.

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

Define `shared/interfaces.py` (the event object shape, the validated-output shape) **in hour one**. All four agree. Then work in parallel. Skip this and you'll spend day two reconciling four incompatible dict formats.

---

## Pipeline Flow Summary

```
raw log stream
   │
   ▼
[M1] reader  ──► prefilter ──► event_grouper
   │ (drops benign noise; groups multi-line traces)
   ▼
candidate events  { raw_text, line_number, prelim_severity }
   │
   ▼
[M2] llm extractor  (gemma2:2b, temp=0, format=json, stateless per call)
   │
   ▼
raw model dict
   │
   ▼
[M3] validator  ──► pydantic schema  ──► (repair retry ×1–2 on fail) ──► dead-letter on final fail
   │
   ▼
validated event object
   │
   ▼
[M4] output  ──► NDJSON ──► webhook DB injection
```