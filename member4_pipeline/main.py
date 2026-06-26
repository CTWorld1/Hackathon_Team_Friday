"""Pipeline orchestration + CLI entry point.

Wires the whole chain as a streaming generator so memory stays flat regardless of
input size — events flow one at a time, never collected into a list::

    reader -> prefilter -> parse (M1) -> remediate (M2) -> validate (M3) -> output (M4)

Run as one command::

    python -m member4_pipeline.main <input_file> [--output out.ndjson]

Output is NDJSON to stdout by default (one webhook-ready JSON object per line);
``--output`` writes to a file instead. Events that fail validation even after a
repair attempt are recorded in the dead-letter log, never silently dropped.
"""

import sys
from pathlib import Path
from typing import Optional

import typer

from member1_ingest.reader import read_lines
from member1_ingest.prefilter import prefilter
from member1_ingest.parser import parse
from member2_llm.remediate import remediate_or_fallback
from member3_validate.validator import validate_event_for_output
from member4_pipeline import config
from member4_pipeline.deadletter import DeadLetterLog
from member4_pipeline.output import dumps_line


def run_pipeline(input_path, dead_letter, model=config.MODEL,
                 keep_keywords=config.KEEP_KEYWORDS,
                 reject_keywords=config.REJECT_KEYWORDS,
                 repair_retries=config.VALIDATION_REPAIR_RETRIES):
    """Yield validated, webhook-ready event dicts for ``input_path``.

    A generator end to end: each line is read, filtered, parsed, sent to the LLM
    for remediation, validated, and yielded — no stage buffers the whole stream.
    On a validation failure the LLM remediation is retried up to
    ``repair_retries`` times; if it still fails the event is dead-lettered.
    """
    lines = read_lines(input_path)
    kept = prefilter(lines, keep_keywords=keep_keywords, reject_keywords=reject_keywords)
    events = parse(kept)

    for event in events:
        llm = remediate_or_fallback(event)
        attempts = 1 + max(0, repair_retries)
        final = None
        last_error = None
        for attempt in range(attempts):
            try:
                final = validate_event_for_output(event, llm)
                break
            except Exception as exc:  # noqa: BLE001 - validation/repair boundary
                last_error = exc
                if attempt < attempts - 1:
                    # Repair: re-ask the LLM, then re-validate.
                    llm = remediate_or_fallback(event)
        if final is not None:
            yield final
        else:
            dead_letter.record(event, reason="validation failed: {}".format(last_error))


def main(
    input_file: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True,
                                      help="Path to the raw log file to triage."),
    output: Optional[Path] = typer.Option(None, "--output", "-o",
                                          help="Write NDJSON here instead of stdout."),
    dead_letter_path: Path = typer.Option(config.DEAD_LETTER_PATH, "--dead-letter",
                                          help="Where to record events that fail validation."),
    model: str = typer.Option(config.MODEL, "--model", help="Ollama model name."),
):
    """Triage a raw log file into webhook-ready NDJSON."""
    out_stream = open(output, "w", encoding="utf-8") if output else sys.stdout
    written = 0
    try:
        with DeadLetterLog(dead_letter_path) as dead_letter:
            for record in run_pipeline(str(input_file), dead_letter, model=model):
                out_stream.write(dumps_line(record))
                out_stream.write("\n")
                written += 1
            dead_lettered = dead_letter.count
    finally:
        if out_stream is not sys.stdout:
            out_stream.close()

    summary = "[member4] wrote {} event(s); {} dead-lettered.".format(written, dead_lettered)
    print(summary, file=sys.stderr)
    if dead_lettered:
        print("[member4] see {} for failures.".format(dead_letter_path), file=sys.stderr)


if __name__ == "__main__":
    typer.run(main)
