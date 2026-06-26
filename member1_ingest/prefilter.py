"""Cheap deterministic pre-filter — kills benign noise BEFORE the LLM.

INFO/DEBUG/healthcheck/heartbeat dominate these logs. Rejecting them here is what
keeps the LLM off the critical path. This runs on raw line text (it does not need
the parsed fields) and operates as a generator so the pipeline stays streaming.

Policy (Docs/Group_Roles.md):
- Reject INFO / DEBUG / healthcheck / heartbeat lines.
- Keep WARN / ERROR / FATAL / CRITICAL / Exception / panic / failed / corrupt ...
- DEFAULT ON AMBIGUOUS: KEEP. Missing a crash is worse than wasting an LLM call.

Keep wins over reject: a line tagged INFO whose body says "Exception" is KEPT, so
a mislabeled severity can't hide a real failure. Member 2 later verifies the
severity/text mismatch; the filter's job is only to not drop it.

Defaults live here and are overridable via parameters, so Member 4's config.py can
swap the keyword lists later without changing this logic.
"""

import re

#: Severity levels / keywords whose presence marks a line as benign noise.
DEFAULT_REJECT_KEYWORDS = (
    "INFO",
    "DEBUG",
    "TRACE",
    "healthcheck",
    "heartbeat",
)

#: Keywords that force a line to be kept, overriding any reject match above.
DEFAULT_KEEP_KEYWORDS = (
    "WARN",
    "WARNING",
    "ERROR",
    "FATAL",
    "CRITICAL",
    "SEVERE",
    "Exception",
    "panic",
    "failed",
    "failure",
    "fail",
    "corrupt",
    "timeout",
    "refused",
    "denied",
)


def _word_matcher(keywords):
    """Compile a case-insensitive whole-word matcher for ``keywords``.

    Word boundaries stop false hits like "INFO" inside "information" or "fail"
    inside a hostname.
    """
    if not keywords:
        # A pattern that never matches.
        return re.compile(r"(?!x)x")
    alternation = "|".join(re.escape(k) for k in keywords)
    return re.compile(r"\b(?:" + alternation + r")\b", re.IGNORECASE)


def should_keep(text, keep_keywords=DEFAULT_KEEP_KEYWORDS,
                reject_keywords=DEFAULT_REJECT_KEYWORDS):
    """Return ``True`` if ``text`` should pass the filter (reach the LLM stage).

    Order matters: keep-keywords are checked first so they override rejects, then
    reject-keywords, then the default-KEEP fallback for ambiguous lines.
    """
    keep_re = _word_matcher(keep_keywords)
    reject_re = _word_matcher(reject_keywords)
    if keep_re.search(text):
        return True
    if reject_re.search(text):
        return False
    return True  # ambiguous -> keep


def prefilter(lines, keep_keywords=DEFAULT_KEEP_KEYWORDS,
              reject_keywords=DEFAULT_REJECT_KEYWORDS):
    """Filter a stream of ``(line_number, raw_text)`` tuples.

    Yields only the tuples that survive :func:`should_keep`. The compiled
    matchers are built once and reused across the whole stream.
    """
    keep_re = _word_matcher(keep_keywords)
    reject_re = _word_matcher(reject_keywords)
    for line_number, raw_text in lines:
        if keep_re.search(raw_text):
            yield line_number, raw_text
        elif reject_re.search(raw_text):
            continue
        else:
            yield line_number, raw_text  # ambiguous -> keep
