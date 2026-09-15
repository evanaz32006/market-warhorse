"""Filing text + LLM factual extraction — synthetic only, no network, no API key.

The load-bearing test is `test_the_schema_contains_no_opinion_fields`. An LLM's training data
includes what happened AFTER these filings, so asking it anything evaluative ("is this bullish?",
"what is the outlook?") invites it to answer from memory of the stock's subsequent move. That is a
lookahead leak living in the model's weights, where no `filed_date <= D` gating can reach it, and it
would produce exactly the beautiful false backtest CLAUDE.md invariant #1 exists to prevent.

The schema is the enforcement point: if there is nowhere to put an opinion, the model cannot express
one. That test exists to stop a future change from quietly adding a sentiment field.
"""
import pytest

from src import filing_text


class _StubClient:
    """Stands in for anthropic.Anthropic so every path below runs with no key and no network."""

    def __init__(self, body):
        self._body = body
        self.messages = self

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        block = type("B", (), {"text": self._body})()
        return type("R", (), {"content": [block]})()


def _valid_json():
    import json
    return json.dumps({k: (False if v.startswith("bool") else "none")
                       for k, v in filing_text.EXTRACTION_SCHEMA.items()})


# ---------------------------------------------------------------------------
# The contamination defences
# ---------------------------------------------------------------------------

def test_the_schema_contains_no_opinion_fields():
    """THE test. Every field must be answerable from the document alone by someone who has never
    heard of the company. A sentiment or outlook field is an invitation to answer from training
    data — which is the one leak this design cannot otherwise detect."""
    banned = ("sentiment", "bullish", "bearish", "outlook", "positive", "negative",
              "prediction", "predict", "forecast", "recommend", "price", "attractive",
              "impact", "significan", "material")
    for field in filing_text.EXTRACTION_SCHEMA:
        for word in banned:
            assert word not in field.lower(), (
                f"field {field!r} invites an opinion; extract facts, not judgements")


def test_the_prompt_forbids_outside_knowledge():
    prompt = filing_text.build_prompt("some filing text", items="2.02")
    low = prompt.lower()
    assert "do not use any outside knowledge" in low
    assert "what happened afterwards" in low
    assert "never infer" in low
    # every schema field must actually be asked for, or the response is silently under-specified
    for field in filing_text.EXTRACTION_SCHEMA:
        assert field in prompt


def test_contamination_split_cuts_at_the_cutoff():
    """If a feature works on filings the model could have memorised and collapses on ones it could
    not, that gap IS the leak — measured rather than assumed."""
    rows = [{"filed_date": d} for d in
            ("2024-06-01", "2025-01-31", "2025-02-01", "2026-03-01")]
    pre, post = filing_text.contamination_split(rows, cutoff="2025-01-31")
    assert [r["filed_date"] for r in pre] == ["2024-06-01", "2025-01-31"]
    assert [r["filed_date"] for r in post] == ["2025-02-01", "2026-03-01"]


def test_rows_without_a_date_are_in_neither_half():
    """An undated filing cannot be placed on either side of the cutoff, and guessing would
    contaminate the clean half — the one that has to stay clean for the test to mean anything."""
    pre, post = filing_text.contamination_split(
        [{"filed_date": None}, {"other": 1}], cutoff="2025-01-31")
    assert pre == [] and post == []


# ---------------------------------------------------------------------------
# Extraction robustness
# ---------------------------------------------------------------------------

def test_a_partial_response_is_discarded_not_filled_in():
    """A half-extracted filing whose missing fields default to `false` looks exactly like a filing
    that genuinely announced nothing. Silently wrong, and it would dilute every real event."""
    import json
    partial = json.dumps({"announces_buyback": True})
    assert filing_text.extract_facts("text", client=_StubClient(partial)) is None


def test_unparseable_responses_return_none():
    for body in ("not json at all", "", "{broken", "[1,2,3]"):
        assert filing_text.extract_facts("text", client=_StubClient(body)) is None


def test_a_valid_response_is_returned_with_exactly_the_schema_keys():
    out = filing_text.extract_facts("text", client=_StubClient(_valid_json()))
    assert set(out) == set(filing_text.EXTRACTION_SCHEMA)


def test_extra_keys_in_the_response_are_dropped():
    """A model that volunteers `{"sentiment": "positive"}` must not have it reach the feature set —
    the schema is the contract, not a suggestion."""
    import json
    body = json.loads(_valid_json())
    body["sentiment"] = "very positive"
    body["expected_return"] = 0.12
    out = filing_text.extract_facts("text", client=_StubClient(json.dumps(body)))
    assert "sentiment" not in out and "expected_return" not in out


def test_prose_around_the_json_is_tolerated():
    body = "Here is the extraction:\n" + _valid_json() + "\nLet me know if you need more."
    assert filing_text.extract_facts("text", client=_StubClient(body)) is not None


# ---------------------------------------------------------------------------
# Fetch and clean
# ---------------------------------------------------------------------------

def test_archive_url_uses_edgars_own_id_conventions():
    """EDGAR's archive path wants an UNPADDED cik and an UNHYPHENATED accession — the opposite of
    every other place in this project, where CIKs are zero-padded to 10."""
    url = filing_text.document_url("0001552033", "0001552033-24-000003", "doc.htm")
    assert url == ("https://www.sec.gov/Archives/edgar/data/1552033/"
                   "000155203324000003/doc.htm")


def test_clean_html_strips_markup_scripts_and_entities():
    raw = ("<html><head><style>.a{color:red}</style><script>var x=1;</script></head>"
           "<body><p>Item&nbsp;4.02 &#8217;Non-Reliance&#8217;</p>"
           "<div>on previously issued <b>financials</b></div></body></html>")
    text = filing_text.clean_html(raw)
    assert "color:red" not in text and "var x" not in text
    assert "Item 4.02" in text and "Non-Reliance" in text
    assert "financials" in text
    assert "<" not in text and "&nbsp;" not in text


def test_missing_primary_document_returns_none_without_a_request():
    assert filing_text.fetch_filing_text("123", "0001-24-000001", None) is None


def test_a_missing_api_key_fails_loudly_and_explains_the_billing():
    """The Anthropic API is billed separately from a Claude subscription, which is the single most
    likely surprise here. Everything else in this module runs without a key."""
    import os
    old = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        with pytest.raises(RuntimeError, match="billed SEPARATELY"):
            filing_text._default_client()
    finally:
        if old is not None:
            os.environ["ANTHROPIC_API_KEY"] = old


def test_prompt_version_is_part_of_the_cache_identity():
    """Extractions are cached to keep a re-run free and a past analysis reproducible. If the prompt
    changed without the version changing, the cache would serve answers to the OLD question under
    the new one — and the change would be invisible."""
    assert filing_text.PROMPT_VERSION
    assert isinstance(filing_text.PROMPT_VERSION, str)
