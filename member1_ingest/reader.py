"""Streaming line reader.

Never load the whole file into memory: iterate the file object directly so memory
stays flat regardless of input size. Yields ``(line_number, raw_text)`` tuples so
downstream stages (prefilter, parser) can carry the 1-based line number into the
final ``Event`` without re-counting.
"""


def read_lines(path, encoding="utf-8"):
    """Yield ``(line_number, raw_text)`` for each non-blank line in ``path``.

    - Streams with ``for line in f`` — the file is never read whole.
    - ``line_number`` is 1-based and counts EVERY physical line (including blanks
      that are skipped), so numbers always match the source file.
    - Trailing newline (and ``\\r``) is stripped from ``raw_text``.
    - Blank / whitespace-only lines are skipped — they are not log events.
    - Decoding errors are replaced rather than raised, so one bad byte can't kill
      the stream.
    """
    with open(path, "r", encoding=encoding, errors="replace") as f:
        for line_number, line in enumerate(f, start=1):
            raw_text = line.rstrip("\r\n")
            if not raw_text.strip():
                continue
            yield line_number, raw_text
