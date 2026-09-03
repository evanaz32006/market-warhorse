"""AI brief — an optional plain-English summary of the day's journal entry.

A LENS on the tool, not a signal. It adds ZERO edge and must never introduce a recommendation
or any buy/sell language beyond what the data already says. If the Anthropic API isn't usable
(no key, package not installed, network/API error), the brief is skipped with a one-line note
and the run completes normally — the journal MUST NOT depend on the brief.

Cost guard: at most one API call per run_date (this module is called once per run, and the
journal entry it summarizes is itself idempotent per run_date).
"""

import os

from src import journal, storage
from src.config import PARAMS

BRIEF_MODEL = "claude-sonnet-4-6"   # per spec — a small, cheap summary model
BRIEF_MAX_TOKENS = 400              # a few hundred tokens out; this is a short summary
BRIEF_TIMEOUT_SEC = 30

SYSTEM_PROMPT = (
    "You are the daily analyst for a self-evaluating stock-ranking research system. "
    "Summarize today's run in under 200 words of plain English for the owner: what ran, "
    "anything that failed or warrants attention, how the live validation of the v0.2 "
    "fundamental factors is progressing, and any notable IC drift. Be factual and unhyped. "
    "This is a research instrument; never phrase anything as a buy/sell recommendation."
)


def _api_key():
    key = os.environ.get("ANTHROPIC_API_KEY")
    return key.strip() if key and key.strip() else None


def generate_brief(entry, api_key=None, model=BRIEF_MODEL):
    """Call the Claude API to summarize one structured journal entry. Returns
    (brief_text_or_None, note). Degrades gracefully on every failure mode:
    - no API key                -> (None, "brief skipped — no API key")
    - anthropic not installed   -> (None, "brief skipped — anthropic package not installed")
    - API/network error/timeout -> (None, "brief skipped — API error: ...")
    Never raises; the caller's run must survive a failed brief."""
    key = api_key or _api_key()
    if not key:
        return None, "brief skipped — no API key"

    try:
        import anthropic  # imported lazily so a missing package can't break import of this module
    except ImportError:
        return None, "brief skipped — anthropic package not installed"

    import json
    user_content = (
        "Here is today's structured journal entry as JSON. Summarize it per your instructions.\n\n"
        + json.dumps(entry, indent=2, default=str)
    )

    try:
        client = anthropic.Anthropic(api_key=key, timeout=BRIEF_TIMEOUT_SEC)
        response = client.messages.create(
            model=model,
            max_tokens=BRIEF_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        text = next((b.text for b in response.content if getattr(b, "type", None) == "text"), "")
        text = text.strip()
        if not text:
            return None, "brief skipped — empty response from API"
        return text, "brief generated"
    except Exception as e:  # any anthropic error, timeout, or unexpected failure — never fatal
        return None, f"brief skipped — API error: {e}"


def run_brief(entry, run_context, db_path=storage.DEFAULT_DB_PATH, output_dir=None):
    """Generate the brief for `entry`, persist it onto the day's journal row, and regenerate
    DAILY_LOG.md so the brief appears at the top of that entry. Called after run_journal. Safe
    to call unconditionally — it self-skips when the API isn't usable and logs why. Returns the
    brief text or None."""
    output_dir = output_dir or os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
    model_version = run_context.get("model_version") or PARAMS["model_version"]
    run_date = run_context.get("run_date")

    brief_text, note = generate_brief(entry)
    print(f"[brief] {note}")

    if brief_text is None:
        return None  # journal entry already stands on its own; nothing more to do

    storage.update_journal_brief(run_date, model_version, brief_text, db_path=db_path)
    log_path = os.path.join(output_dir, "DAILY_LOG.md")
    try:
        with open(log_path, "w", encoding="utf-8") as fh:
            fh.write(journal.render_daily_log(storage.load_all_journal_entries(db_path)))
    except OSError as e:
        print(f"[brief] warning: brief saved to DB but DAILY_LOG.md rewrite failed: {e}")
    return brief_text
