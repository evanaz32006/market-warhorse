# EDGAR Phase-3 validation gate — reading notes

Companion to `edgar_validation_report.csv` (per-ticker detail) and the per-concept summary printed by
`edgar.build_validation_report`. Written 2026-08-17.

## What the gate is

Before any historical backfill, EDGAR-derived fundamentals are compared against the stored yfinance
values for the same tickers **today**. The premise: if the pipe can't reproduce a number we can already
observe, it certainly can't be trusted to reconstruct one from two years ago. A wrong tag mapping
backfilled across years is a confident, beautiful lie — plausible, internally consistent, and wrong.

## The pre-registered bar

Written down **before** the numbers were seen, in `config.PARAMS`:

| criterion | threshold | why |
|---|---|---|
| `edgar_gate_max_median_pct_diff` | < 10% | typical disagreement on a typical name |
| `edgar_gate_min_spearman` | > 0.90 | does EDGAR ORDER the universe the same way? |
| `edgar_gate_max_share_gt_100pct` | < 5% | how fat is the disagreement tail? |

Every criterion must clear. Pre-registration is the whole mechanism: it removes the room to look at a
marginal result and construct a reason it should count.

## Read `spearman`, not `pearson_ref_only`

These are fat-tailed ratios. One company with near-zero equity sends P/E or ROE to five figures and
single-handedly sets a Pearson correlation. An early gate run showed `trailing_pe` Pearson **−0.015**
alongside a perfectly healthy **3.1%** median difference — the correlation was measuring one outlier,
not the mapping. Rank correlation answers the question that matters for a percentile-ranked system:
does EDGAR sort the universe the same way? `pearson_ref_only` is retained for reference and should not
drive a decision.

## Two failure modes that are NOT mapping bugs

Both were mistaken for mapping disagreement during the 2026-08 review, and both are now controlled for.

**1. Price misalignment.** `trailing_pe`, `price_to_sales`, and `price_to_book` are market-cap based.
The cached yfinance row computed its ratio using the price on the day *it* was fetched, and the
fundamentals cache refreshes on a rolling ~1/5 per night — so a row can be several days and several
percent of price movement old. Pricing the EDGAR side at today's close compares two different days.
`_yf_row_price_basis` now prices both sides on the same day.

**2. Ingest staleness — the big one.** The EDGAR store is only as current as its last ingest. In the
2026-08 review it was last ingested 07-28 while the yfinance cache had refreshed through 08-17, so Q2
10-Q figures existed on one side only. That single difference moved:

| concept | stale store | after re-ingest |
|---|---|---|
| `return_on_equity` | 0.947 / 5.5% tail (**fail**) | 0.978 / 3.7% tail (**pass**) |
| `trailing_pe` | 0.859 Spearman (**fail**) | 0.929 (**pass**) |

**Always re-ingest immediately before running the gate.** Otherwise the gate measures ingest lag and
reports it as mapping disagreement.

## The standing lesson

An argument was constructed for why ROE's failing tail criterion didn't apply to it — that the tail was
measuring near-zero-denominator instability (9 of 25 tail names had |yfinance ROE| < 0.05) rather than
mapping disagreement. **That argument was true. It was also unnecessary**, because re-measuring on
fresh inputs made ROE pass outright.

> When a result sits near the bar, re-measure on fresh inputs BEFORE reasoning about why the bar might
> not apply. The urge to explain a marginal miss is precisely the failure mode a pre-registered bar
> exists to catch.

## Withheld concepts

`operating_margin` is computed and then dropped (`config.EDGAR_EXCLUDED_FIELDS`). It failed all three
criteria with a systematic ~9% one-directional gap across 75% of names that survived every fix,
including period alignment — a definitional difference (Yahoo's apparently-normalized operating income
vs us-gaap as-reported `OperatingIncomeLoss`), not a bug. Plausible but unverified against a third
source, so it does not enter a score. A withheld field is reported separately from a gate failure: it
has nothing to prove, and a permanently-red banner trains the reader to ignore banners. See ROADMAP.

## What the gate caught (2026-08 review)

Five pipeline bugs, two of which would have silently corrupted a two-year backfill with numbers that
look entirely reasonable:

1. **Dead-tag staleness** — filers abandon XBRL tags but the old facts live forever. First-tag-wins
   handed NVDA a 1,603-day-old revenue labelled `method="annual"`; 40 of 360 filers shared the pattern.
2. **Negative-equity rank inversion** — `debt_to_equity` is an INVERTED quality field, so Clorox's
   negative book equity (−3,711) would have ranked the most-levered name in the index as its safest.
3. `debt_to_equity` built from total Liabilities as a raw ratio rather than interest-bearing debt × 100.
4. REIT revenue read from the ASC-606 contract tag — leases are not contracts with customers, so AVB's
   revenue was a sliver of its top line and its profit margin read 160×.
5. Margin legs resolved from different periods for 51 of 507 filers.

Numbers 1 and 2 are the argument for keeping this gate on every future data source. Neither is
detectable downstream: both produce clean, plausible backfills.
