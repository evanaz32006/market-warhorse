"""Filing TEXT — fetch, cache, and LLM factual extraction. REPORT ONLY, and unproven.

## Why this exists

The 8-K event study found nothing, but it tested **item codes** — two-digit numbers. Item 8.01 is
literally titled "Other Events" and covers a buyback, a plant fire and a lawsuit settlement alike.
A null on that says almost nothing about whether the filings' TEXT carries signal. The filings are
already indexed here with exact timestamps and document paths (`sec_filings`), so reading them is a
genuinely different experiment rather than a re-run of the same one.

## The trap this module is designed around

An LLM's training data includes what happened AFTER these filings. Ask "is this March 2025 8-K
bullish?" and the model may already know the stock doubled. **That is a lookahead leak no date
gating can catch**, because it lives in the model's weights rather than in our data pipeline — and
it would produce exactly the beautiful, false backtest CLAUDE.md invariant #1 exists to prevent.

Two defences, both structural:

1. **Extract FACTS, never forecasts.** "Does this announce a guidance cut? A buyback? An auditor
   change?" is a reading-comprehension task about the document in front of the model. "Is this
   bullish?" invites it to consult what it remembers about the company. The prompt is constrained to
   the former and the schema has no field for an opinion — see `EXTRACTION_SCHEMA`.

2. **Measure the contamination directly.** `contamination_split` cuts the sample at the model's
   training cutoff. If a feature predicts beautifully on filings the model could have memorised and
   collapses on filings it could not, that gap IS the leak, measured rather than assumed. A feature
   that works EQUALLY on both sides is the only kind worth believing.

## Cost, stated plainly

The Anthropic API is billed separately from a Claude subscription. Measured: an 8-K primary document
cleans to ~10k characters, roughly 2.5k input tokens. A 5,000-filing pilot is therefore ~13M input
tokens plus a small output. Extractions are CACHED by (accession, prompt_version, model) so a
re-run costs nothing and a past analysis stays reproducible.
"""

import json
import os
import re
import time
from datetime import datetime, timezone

import requests

from src import storage
from src.config import EDGAR, FILING_TEXT

_last_request_ts = 0.0

# Bumped whenever the prompt or schema changes. Part of the cache key, so an old extraction is never
# silently reused under a new question — the cache would otherwise make a prompt change invisible.
PROMPT_VERSION = "v1"

# FACTS ONLY. Every field is answerable from the document alone by someone who has never heard of
# the company. There is deliberately no "sentiment", "outlook" or "bullish" field: those invite the
# model to answer from memory of what the stock did next, which is the leak this module exists to
# avoid.
EXTRACTION_SCHEMA = {
    "announces_guidance_change": "bool - does the filing state a change to financial guidance?",
    "guidance_direction": "one of: raised, lowered, reaffirmed, none",
    "announces_buyback": "bool - a share repurchase authorisation or expansion",
    "announces_dividend_change": "bool - a change to the dividend",
    "announces_acquisition_or_divestiture": "bool",
    "announces_executive_departure": "bool - a named officer or director leaving",
    "announces_restructuring_or_layoffs": "bool",
    "announces_impairment_or_writedown": "bool",
    "announces_litigation_or_investigation": "bool",
    "announces_restatement": "bool - previously issued financials cannot be relied upon",
    "announces_debt_financing": "bool - new borrowing, notes, or credit facility",
    "is_routine_administrative": "bool - the filing reports only procedural matters",
}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _throttle():
    global _last_request_ts
    min_gap = 1.0 / EDGAR["max_requests_per_sec"]
    wait = min_gap - (time.monotonic() - _last_request_ts)
    if wait > 0:
        time.sleep(wait)
    _last_request_ts = time.monotonic()


# ---------------------------------------------------------------------------
# Fetch and clean
# ---------------------------------------------------------------------------

def document_url(cik, accession, primary_doc):
    """EDGAR archive path for a filing's primary document.

    The CIK is un-padded here and the accession un-hyphenated — EDGAR's archive layout, which
    differs from every other place in this project where CIKs are zero-padded to 10."""
    return "https://www.sec.gov/Archives/edgar/data/%s/%s/%s" % (
        str(int(cik)), str(accession).replace("-", ""), primary_doc)


def clean_html(raw):
    """HTML -> plain text, good enough for a reading-comprehension prompt.

    Deliberately not a parser dependency: 8-K primary documents are simple, and the alternative is
    adding a library to strip tags. Script/style blocks go first (their contents are not prose),
    then tags, then entities, then whitespace."""
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw or "")
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#8217;", "'")
    text = re.sub(r"&[a-zA-Z#0-9]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_filing_text(cik, accession, primary_doc, max_chars=None):
    """Plain text of one filing's primary document, or None. Truncated to `max_chars`.

    Truncation is from the FRONT, keeping the head of the document: an 8-K states its item and the
    substance in the first page or two, and the tail is signatures and exhibit indexes."""
    max_chars = max_chars or FILING_TEXT["max_chars"]
    if not primary_doc:
        return None
    url = document_url(cik, accession, primary_doc)
    headers = {"User-Agent": EDGAR["user_agent"], "Accept-Encoding": "gzip, deflate"}
    for attempt in range(EDGAR["max_retries"]):
        _throttle()
        try:
            resp = requests.get(url, headers=headers, timeout=EDGAR["request_timeout_sec"])
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return clean_html(resp.text)[:max_chars]
        except Exception as exc:
            wait = EDGAR["backoff_base_sec"] * (2 ** attempt)
            print("[filing_text] GET %s failed (%s), retry %d/%d in %.1fs"
                  % (url, exc, attempt + 1, EDGAR["max_retries"], wait))
            time.sleep(wait)
    return None


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def build_prompt(text, items=None):
    """The extraction prompt. Reading comprehension, not analysis.

    Three constraints carry the anti-contamination design:
      * it never names the company or the date, so there is less to recognise;
      * it asks only what the document SAYS, never what it implies or what followed;
      * it demands strict JSON of the fixed schema, so there is no room for an unprompted opinion.
    """
    fields = "\n".join("  %-42s %s" % (k, v) for k, v in EXTRACTION_SCHEMA.items())
    head = (
        "You are extracting facts from a US SEC Form 8-K filing. Answer ONLY from the text "
        "provided. Do not use any outside knowledge about the company, its industry, or what "
        "happened afterwards. If the text does not say something, the answer is false or "
        "\"none\" - never infer, never guess.\n\n"
        "Return STRICT JSON with exactly these keys and no others:\n%s\n\n" % fields)
    if items:
        head += "Reported SEC item codes: %s\n\n" % items
    return head + "FILING TEXT:\n\"\"\"\n%s\n\"\"\"\n\nJSON:" % text


def _default_client():
    """The Anthropic client, or a clear error. Kept behind a function so every other part of this
    module is testable with a stub and no key."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key or not key.strip():
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. The Anthropic API is billed SEPARATELY from a Claude "
            "subscription - get a key at console.anthropic.com. Every other part of this module "
            "(fetching, cleaning, caching, the contamination split) runs without one.")
    import anthropic
    return anthropic.Anthropic(api_key=key)


def extract_facts(text, items=None, client=None, model=None):
    """One filing -> the fact dict, or None if the response was not usable.

    Returns None rather than a partially-filled dict on a parse failure: a half-extracted filing
    silently defaulting its missing fields to `false` would look exactly like a filing that
    genuinely announced nothing."""
    model = model or FILING_TEXT["model"]
    client = client or _default_client()
    prompt = build_prompt(text, items=items)
    try:
        resp = client.messages.create(
            model=model, max_tokens=FILING_TEXT["max_output_tokens"],
            messages=[{"role": "user", "content": prompt}])
        body = "".join(getattr(b, "text", "") for b in resp.content)
    except Exception as exc:
        print("[filing_text] extraction call failed: %s" % exc)
        return None
    match = re.search(r"\{.*\}", body, re.S)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    missing = set(EXTRACTION_SCHEMA) - set(parsed)
    if missing:
        print("[filing_text] response missing fields %s - discarded" % sorted(missing))
        return None
    return {k: parsed[k] for k in EXTRACTION_SCHEMA}


# ---------------------------------------------------------------------------
# The contamination test — the reason this is an experiment and not a hope
# ---------------------------------------------------------------------------

def contamination_split(rows, cutoff=None, date_key="filed_date"):
    """Split rows into (could_have_been_memorised, definitely_not) at the model's training cutoff.

    This is the whole safeguard. An LLM's weights encode what happened after the filings it was
    trained on, and no amount of `filed_date <= D` gating in our pipeline can remove that. So the
    sample is cut at the cutoff and the SAME feature is measured on both sides:

      * works on both  -> the signal is in the document, which is the only believable outcome;
      * works only before the cutoff -> that is the leak, measured rather than assumed;
      * works only after -> almost certainly noise, since there is no mechanism for it.

    Returns (pre_cutoff, post_cutoff). Pre-cutoff results must never be reported alone."""
    cutoff = cutoff or FILING_TEXT["model_knowledge_cutoff"]
    pre = [r for r in rows if r.get(date_key) and r[date_key] <= cutoff]
    post = [r for r in rows if r.get(date_key) and r[date_key] > cutoff]
    return pre, post


def coverage_report(db_path=storage.DEFAULT_DB_PATH, cutoff=None):
    """How many 8-Ks sit each side of the cutoff — i.e. whether the contamination test is even
    possible on this sample before a single token is spent."""
    cutoff = cutoff or FILING_TEXT["model_knowledge_cutoff"]
    rows = storage.load_sec_filings(forms=["8-K", "8-K/A"], db_path=db_path)
    pre, post = contamination_split(rows, cutoff=cutoff)
    est_tokens = len(rows) * (FILING_TEXT["max_chars"] / 4)
    print("[filing_text] %d 8-K filings: %d on or before %s (model may have memorised), "
          "%d after (it cannot have)" % (len(rows), len(pre), cutoff, len(post)))
    print("[filing_text] full-sample cost estimate: ~%.1fM input tokens" % (est_tokens / 1e6))
    if len(post) < FILING_TEXT["min_post_cutoff_filings"]:
        print("[filing_text] WARNING: only %d post-cutoff filings — too few to detect "
              "contamination, so a positive result here could not be trusted" % len(post))
    return {"total": len(rows), "pre_cutoff": len(pre), "post_cutoff": len(post),
            "cutoff": cutoff, "est_input_tokens": est_tokens}
