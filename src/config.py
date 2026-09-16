# All tunable values live here so every threshold/window is auditable in one place.
# Nothing in features.py, data.py, storage.py, or scoring.py should hardcode a number
# that belongs in one of these dicts.
#
# SECRETS AND PERSONAL DATA DO NOT LIVE HERE. They come from the environment, optionally via a
# local `.env` that is gitignored, so this file stays safe to publish. `.env.example` documents
# what to set. The loader below is ten lines rather than a python-dotenv dependency, and it never
# overwrites a variable the real environment already defines - an explicitly exported value must
# always win over a file on disk.

import os


def _load_dotenv(path=None):
    """Read KEY=VALUE lines from `.env` into os.environ, without clobbering the real environment."""
    path = path or os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()

# SEC REQUIRES a descriptive User-Agent carrying a real contact address, and will block a generic or
# absent one. It is therefore genuinely mandatory AND genuinely personal, which is exactly the
# combination that should not sit in a published file. Set SEC_CONTACT_EMAIL in .env.
SEC_CONTACT_EMAIL = os.environ.get("SEC_CONTACT_EMAIL", "").strip()
SEC_USER_AGENT = "market-warhorse research (contact: %s)" % (SEC_CONTACT_EMAIL or "UNSET")


def require_sec_contact():
    """Fail loudly before any SEC request if no contact is configured.

    SEC blocks on a missing contact, and a block is indistinguishable from "this company has no
    filings" once the fail-soft handlers swallow it - so this is checked up front rather than
    diagnosed later from an empty ingest."""
    if not SEC_CONTACT_EMAIL:
        raise RuntimeError(
            "SEC_CONTACT_EMAIL is not set. SEC requires a real contact address in the User-Agent "
            "and blocks requests without one. Copy .env.example to .env and fill it in.")


PARAMS = {
    # PROMOTED 2026-08-21 from v0.3_sector_neutral. v0.5 is the same scoring logic as v0.3/v0.4 -
    # identical weights, identical sector-neutral ranking, EDGAR point-in-time fundamentals - run over
    # a ~3x wider universe (S&P 500 + 400 + 600, 1,527 names). It carries 542 backfilled dates with
    # 97% fundamentals coverage, where v0.3 had 34 live dates and no backfillable fundamentals.
    #
    # SCORES ARE NOT BACKWARD-COMPARABLE ACROSS THIS BOUNDARY. A percentile is a rank against peers,
    # and the peer set tripled: a value_percentile of 80 under v0.5 means "top 20% of ~1,500", under
    # v0.3 it meant "top 20% of ~500". Every prior version stays frozen and untouched under its own
    # version string for side-by-side comparison; nothing is rewritten.
    # v0.6 (2026-09-16): the LIVE row is finally the SAME MODEL as the BACKFILLED row. Under v0.5
    # one version string covered two different models — see LIVE_PIT_MODEL_VERSION below for the
    # measured evidence. Nothing about the scoring formula changes; only where the live path gets
    # its fundamentals. v0.5 stays frozen and untouched.
    "model_version": "v0.6_live_pit_fundamentals",

    # Trend / moving averages
    "sma_windows": [20, 50, 200],

    # Momentum return windows (in trading days)
    "return_windows": [1, 5, 10, 20, 60, 120, 252],

    # Relative-strength windows vs benchmark
    "rs_windows": [5, 20, 60, 120],

    # Volume/behavior
    "volume_avg_windows": [20, 60],
    "high_volume_ratio_threshold": 1.5,  # used by high_volume_up/down_days_20d
    "up_down_volume_cap": 10.0,
    "close_position_weak_threshold": 0.35,
    "close_position_strong_threshold": 0.65,

    # Risk
    "atr_window": 14,
    "volatility_windows": [20, 60],
    "downside_volatility_window": 20,
    "max_drawdown_windows": [20, 60],
    "trading_days_per_year": 252,  # for annualizing volatility (x sqrt(252))
    "week52_window": 252,

    # Setup flags
    "near_20d_high_pct": 0.98,   # within 2% of 20-session high
    "near_60d_high_pct": 0.97,   # within 3% of 60-session high
    "pullback_min_pct": 3.0,     # pullback_above_SMA50: 3%-10% below 20d high
    "pullback_max_pct": 10.0,
    "failed_breakout_lookback_days": 5,
    "failed_breakout_threshold_pct": 3.0,
    # extended_flag = close_vs_SMA20_pct > extended_pct (per spec).
    "extended_pct": 15.0,

    # Benchmark / market regime
    "benchmark_return_windows": [20, 60],
    "benchmark_volatility_window": 20,
    "benchmark_vol_high_percentile": 80,
    "benchmark_vol_trailing_window": 252,

    # yfinance fetch behavior
    "fetch_period": "2y",
    "yfinance_batch_size": 8,
    "yfinance_batch_delay_sec": 1.5,
    "yfinance_max_retries": 3,
    "yfinance_backoff_base_sec": 2.0,

    # --- v0.2 fundamentals + short interest (live runs only; never backfilled) ---
    # Ticker.info / get_shares_full calls are per-ticker and the most rate-limit-prone, so
    # they reuse the same throttle and are cached aggressively. A cached fundamentals row is
    # reused (no refetch) until it is older than this many days, since these fields move slowly.
    "fundamentals_refresh_days": 5,
    "fundamentals_fetch_delay_sec": 1.5,  # pause between per-ticker .info calls
    # Next-earnings dates: same rolling-slice discipline as fundamentals. Previously fetched per ticker
    # per run with NO cache and NO throttle (519 raw requests/night against Yahoo's ~360/hr soft limit);
    # that was the most likely route to an IP block, which would stop data collection entirely.
    # A scheduled earnings date rarely moves, and only matters within ~5 days of the event, so a 5-day
    # TTL costs nothing in accuracy.
    "earnings_refresh_days": 5,
    "earnings_fetch_delay_sec": 1.5,
    # Warn (never crash) if more than this fraction of the scored universe is missing a given
    # fundamental field on a live run — signals a data-source problem worth knowing about.
    "fundamental_sparse_warn_pct": 0.40,

    # Analyst estimate revisions — how many nights to spread one pass over the universe across.
    # 5 means ~1/5 of the names are asked each night (~300 requests at current size), which keeps the
    # run well inside Yahoo's ~360/hr soft limit. Thinner sampling costs less here than it would
    # elsewhere because one observation carries its own 90-day trail (eps_7d_ago..eps_90d_ago).
    "estimates_refresh_days": 5,

    # Macro / regime (src/macro.py). A macro reading older than this goes MISSING rather than being
    # carried forward: a series that stopped publishing must not keep supplying a stale value as if
    # it were current. 7 calendar days covers a holiday week without tolerating a dead series.
    "macro_max_staleness_days": 7,
    # Minimum observations before an EXPANDING percentile is allowed to define a regime. 252 ~ one
    # trading year; below that a "high VIX" label is noise dressed as a regime.
    "macro_min_regime_history": 252,

    # How many still-maturing FROZEN versions to recompute per nightly run, oldest-first. A frozen
    # version keeps gaining evaluable rows until its newest snapshot has matured at the longest
    # horizon, so "frozen" cannot mean "never recomputed" without pinning its metrics (see the
    # CORRECTION note in evaluation.run_evaluation). Recomputing them all costs ~8 min/run at current
    # sizes; 1 per night bounds that to ~60s while rotating through them.
    "eval_frozen_refresh_per_run": 1,

    # Regime-vigilance: trailing window (in distinct LIVE, non-backfilled run_dates) over which
    # a "recent" component IC is computed alongside full-history IC, to surface factor decay.
    "regime_recent_live_days": 60,

    # --- Daily-log (journal_v2) presentation thresholds ---------------------------------------
    # These govern ONLY how the daily log renders; they never touch a scoring/evaluation value.
    # Starting priors — adjust as live data accrues.
    # Section 4b: a component's recent-window IC is flagged as "drifting" once it moves at least
    # this far from its full-history IC (both must be present + recent n sufficient). Descriptive
    # only, never auto-applied. Moved here from a hardcoded constant in journal.py (invariant #3).
    "ic_drift_flag_threshold": 0.05,
    # Section 2: a matured cohort with fewer than this many graded names is labelled low-confidence.
    "cohort_low_confidence_min_n": 30,
    # Section 3: a cumulative Strong/Weak bucket with fewer than this many names shows "n/a" rather
    # than a hit rate computed on too little data.
    "scoreboard_min_bucket_n": 20,
    # Section 4a: below this many evaluable rows, a new factor's live IC prints "too early (n=X)"
    # instead of a misleading number.
    "factor_ic_min_n": 20,

    # --- Cross-sectional decile / top-N reporting (daily, into performance_review.csv) ----------
    # Full-universe IC measures rank correlation across all ~519 names; a human trades ~3. Those are
    # different objectives and the existing metrics cannot tell them apart. Deciles are assigned
    # WITHIN EACH DAY (never pooled across dates — that mixes regimes and reproduces the bucket-
    # imbalance problem the fixed 80/65/50 score bands already have).
    "decile_count": 10,
    "decile_min_names_per_day": 30,        # below ~3 names/decile a decile is noise, not a decile
    "decile_min_days": 20,                 # fewer contributing days than this -> reported but flagged
    "top_n_selection_sizes": [3, 10, 25],  # 3 = what a human would actually hold; 25 = a diversified read
    "performance_review_min_sample_size": 5,   # was a literal default in build_performance_review

    # --- Signal decay curve (research only, `--research decay`) ---------------------------------
    # The 5/20/60/120 horizons were chosen by guess. This measures where IC actually peaks, i.e. the
    # natural holding period, by computing IC at EVERY horizon 1..N.
    "decay_max_horizon": 250,              # one trading year; beyond that it is not a swing trade
    "decay_min_names_per_day": 30,
    "decay_min_days": 60,                  # below this many contributing cross-sections, flag as thin
    "decay_date_stride": 1,                # 1 = every run_date. >1 = deterministic every-k-th, stamped in output
    "decay_common_panel_max_horizon": 120, # the strictly-comparable panel intersects over h <= this

    # --- Walk-forward IC-weighted composite (research only, REPORT ONLY — never deployed) --------
    "wf_horizons": [5, 20, 60, 120],
    "wf_train_mode": "expanding",          # a 126-date ROLLING window yields ZERO h=120 OOS dates today
    "wf_train_window_run_dates": 126,      # only consulted when wf_train_mode == "rolling"
    "wf_train_min_run_dates": 60,          # below this many MATURED cross-sections a trailing IC is noise
    "wf_refit_every_run_dates": 21,        # monthly; weights that move daily are fitting noise
    "wf_ic_ratio_min_dates": 20,           # IC_std needs this many daily ICs to mean anything
    "wf_min_component_ic_days": 20,        # a component below this gets weight 0 and is flagged, never imputed
    "wf_negative_ic_policy": "clip_to_zero",   # explicit; "allow_negative" is deliberately NOT implemented
    "wf_min_oos_dates": 60,                # below this, report "insufficient OOS history", not a number
    # Regression-fitted variants (Job 3). Ridge must be regularized hard: ~17 correlated components
    # against a few hundred effective observations is exactly where an unpenalized fit puts large
    # offsetting weights on collinear momentum terms and reports the noise as signal.
    "wf_ridge_alpha": 50.0,
    "wf_min_regression_rows": 500,         # below this many (name, date) rows, no fit is attempted
    "wf_variants": ["ic_mean", "ic_ratio", "ridge", "nnls"],

    # --- Portfolio backtest (research only, `--research backtest`) ------------------------------
    # The tool has always reported IC and hit rates; it has never simulated an ACCOUNT. IC says
    # "the ranking is informative"; an equity curve says "here is what would have happened to the
    # money, after costs". Those are different claims and only the second one is tradeable.
    "backtest_top_n": [10, 20, 30],          # sweep: how many positions actually maximizes risk-adj return
    "backtest_hold_days": [20, 60, 120],     # sweep: how long to hold, in trading sessions
    "backtest_score_column": "score_60d",    # the composite ranked on; 60d is where signal exists
    "backtest_initial_equity": 100_000.0,
    # Fill at the NEXT session's OPEN. Filling at date D's close is a look-ahead: D's close is an
    # input to D's score, so you cannot both use it to decide and trade at it.
    "backtest_fill_policy": "next_open",
    "backtest_exclude_illiquid": True,       # a name you cannot fill does not belong in an equity curve
    # Cost model, zero commission. Spread widens as liquidity falls; impact follows the standard
    # square-root participation law. Coefficients are deliberately conservative (i.e. pessimistic):
    # an over-stated cost that still leaves an edge is a safer error than an under-stated one.
    "backtest_spread_base_bps": 1.0,         # floor for a mega-cap
    "backtest_spread_liquidity_coef": 12.0,  # bps added per 1/sqrt($M ADV)
    "backtest_spread_min_bps": 1.0,
    "backtest_spread_max_bps": 80.0,         # cap; beyond this the name is untradeable, not expensive
    "backtest_impact_coef_bps": 10.0,        # impact_bps = coef * sqrt(trade$ / ADV$)
    "backtest_adv_window": 20,               # sessions of dollar volume averaged for ADV
    "backtest_participation_cap": 0.10,      # never model taking >10% of a day's volume
    # A single-day move this large with no corporate action is almost certainly an unadjusted split
    # leaking into the cache (new bars arrive adjusted, cached pre-split rows are never re-adjusted).
    "backtest_suspicious_return_pct": 50.0,
    "backtest_risk_free_rate": 0.0,          # Sharpe vs zero; stated rather than assumed

    # --- Conditional-pattern test harness (research only, `--research patterns`) ----------------
    # Answers "after condition X, does outcome Y happen?" as a QUERY rather than a build, so a
    # hypothesis costs minutes instead of a day. Everything here is about not fooling ourselves:
    # seasonality is the most data-mined corner of finance and a harness that makes testing cheap
    # ALSO makes false discovery cheap. The multiple-comparisons machinery below is not optional
    # decoration — it is the reason this harness is allowed to exist.
    "pattern_min_history": 60,             # sessions of expanding history before a percentile condition may fire
    "pattern_min_triggers": 20,            # below this many trigger days, report the row but never call it a finding
    # HARD FLOOR for inference, and the harness caught its own need for it on the very first real
    # run: "SPY down 5 days in a row" fired exactly TWICE in 554 sessions, both times followed by a
    # gain, which produces a two-point standard deviation, a t-statistic of 185, and a family-level
    # "SIGNAL" verdict built on two coin flips. Below this many INDEPENDENT observations a row is
    # still reported descriptively but gets no t, no p, and no vote in the family correction —
    # a std estimated from a handful of points is arithmetic, not evidence.
    "pattern_min_effective_n": 5,
    "pattern_horizons": [1, 5, 10, 20],    # forward sessions measured after each trigger
    "pattern_alpha": 0.05,                 # per-test two-sided significance, BEFORE any correction
    "pattern_fdr_q": 0.10,                 # Benjamini-Hochberg false-discovery rate for the family
    # White's-Reality-Check-style family null: circularly shift the WHOLE condition system against
    # the outcomes and record the family's max |t|. One shared offset per replication, deliberately —
    # independent shifts would destroy the correlation between patterns and inflate the null.
    "pattern_permutations": 500,
    "pattern_perm_seed": 20260909,         # fixed so a reported p-value is reproducible to the digit
    # z(0.975) + z(0.80) = 1.96 + 0.84. Multiplies std/sqrt(effective_n) to give the smallest effect
    # this sample could detect at 80% power — the column that turns "no signal" into "no signal
    # DETECTABLE with this much data", which with 554 sessions is usually the honest reading.
    "pattern_power_z": 2.80,
    "pattern_oos_split": 0.6,              # chronological; first 60% in-sample, last 40% held out

    # A live day whose scored-ticker count falls below this fraction of the trailing norm is
    # INCOMPLETE, not merely quiet. Recovery only looks for sessions with ZERO snapshots, so a day
    # that scored 945 of 1,521 names reads as "present" and is never revisited — while its
    # sector-neutral percentile ranks were computed on 62% of the universe. Observed 2026-09-10,
    # when a run fired before Yahoo had published end-of-day bars for the whole universe.
    "min_live_coverage_fraction": 0.90,
    "live_coverage_lookback_days": 30,     # sessions of trailing history the norm is taken from

    # --- Database backup ---------------------------------------------------------------------
    # data/market_data.db is PARTIALLY IRREPLACEABLE: `fetch_period` is 2y, so yfinance no longer
    # serves bars from before the rolling two-year window, while the cache holds history from
    # 2024-06-24. Everything older than that window exists in exactly one place — this file.
    # Default destination is deliberately INSIDE the repo folder only as a fallback; a real backup
    # belongs on a different physical device, which is why the path is a CLI argument.
    "backup_dir": "backups",

    # The horizon the daily log RANKS AND DISPLAYS on.
    #
    # Was 20d, chosen when the horizons were a guess. Measured on the expanded universe, the
    # composite's top-decile-minus-bottom-decile spread is -0.1% at 20d and +6.6% at 120d, and the
    # top-10 basket beats the average stock by -0.3% at 20d versus +10.6% at 120d. The daily list
    # was therefore showing the owner the one horizon where the model demonstrably does nothing,
    # every single day, which is most of why it read as useless.
    #
    # Every horizon is still scored, stored and graded - this changes what leads the display, not
    # what is computed. Read it as an honest relabelling: this is a ~6-month tool that had been
    # presenting itself as a 3-week one.
    "display_horizon_days": 120,

    # --- Sector timing (research only, `--research sectortiming`) --------------------------
    # A sector's breadth reading is only meaningful with enough constituents behind it. SMH has
    # ~40 names and XLRE ~30; below this many SCORED names on a date the fraction is noise.
    "sector_timing_min_constituents": 8,

    # --- Shared research plumbing ---------------------------------------------------------------
    "calendar_ticker": "SPY",              # the ONE master session calendar (was a literal in journal.py)
    "research_output_dir": "output/research",

    # --- v0.4 EDGAR point-in-time resolution ---------------------------------------------------
    # A filer can ABANDON an XBRL tag (NVDA stopped tagging RevenueFromContractWithCustomer... after
    # FY2022 and switched to Revenues). The resolver therefore picks the FRESHEST candidate across a
    # concept's whole tag chain, and refuses anything older than this — a company that has genuinely
    # stopped reporting must SIT OUT, never contribute an ancient number dressed up as current.
    # 550 days ~= 18 months: comfortably past a late annual filing, well short of a dead tag.
    "edgar_max_data_age_days": 550,
    # TTM roll-forward (annual + current-YTD - prior-year-YTD) is only valid when the two YTD legs
    # cover the SAME span. A 3-month current minus a 9-month prior-year silently undercounts by half
    # a year. Legs whose durations differ by more than this many days -> the concept goes missing.
    "edgar_ttm_span_tolerance_days": 20,
    # A margin divides one FLOW by another (operating income / revenue). Both legs must describe the
    # SAME twelve months, or the ratio is a category error — an annual revenue to Dec-31 over a TTM
    # operating income to Mar-31 blends two different windows and reads as a real number. 51 of 507
    # filers resolved misaligned legs, a milder version of the bug that gave NVDA a 603% margin.
    # Legs whose period_end differ by more than this -> the ratio sits out (20d absorbs 52/53-week years).
    "edgar_ratio_period_tolerance_days": 20,

    # --- v0.4 Phase-3 validation gate: the PRE-REGISTERED pass bar ------------------------------
    # Written down BEFORE looking at the numbers, so a marginal result can't be rationalised into a
    # pass. Every compared concept must clear all three or the backfill does not run.
    "edgar_gate_max_median_pct_diff": 10.0,   # median abs % diff vs the yfinance cache
    "edgar_gate_min_spearman": 0.90,          # rank correlation (Pearson on fat-tailed ratios lies)
    "edgar_gate_max_share_gt_100pct": 0.05,   # share of tickers off by >100%

    # --- v0.3 sector-neutral value/quality ranking ---
    # Minimum number of tickers WITH the composite's data present that a sector must have before
    # value/quality are ranked within that sector. Below this, those names fall back to
    # cross-sectional ranking (flagged sector_rank_fallback) rather than ranking within a
    # meaninglessly small peer group.
    "sector_min_tickers_for_neutral": 8,

    # S&P 500 universe expansion
    "sp500_source_url": "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv",
    "sp500_cache_path": "data/sp500_constituents.csv",
    "sp500_fetch_timeout_sec": 10,

    # --- v0.5 universe expansion: mid- and small-cap indices -----------------------------------
    # The 5-40d signal band measured empty, but ONLY on S&P 500 names - the most-watched, most
    # arbitraged segment there is. Whether that band is empty because of the market or because of
    # the sample is the question this expansion exists to answer. S&P 400+600 rather than the
    # Russell 2000: same GICS taxonomy the pipeline already speaks, stable sources, far less index
    # turnover (which is also less survivorship bias).
    "index_fetch_timeout_sec": 25,
    "index_fetch_user_agent": SEC_USER_AGENT,
    # Liquidity. Small caps include names that cannot absorb a real order; a backtest that trades
    # them is fiction. Measured, FLAGGED, and never silently dropped - the row is still scored and
    # stored, only the portfolio simulation excludes it.
    "min_dollar_volume_20d": 2_000_000.0,   # $2M/day median floor; below this, fills are aspirational
}

# GICS Sector -> default benchmark ETF, used by src/universe.py to assign a benchmark to
# any S&P 500 ticker not already hand-assigned in watchlist.csv. Semiconductor sub-industries
# override this map (see universe.assign_benchmark); anything not covered here falls back to
# SPY. Kept here, not hardcoded in universe.py, per CLAUDE.md invariant #3.
SECTOR_BENCHMARK_MAP = {
    "Information Technology": "QQQ",
    "Energy": "XLE",
    "Financials": "XLF",
    "Health Care": "XLV",
    "Industrials": "XLI",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Utilities": "XLU",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}

# GICS Sub-Industry values that should map to SMH instead of their sector's default
# (Information Technology -> QQQ), since semiconductors behave differently from
# software/services. Verified against the live source as the exact two values in use.
SEMICONDUCTOR_SUB_INDUSTRIES = {"Semiconductors", "Semiconductor Materials & Equipment"}

# Constituent sources per index. Each yields Symbol / GICS Sector / GICS Sub-Industry, which is what
# assign_benchmark already consumes - so mid/small caps flow through the existing sector logic
# unchanged. "kind" selects the parser: a plain CSV, or the first HTML table carrying both a Symbol
# and a GICS Sector column.
INDEX_SOURCES = {
    "sp500": {
        "url": PARAMS["sp500_source_url"],
        "kind": "csv",
        "cache_path": "data/sp500_constituents.csv",
        "size_bucket": "large",
    },
    "sp400": {
        "url": "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
        "kind": "html",
        "cache_path": "data/sp400_constituents.csv",
        "size_bucket": "mid",
    },
    "sp600": {
        "url": "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",
        "kind": "html",
        "cache_path": "data/sp600_constituents.csv",
        "size_bucket": "small",
    },
}

# Benchmark per SIZE BUCKET, used when no size-appropriate SECTOR ETF exists.
#
# An honest limitation, stated where it is implemented: complete, liquid sector ETF families exist
# ONLY for large caps (the XL* SPDRs track S&P 500 sectors). There is no mid- or small-cap
# equivalent. So large caps keep their sector benchmark while mid/small get a broad size benchmark,
# which means large-cap relative strength is SECTOR-relative and mid/small is SIZE-relative.
#
# That asymmetry would confound a large-vs-small comparison of short-horizon signal - the very thing
# v0.5 is built to measure. The decay comparison therefore uses ONE COMMON benchmark per size bucket,
# which makes the comparison exactly invariant to the choice: a cross-sectional rank correlation
# computed within a group cannot be changed by subtracting a per-date constant every member shares.
SIZE_BUCKET_BENCHMARK = {
    "large": "SPY",
    "mid": "IJH",     # iShares Core S&P Mid-Cap
    "small": "IJR",   # iShares Core S&P Small-Cap
}

# Buckets whose names are benchmarked by SIZE rather than by sector (see the note above).
SIZE_BENCHMARKED_BUCKETS = {"mid", "small"}

# --- v0.2 fundamentals + short interest -------------------------------------------------
# Raw fields pulled from yfinance Ticker.info (latest available, point-in-time as of fetch —
# NOT historical, so they apply to live runs only and are never reconstructed for backfill).
# This single list keeps data.py (fetch), storage.py (cache + snapshot columns) and
# features.py (cleaning) in sync. Order is informational only.
FUNDAMENTAL_FIELDS = [
    # valuation (lower = cheaper)
    "trailing_pe", "forward_pe", "price_to_sales", "price_to_book", "ev_to_ebitda",
    # quality (margins/returns higher better; leverage lower better)
    "profit_margin", "operating_margin", "return_on_equity", "debt_to_equity", "current_ratio",
    # growth (context for now; not yet in a component)
    "earnings_growth", "revenue_growth",
    # short interest
    "short_percent_of_float", "short_ratio",
]

# Mapping from our field name -> the key yfinance exposes in Ticker.info. Kept explicit so a
# yfinance key rename is a one-line config fix, not a hunt through data.py.
FUNDAMENTAL_INFO_KEYS = {
    "trailing_pe": "trailingPE",
    "forward_pe": "forwardPE",
    "price_to_sales": "priceToSalesTrailing12Months",
    "price_to_book": "priceToBook",
    "ev_to_ebitda": "enterpriseToEbitda",
    "profit_margin": "profitMargins",
    "operating_margin": "operatingMargins",
    "return_on_equity": "returnOnEquity",
    "debt_to_equity": "debtToEquity",
    "current_ratio": "currentRatio",
    "earnings_growth": "earningsGrowth",
    "revenue_growth": "revenueGrowth",
    "short_percent_of_float": "shortPercentOfFloat",
    "short_ratio": "shortRatio",
}

# Which raw fields feed each composite percentile, and how they rank. "invert" means a LOWER
# raw value should rank HIGHER (cheaper / less levered / less shorted = better). A field listed
# here that is missing for a ticker simply sits out of that composite's average (per spec — a
# composite is the mean of the present sub-percentiles, never defaulted). Negative valuation
# ratios are scrubbed to missing upstream in features.py (a negative P/E is not "cheap").
FUNDAMENTAL_PERCENTILE_GROUPS = {
    # value_percentile: cheaper -> higher. (forward_pe is fetched for context but, per spec's
    # Value definition, only these four ratios feed the composite.)
    "value_percentile": {
        "fields": ["trailing_pe", "price_to_sales", "ev_to_ebitda", "price_to_book"],
        "invert": True,
    },
    # quality_percentile: margins + ROE rank normally; debt_to_equity inverts. current_ratio is
    # deliberately excluded from the composite (fetched/stored as context only) — see spec note.
    "quality_percentile": {
        "fields": ["profit_margin", "operating_margin", "return_on_equity"],
        "invert_fields": ["debt_to_equity"],
        "invert": False,
    },
    # short_interest_percentile: less shorted -> higher. short_ratio is context only, not scored.
    "short_interest_percentile": {
        "fields": ["short_percent_of_float"],
        "invert": True,
    },
}

# Valuation ratios where a negative raw value means "no earnings / not meaningful", to be
# treated as missing rather than as a (misleadingly low = good) cheap reading. Scrubbed in
# features.compute_fundamental_features before any ranking happens.
NON_NEGATIVE_VALUATION_FIELDS = [
    "trailing_pe", "forward_pe", "price_to_sales", "price_to_book", "ev_to_ebitda",
]

# --- v0.3 sector-neutral ranking config -------------------------------------------------
# The `sector` column in watchlist.csv is mostly clean GICS but carries a few fragmented labels
# from the original hand-assigned rows. Normalize them to GICS before grouping so peers rank
# together (e.g. the 5 "Healthcare" names join the 54 "Health Care" peers). "Semiconductors" is
# deliberately kept as its own group (distinct valuation profile). Anything not in this map passes
# through unchanged. Applied by scoring/app via the `normalize_sector` helper.
SECTOR_NORMALIZE = {
    "Tech-Software": "Information Technology",
    "Healthcare": "Health Care",
    "Utilities-Power": "Utilities",
    "Industrials-Power": "Industrials",
}

# Rows carrying this (normalized) sector are benchmark ETFs — they have no meaningful fundamentals
# and are EXCLUDED from value/quality sector ranking entirely (value/quality components sit out).
# Matches the benchmark ETF set (set(watchlist.benchmark) | {"SPY"}); all 13 ETFs carry "Index".
ETF_SECTOR_LABEL = "Index"

# Which composite percentiles are computed WITHIN sector in v0.3. Short interest and every
# price/volume percentile stay cross-sectional. Empty set = v0.1/v0.2 all-cross-sectional behavior.
SECTOR_NEUTRAL_COMPOSITES = {"value_percentile", "quality_percentile"}

# v0.1 horizon weights — PRESERVED UNTOUCHED so the side-by-side performance report can
# annotate v0.1 component ICs against the weights they were actually scored under. Never used
# to score a v0.2 run; kept purely for honest historical comparison (CLAUDE.md #5).
SCORE_WEIGHTS_V01 = {
    "score_5d": {
        "trend_component": 0.10,
        "short_momentum_component": 0.25,
        "relative_strength_component_5d": 0.15,
        "volume_behavior_component": 0.20,
        "risk_component": 0.15,
        "setup_component": 0.15,
    },
    "score_20d": {
        "trend_component": 0.20,
        "momentum_component_20d": 0.20,
        "relative_strength_component_20d": 0.20,
        "volume_behavior_component": 0.10,
        "risk_component": 0.15,
        "setup_component": 0.10,
        "market_regime_component": 0.05,
    },
    "score_60d": {
        "trend_component": 0.25,
        "medium_momentum_component": 0.20,
        "relative_strength_component_60d": 0.25,
        "volume_behavior_component": 0.05,
        "risk_component": 0.15,
        "market_regime_component": 0.10,
    },
    "score_120d": {
        "trend_component": 0.30,
        "long_momentum_component": 0.25,
        "relative_strength_component_120d": 0.25,
        "risk_component": 0.10,
        "market_regime_component": 0.10,
    },
}

# v0.2 ACTIVE horizon weights — the principled reweight. Each weight is a STARTING PRIOR set
# from cross-regime durability + v0.1 IC evidence, NOT curve-fit to the 2024-26 backfill (the
# primary failure mode). The IC report measures whether they hold; adjust gently, never in one
# pass. value/quality/short_interest are the new orthogonal factors; on any ticker missing
# them (always, on backfill) those components SIT OUT and the remaining weights renormalize to
# 1 in scoring.compute_horizon_scores. Each map sums to 1.0 with all components present.
# (volume_behavior/setup were cut to ~0 by IC; they are simply omitted rather than listed at 0,
# so a missing price/volume component still correctly nulls the horizon — see scoring.py.)
SCORE_WEIGHTS = {
    # 5d kept deliberately though price/volume can't predict 5-day moves (IC ~0): it is the
    # explicit testbed for the future data layer. Dead short-horizon p/v stuff down-weighted;
    # value/quality/short added as the orthogonal signal that *might* carry where momentum can't.
    "score_5d": {
        "short_momentum_component": 0.15,        # was 0.25 — ~0 IC, starved of the right inputs
        "relative_strength_component_5d": 0.15,
        "trend_component": 0.15,
        "value_component": 0.15,                 # NEW orthogonal factor
        "quality_component": 0.15,               # NEW orthogonal factor
        "risk_component": 0.10,                  # reduced, not inverted (anti-overfit)
        "short_interest_component": 0.10,        # NEW orthogonal factor
        "volume_behavior_component": 0.05,       # was 0.20 — ~0 IC, arbitraged folklore
    },
    # 20d: cut volume/setup to zero per IC (~0); added value+quality as 30% combined orthogonal
    # signal; trend nudged up; market_regime kept minimal.
    "score_20d": {
        "trend_component": 0.18,
        "momentum_component_20d": 0.15,
        "relative_strength_component_20d": 0.15,
        "value_component": 0.15,                 # NEW
        "quality_component": 0.15,               # NEW
        "risk_component": 0.10,                  # reduced, not inverted
        "short_interest_component": 0.07,        # NEW
        "market_regime_component": 0.05,
        # volume_behavior 0.00 and setup 0.00 per IC — omitted (see header note).
    },
    # 60d: real separation begins here; trend nudged, value/quality fold in as durable
    # medium-horizon factors.
    "score_60d": {
        "trend_component": 0.20,
        "medium_momentum_component": 0.15,
        "relative_strength_component_60d": 0.18,
        "value_component": 0.17,                 # NEW
        "quality_component": 0.15,               # NEW
        "risk_component": 0.08,                  # reduced, not inverted
        "short_interest_component": 0.05,        # NEW
        "market_regime_component": 0.02,
    },
    # 120d: clearest edge; trend up to ~0.22 reflecting its 0.11 IC; value/quality as
    # long-horizon bedrock.
    "score_120d": {
        "trend_component": 0.22,
        "long_momentum_component": 0.15,
        "relative_strength_component_120d": 0.18,
        "value_component": 0.15,                 # NEW
        "quality_component": 0.15,               # NEW
        "risk_component": 0.08,                  # reduced, not inverted
        "short_interest_component": 0.05,        # NEW
        "market_regime_component": 0.02,
    },
}

# Per-model-version weight map, so the side-by-side report annotates each version's component
# ICs against the weights it was actually scored under (v0.1 rows -> v0.1 weights).
SCORE_WEIGHTS_BY_VERSION = {
    "v0.1_price_volume_only": SCORE_WEIGHTS_V01,
    "v0.2_fundamentals_added": SCORE_WEIGHTS,
    # v0.3 reuses v0.2's weights verbatim — it changes how value/quality RANKS are computed
    # (within-sector), not what they're worth. One change at a time keeps the IC comparison clean.
    "v0.3_sector_neutral": SCORE_WEIGHTS,
    # v0.4 reuses v0.3's weights VERBATIM. The single variable that changes is where fundamentals come
    # from: yfinance's current-only snapshot -> EDGAR filings gated on filed_date <= D. Same weights,
    # same sector-neutral ranking, same everything else, so a v0.3-vs-v0.4 IC comparison isolates the
    # source change. Changing weights here too would confound the one thing this version tests.
    "v0.4_edgar_pit_fundamentals": SCORE_WEIGHTS,
    # v0.5 reuses v0.4's weights VERBATIM - only the universe changes. One variable at a time.
    "v0.5_expanded_universe": SCORE_WEIGHTS,
    # v0.6 reuses v0.5's weights VERBATIM. The single variable that changes is that the LIVE path
    # now resolves fundamentals the same way the backfill always did. Changing a weight here would
    # confound the one thing this version exists to fix.
    "v0.6_live_pit_fundamentals": SCORE_WEIGHTS,
}

# The v0.4 model version string, referenced by the EDGAR backfill path. Kept as a constant so the
# backfill and the evaluation split can't drift on a typo.
EDGAR_MODEL_VERSION = "v0.4_edgar_pit_fundamentals"

# v0.5: the SAME pipeline as v0.4, run over a ~3x wider universe (S&P 500 + 400 + 600).
# Weights, sector-neutral ranking, and the EDGAR fundamentals source are all identical - the
# single variable that changes is WHICH NAMES are in the cross-section, so a v0.4-vs-v0.5
# comparison isolates the universe. Note the percentile denominators change with it (a value
# rank is now against ~1500 peers, not ~500), which is precisely why this needs its own version
# rather than overwriting v0.4.
EXPANDED_MODEL_VERSION = "v0.5_expanded_universe"

# v0.6 — THE LIVE ROW AND THE BACKFILLED ROW ARE NOW THE SAME MODEL.
#
# Up to v0.5 they were not, and one `model_version` string covered both. Measured 2026-09-16 on the
# v0.5 rows, by direct query:
#
#                             live (27,396 rows)          backfilled (777,738 rows)
#   fundamentals_pit          0 on every row              1 on every row
#   fundamentals source       yfinance CURRENT snapshot   EDGAR, gated filed_date <= D
#   short_interest_component  present on 26,744           NULL on all 777,738
#   earnings penalty          applied to 289 rows         applied to 0
#
# So every historical number this project has produced — the decile spread, the backtest, the daily
# log's "same model" caption — described a model that was NOT the one running nightly, and the only
# genuinely out-of-sample rows (the live ones) were scored by a model that had never been validated.
# The three differences all have the same root cause (the live path fetched its own fundamentals
# instead of resolving them), so they are fixed together as ONE variable: live-vs-backfill
# equivalence. They are NOT three separate changes.
#
# What v0.6 changes:
#   1. live + recovered rows resolve fundamentals via edgar.get_fundamentals_as_of(as_of=run_date),
#      which is what the backfill has always done -> fundamentals_pit=1 on EVERY v0.6 row;
#   2. short_interest_component therefore has no source and sits out everywhere, exactly as it does
#      on backfilled rows. It is NOT removed from SCORE_WEIGHTS: sitting out renormalizes the
#      surviving weights, which is numerically identical to deleting it, and leaving it in place
#      means a real FINRA short-interest history (free, bi-monthly, backfillable) can be switched
#      on later without another weight change;
#   3. the live-only earnings penalty is disabled — see LIVE_EARNINGS_PENALTY_VERSIONS.
#
# What v0.6 does NOT change: weights, sector-neutral ranking, the universe, any component formula.
LIVE_PIT_MODEL_VERSION = "v0.6_live_pit_fundamentals"

# Versions whose LIVE path applied the near-earnings penalty. The backfill NEVER applies it (a
# historical earnings date is not reconstructable), so on every version listed here a live row near
# earnings was scored on a different formula than its backfilled counterpart — 289 rows under v0.5.
# v0.6 is deliberately absent: the penalty is a plausible risk control that has never been validated
# against anything, and equivalence with the backtested model is worth more than an unmeasured
# adjustment. `days_until_earnings` and `earnings_risk_unknown` are still COLLECTED and stored on
# every v0.6 row, so the penalty can be measured later and switched back on if it earns its place.
LIVE_EARNINGS_PENALTY_VERSIONS = {
    "v0.2_fundamentals_added",
    "v0.3_sector_neutral",
    "v0.5_expanded_universe",
}

# Versions whose snapshots are COMPLETE and immutable — no new rows will ever be written to them, so
# re-deriving their forward returns nightly can only ever reproduce the same numbers. They are skipped
# on the nightly evaluation path (their last computed report rows are carried forward, so the report
# still shows every version side by side) and recomputed only when explicitly requested.
# A version belongs here once its backfill is finished and the daily run has moved on to a successor.
FROZEN_MODEL_VERSIONS = {
    "v0.1_price_volume_only",
    "v0.2_fundamentals_added",
    # frozen 2026-08-21 when v0.5 was promoted: 34 live dates, preserved for comparison, never extended
    "v0.3_sector_neutral",
    "v0.4_edgar_pit_fundamentals",
}

# Components that may legitimately be absent for a ticker (sparse fundamentals/short interest)
# and "sit out" — their weight is dropped and the remaining weights renormalize to 1. Every
# OTHER (price/volume) component stays mandatory: if one is None the horizon is None, exactly
# as in v0.1 (preserves the v0.1 missing-input contract and its tests).
SITOUT_COMPONENTS = {"value_component", "quality_component", "short_interest_component"}

# Event-risk penalty applied only on live (non-backfilled) runs when
# 0 <= days_until_earnings <= 5. Skipped entirely if earnings_risk_unknown.
EARNINGS_PENALTIES = {"5d": 20, "20d": 12, "60d": 5, "120d": 0}

# The same map zeroed, for a version that does not apply the penalty (see
# LIVE_EARNINGS_PENALTY_VERSIONS). Passed explicitly rather than branching around the penalty so
# both paths run identical code and only the numbers differ.
NO_EARNINGS_PENALTIES = {k: 0 for k in EARNINGS_PENALTIES}

# Score -> label bands. 80-100 strong / 65-79 decent / 50-64 watchlist / <50 weak.
SCORE_LABEL_BANDS = {
    "strong": (80, 100),
    "decent": (65, 79),
    "watchlist": (50, 64),
    "weak": (0, 49),
}

# Every weight/penalty/threshold used inside an individual component formula. Keyed by
# component name; scoring.py reads from here instead of hardcoding spec constants.
COMPONENT_PARAMS = {
    "trend_component": {
        "points_per_condition": 20,  # 5 conditions: close>SMA20/50/200, SMA20>SMA50, SMA50>SMA200
    },
    "short_momentum_component": {
        "w_return_5d_pct": 0.40, "w_return_10d_pct": 0.35, "w_return_20d_pct": 0.25,
        "penalty_return_5d_negative": 15, "penalty_return_10d_negative": 10,
    },
    "momentum_component_20d": {
        "w_return_20d_pct": 0.50, "w_return_60d_pct": 0.30, "w_return_10d_pct": 0.20,
        "penalty_return_20d_negative": 20,
    },
    "medium_momentum_component": {
        "w_return_60d_pct": 0.45, "w_return_120d_pct": 0.35, "w_return_20d_pct": 0.20,
        "penalty_return_60d_negative": 20,
    },
    "long_momentum_component": {
        "w_return_120d_pct": 0.45, "w_return_252d_pct": 0.35, "w_return_60d_pct": 0.20,
        "penalty_return_120d_negative": 20,
        # fallback when return_252d_pct is missing: use return_120d_pct in its place
        "return_252d_fallback_field": "return_120d_pct",
    },
    "relative_strength_component_5d": {
        "w_rs_5d_pct": 0.60, "w_rs_20d_pct": 0.40, "penalty_rs_5d_negative": 10,
    },
    "relative_strength_component_20d": {
        "w_rs_20d_pct": 0.50, "w_rs_60d_pct": 0.50,
        "penalty_rs_20d_negative": 10, "penalty_rs_60d_negative": 10,
    },
    "relative_strength_component_60d": {
        "w_rs_60d_pct": 0.60, "w_rs_120d_pct": 0.40, "penalty_rs_60d_negative": 10,
    },
    "relative_strength_component_120d": {
        "w_rs_120d_pct": 0.70, "w_rs_60d_pct": 0.30, "penalty_rs_120d_negative": 10,
    },
    "volume_behavior_component": {
        "base": 50,
        "ratio_threshold_1": 1.2, "ratio_threshold_2": 1.5, "ratio_threshold_3": 2.0,
        "up_day_bonus_at_threshold_1": 10,   # vol_ratio_20d > 1.2 & return_1d > 0
        "up_day_bonus_at_threshold_2": 15,   # additionally > 1.5
        "up_day_bonus_at_threshold_3": 10,   # additionally > 2.0
        "down_day_penalty_at_threshold_2": -25,  # vol_ratio_20d > 1.5 & return_1d < 0
        "down_day_penalty_at_threshold_3": -15,  # additionally > 2.0
        "high_vol_day_diff_multiplier": 5,   # 5 * (high_vol_up_days - high_vol_down_days)
        "weak_close_penalty": -10,           # weak_close_flag & vol_ratio_20d > 1.2
        "strong_close_bonus": 10,            # strong_close_flag & vol_ratio_20d > 1.2
        "close_flag_ratio_threshold": 1.2,
    },
    "risk_component": {
        "w_atr_pct_percentile": 0.35,
        "w_volatility_60d_percentile": 0.25,
        "w_max_drawdown_60d_percentile": 0.25,
        "w_distance_from_52w_high_adjusted_percentile": 0.15,
        "penalty_extended": 20,
        "penalty_below_sma50": 15,
    },
    "setup_component": {
        "points_close_above_sma20": 20,
        "points_close_above_sma50": 20,
        "points_not_extended": 20,
        "points_near_20d_high": 15,
        "points_near_60d_high": 15,
        "points_pullback_above_sma50": 10,
        "penalty_failed_breakout": -30,
    },
    "market_regime_component": {
        "points_benchmark_above_sma20": 25,
        "points_benchmark_above_sma50": 25,
        "points_benchmark_above_sma200": 20,
        "points_benchmark_return_20d_positive": 15,
        "points_benchmark_return_60d_positive": 15,
        "penalty_benchmark_vol_high": -10,
    },
    # v0.2 — each is simply the (already 0-100) composite percentile passed through and clamped.
    # No internal sub-weights live here: the value/quality blend is the mean of present
    # sub-percentiles, defined in FUNDAMENTAL_PERCENTILE_GROUPS, not a tunable here.
    "value_component": {"percentile_field": "value_percentile"},
    "quality_component": {"percentile_field": "quality_percentile"},
    "short_interest_component": {"percentile_field": "short_interest_percentile"},
}

# --- v0.4 EDGAR point-in-time fundamentals ----------------------------------------------------
# SEC EDGAR gives every XBRL fact stamped with its FILED date, enabling legitimate point-in-time
# reconstruction (a fact is usable as-of D iff filed_date <= D). This replaces yfinance's current-only
# fundamentals so value/quality can be backfilled + validated on history instead of only live.
EDGAR = {
    # SEC REQUIRES a descriptive User-Agent with a real contact on every request (they will block a
    # generic/absent one). This is a config value — change the contact to your own.
    "user_agent": SEC_USER_AGENT,
    "company_tickers_url": "https://www.sec.gov/files/company_tickers.json",
    # {cik10} = 10-digit zero-padded CIK.
    "companyfacts_url": "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json",
    # Optional full-refresh archive (several GB) — NOT the default path; per-CIK is primary for our
    # fixed universe. Kept here so a bulk refresh is a config-known URL, not a magic string.
    "companyfacts_bulk_url": "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip",
    "max_requests_per_sec": 8,        # SEC hard limit is 10/s; stay comfortably under
    "request_timeout_sec": 30,
    "max_retries": 3,
    "backoff_base_sec": 2.0,
    # A company's facts are refetched at most this often (facts change only when a new filing lands).
    "refresh_days": 7,
}

# --- Filing TEXT + LLM factual extraction (research only, UNPROVEN) ---------------------------
#
# The 8-K study tested ITEM CODES and found nothing. Item 8.01 is literally "Other Events" and
# covers a buyback, a plant fire and a lawsuit settlement alike, so that null says little about
# whether the filings' TEXT carries signal. Reading them is a different experiment.
#
# THE TRAP: an LLM's training data includes what happened AFTER these filings. Asking "is this
# bullish?" invites it to answer from memory of the stock's subsequent move - a lookahead leak that
# lives in the model's weights, where no filed_date gating can reach it. Two structural defences:
# the prompt extracts FACTS only (no sentiment field exists in the schema), and every result is
# split at the knowledge cutoff so contamination is MEASURED rather than assumed.
#
# COST: billed separately from any Claude subscription. ~2.5k input tokens per filing.
FILING_TEXT = {
    "model": "claude-haiku-4-5-20251001",   # extraction is reading comprehension; cheap is correct
    "max_chars": 10000,                     # an 8-K states its substance in the first page or two
    "max_output_tokens": 500,               # the schema is a dozen booleans
    # Conservative. Set EARLIER than the true cutoff rather than later: an over-generous value would
    # put memorisable filings in the "clean" half and hide the very leak the split exists to find.
    "model_knowledge_cutoff": "2025-01-31",
    "min_post_cutoff_filings": 500,         # below this the contamination test cannot conclude
    "pilot_sample_size": 2000,              # prove the method before spending on all 65k
}

# --- SEC filing index: 8-K material events, 10-K/10-Q dates -----------------------------------
#
# SOURCE: the per-company submissions API, which carries the 8-K ITEM CODES. The quarterly bulk
# index lists filings but not items, and the item code is where the whole signal lives - a 5.07
# (annual-meeting vote) and a 4.02 (previously issued financials can no longer be relied upon) are
# both "an 8-K", and only one of them matters.
#
# Unlike the Form 3/4/5 bulk datasets, this source is CURRENT (returns filings through today), so a
# feature built on it could serve a nightly run without a second pipeline.
SEC_SUBMISSIONS = {
    "submissions_url": "https://data.sec.gov/submissions/CIK{cik10}.json",
    "archive_url": "https://data.sec.gov/submissions/{name}",
    "since_date": "2023-12-01",     # ~6 months before price history starts, so 90d lookbacks are full
    # Regular-session close in EXCHANGE time. SEC stamps acceptanceDateTime in Eastern with an
    # explicit offset, so the clock time in the string is already the exchange's own clock. A filing
    # accepted at or after this hour could not be traded until the next session.
    "market_close_hour_et": 16,
}

# Forms stored. Deliberately NARROW, unlike `edgar_facts`: a full re-ingest here is ~3 minutes at
# 8 req/s, so widening this later is cheap and disk is the scarcer resource (the DB is already
# 14.1 GB). Form 4 is excluded because `insider_transactions` already holds it with full detail.
FILING_FORMS = {"8-K", "8-K/A", "10-K", "10-K/A", "10-Q", "10-Q/A"}

# 8-K item codes that are PURE PAPERWORK. 9.01 is "financial statements and exhibits" - an
# attachment notice bolted onto most other items; 5.07 is the annual shareholder vote. An 8-K
# carrying ONLY these is administrative. Counting it as a material event is the same mistake as
# counting an option grant as insider buying: it buries the signal under paperwork.
ROUTINE_8K_ITEMS = {"9.01", "5.07"}

# The item codes with documented price reactions, kept here so the mapping is auditable in one
# place rather than inferred from a feature name.
MATERIAL_8K_ITEMS = {
    "1.01": "material_definitive_agreement",
    "1.03": "bankruptcy_or_receivership",
    "2.01": "completion_of_acquisition",
    "2.02": "results_of_operations",           # the earnings release itself
    "2.05": "exit_or_disposal_costs",
    "2.06": "material_impairment",
    "3.01": "delisting_or_listing_deficiency",
    "4.01": "change_in_accountant",
    "4.02": "non_reliance_on_prior_financials",  # the sharpest red flag on the list
    "5.02": "officer_or_director_change",
    "7.01": "reg_fd_disclosure",
    "8.01": "other_events",
}

# 8-K item GROUPS the features count separately. Split rather than pooled because these events are
# not the same kind of news: an earnings release (2.02) is scheduled and widely anticipated, a
# non-reliance notice (4.02) is a rare shock, and a Reg FD disclosure (7.01) is usually nothing.
# Pooling them into "an 8-K happened" averages a shock with a formality and measures neither.
# `None` means "anything that is not pure paperwork" (see ROUTINE_8K_ITEMS).
EVENT_8K_GROUPS = {
    "material": None,
    "earnings": {"2.02"},
    "officer_change": {"5.02"},
    "agreement": {"1.01", "2.01"},
    "redflag": {"4.02", "2.06", "1.03", "3.01"},
    "disclosure": {"7.01", "8.01"},
}

# Trailing windows, in CALENDAR days, over which each group is counted.
EVENT_8K_WINDOWS = [5, 30, 90]

# --- SEC Form 3/4/5 insider transactions -----------------------------------------------------
#
# SOURCE CHOICE, and it is the whole reason this is affordable: SEC publishes QUARTERLY structured
# datasets containing every ownership filing already parsed into TSVs. Nine downloads (~94 MB) cover
# the entire price history. Enumerating the same filings one at a time through the submissions API
# would be roughly 200,000 HTTP requests — days of wall clock against an 8/s throttle, for identical
# data.
#
# THE POINT-IN-TIME GATE IS `FILING_DATE`, NEVER `TRANS_DATE`. An insider has two business days to
# report, so the market cannot know about a purchase on the day it happened. Gating on the
# transaction date would hand the model several days of foresight per filing and produce exactly the
# kind of beautiful, false backtest CLAUDE.md invariant #1 exists to prevent.
INSIDER = {
    "dataset_url": ("https://www.sec.gov/files/structureddata/data/"
                    "insider-transactions-data-sets/{year}q{quarter}_form345.zip"),
    "cache_dir": "data/insider_datasets",   # zips are cached; a re-run re-parses, never re-downloads
    # Coverage. SEC publishes these on a lag — verified 2026-09-10: 2024Q1 through 2026Q1 exist,
    # 2026Q2 and 2026Q3 return 404. So the store ENDS at 2026-03-31 while price history runs to
    # 2026-09-08. That gap is recorded in `meta` and enforced by `coverage_end`: a date past the end
    # of coverage must return "unknown", never "no insider activity". Absence of data is not a zero.
    "first_quarter": (2024, 1),
    "last_quarter": (2026, 1),
    "request_timeout_sec": 180,             # these are 8-14 MB files, not JSON blobs
    "max_retries": 3,
    "backoff_base_sec": 2.0,
}

# Form 4 transaction codes, and which of them carry INFORMATION rather than compensation mechanics.
#
# This split is the entire signal. An insider "acquiring" shares is usually just being paid: code A
# is a grant, M is an option exercise, F is shares withheld to cover the tax on a grant. None of
# those reflect an opinion about the price. Code P — an open-market purchase with the insider's own
# money — is the one with a documented anomaly behind it. Treating all acquisitions alike would bury
# that signal under an order of magnitude more compensation noise.
INSIDER_TRANS_CODES = {
    "P": "open_market_purchase",   # the informative one
    "S": "open_market_sale",       # informative but noisy: diversification, tax, scheduled plans
    "A": "grant_award",            # compensation
    "M": "option_exercise",        # compensation
    "F": "tax_withholding",        # compensation
    "G": "gift",
    "C": "conversion",
    "D": "disposition_to_issuer",
    "X": "option_exercise_in_money",
    "J": "other",
}
INSIDER_INFORMATIVE_CODES = {"P", "S"}
INSIDER_PURCHASE_CODES = {"P"}

# Reporting-owner relationships, collapsed. The raw field is a free-ish text list ("Director",
# "Officer", "TenPercentOwner", or several joined), so it is normalized once on ingest.
INSIDER_RELATIONSHIPS = ["Director", "Officer", "TenPercentOwner", "Other"]

# Ordered XBRL tag fallback chains per CONCEPT (us-gaap taxonomy unless a "dei:" prefix says otherwise).
# XBRL tagging varies by filer, so each concept tries tags in order; the FIRST present in a filing wins,
# and the resolver logs which one resolved (a concept resolving via a late fallback for many names is a
# signal the mapping needs work). WIDEN THIS — and add new concepts — as future factors arrive; the raw
# edgar_facts store already holds every tag, so a new factor is a config change, not a re-ingest.
EDGAR_CONCEPT_TAGS = {
    # `Revenues` FIRST: it is the us-gaap TOTAL. RevenueFromContractWithCustomer... covers only ASC-606
    # contract revenue, which for a lease-heavy filer (REITs) is a small slice of the top line — leases
    # are not contracts with customers. Preferring the contract tag understated AVB's revenue so badly
    # its profit margin read 160x. For ordinary filers the two are equal, so this order is strictly safer.
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "equity": ["StockholdersEquity",
               "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "shares": ["CommonStockSharesOutstanding", "dei:EntityCommonStockSharesOutstanding",
               "WeightedAverageNumberOfDilutedSharesOutstanding"],
    "assets": ["Assets"],
    "liabilities": ["Liabilities"],
    # Interest-bearing DEBT is not total liabilities (which includes payables, deferred revenue,
    # pension...). It is also not a single tag: it is the SUM of a long-term leg and a current leg,
    # each with its own fallback chain. yfinance's debtToEquity uses this same interest-bearing
    # notion, expressed as a PERCENT — see EDGAR_DEBT_LEGS below for how the two are combined.
    "debt_long_term": ["LongTermDebtNoncurrent", "LongTermDebt",
                       "LongTermDebtAndCapitalLeaseObligations"],
    "debt_current": ["LongTermDebtCurrent", "DebtCurrent", "ShortTermBorrowings"],
    # LEASE OBLIGATIONS. Since ASC 842 both finance and operating leases sit on the balance
    # sheet, and yfinance's totalDebt includes them. Omitting them understated debt_to_equity by
    # a systematic ~6-9%, worsening as companies got smaller (small caps lease proportionally
    # more of what they use). Adding them moved the median disagreement from 8.2/9.1/10.5% to
    # 3.9/2.8/2.1% across large/mid/small and removed the one-directional bias entirely.
    # Noncurrent + current are SUMMED; the combined tag is the fallback when the split is absent.
    "debt_finance_lease_noncurrent": ["FinanceLeaseLiabilityNoncurrent"],
    "debt_finance_lease_current": ["FinanceLeaseLiabilityCurrent"],
    "debt_finance_lease_total": ["FinanceLeaseLiability"],
    "debt_operating_lease_noncurrent": ["OperatingLeaseLiabilityNoncurrent"],
    "debt_operating_lease_current": ["OperatingLeaseLiabilityCurrent"],
    "debt_operating_lease_total": ["OperatingLeaseLiability"],
    "current_assets": ["AssetsCurrent"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "cogs": ["CostOfGoodsAndServicesSold", "CostOfRevenue"],
    "operating_income": ["OperatingIncomeLoss"],
    "cash_flow_ops": ["NetCashProvidedByUsedInOperatingActivities"],
}

# Total interest-bearing debt = long-term leg + current leg. The long-term leg is REQUIRED (it is the
# dominant one and is present for 423/507 filers); the current leg is added when present. A missing
# current leg is NOT treated as zero — absence of a tag is not evidence of no short-term debt — so the
# result is flagged `debt_partial` in provenance rather than silently understated (invariant #2).
EDGAR_DEBT_LEGS = {"required": "debt_long_term", "optional": "debt_current"}

# Lease legs added on top of interest-bearing debt. Each entry is (split_parts, combined_fallback):
# sum the noncurrent+current parts when present, else take the single combined tag.
EDGAR_LEASE_LEGS = [
    (("debt_finance_lease_noncurrent", "debt_finance_lease_current"), "debt_finance_lease_total"),
    (("debt_operating_lease_noncurrent", "debt_operating_lease_current"), "debt_operating_lease_total"),
]

# A long-term debt tag that ALREADY bundles capital/finance leases. If debt resolves through this
# tag, the finance-lease leg must not be added again or the obligation is counted twice.
EDGAR_DEBT_TAGS_INCLUDING_LEASES = {"LongTermDebtAndCapitalLeaseObligations"}

# yfinance reports debtToEquity as a PERCENT (e.g. 70.3, not 0.703). v0.4 must match that convention
# exactly so v0.3 (yfinance-sourced) and v0.4 (EDGAR-sourced) snapshots stay directly comparable.
EDGAR_DEBT_TO_EQUITY_SCALE = 100.0

# Fields the EDGAR resolver deliberately WITHHOLDS, even though it can compute them. A field lands here
# when the Phase-3 validation gate could not confirm it reproduces reality — the pipe is capable, the
# number is unverified, so it sits out and the existing renormalization redistributes its weight.
#
# operating_margin (excluded 2026-08): EDGAR runs a systematic ~9% BELOW yfinance for 75% of names
# (Spearman 0.860, median diff 14.2% — all three gate criteria failed). The gap survived every fix
# including period alignment, so it is not a mapping bug. Working hypothesis: Yahoo publishes a
# NORMALIZED operating income (excluding one-time charges) while us-gaap OperatingIncomeLoss is
# as-reported — consistent with yfinance showing NEGATIVE margins for PANW and COO, both profitable
# but both heavy on stock comp and acquisition amortization, exactly where the two definitions split.
# Plausible, but unverified against a third source, so it does not enter a score. See ROADMAP.
EDGAR_EXCLUDED_FIELDS = {"operating_margin"}

# Fields the EDGAR resolver STRUCTURALLY cannot supply — each already documented at its definition in
# edgar.py or in EDGAR_EXCLUDED_FIELDS above. Verified against the stored data on 2026-09-16: these are
# NULL on 100% of all 1,055,667 EDGAR-sourced rows across v0.4 and v0.5, i.e. they have never once
# resolved, which is the designed behaviour and not a fault.
#
# The live-run sparse-fundamentals warning skips them. Before v0.6 the live path fetched fundamentals
# from yfinance, where a field missing for 100% of the universe genuinely meant a broken data source
# and deserved a loud warning. From v0.6 the live path IS the EDGAR path, so those same seven fields
# would print seven "check the data source" warnings every single night, forever, about a state nobody
# can fix — and a warning that always fires is a warning that stops being read, which is how the next
# REAL source failure gets missed.
#
# Two consequences worth stating plainly, because the composites are documented in terms of fields that
# never arrive: value_percentile is the mean of THREE ratios (trailing_pe, price_to_sales,
# price_to_book), not the four listed in FUNDAMENTAL_PERCENTILE_GROUPS; and quality_percentile is
# profit_margin + return_on_equity + inverted debt_to_equity, with operating_margin never contributing.
EDGAR_UNAVAILABLE_FIELDS = {
    "forward_pe",                              # an estimate; never appears in a filing
    "ev_to_ebitda",                            # not implemented — needs debt/cash/EBITDA tags
    "operating_margin",                        # withheld by the gate; see EDGAR_EXCLUDED_FIELDS
    "earnings_growth", "revenue_growth",       # YoY derivations, a future factor
    "short_percent_of_float", "short_ratio",   # short interest is FINRA, not SEC filings
}

# GICS sectors whose filers (banks/insurers/REITs) don't report comparable COGS/margins — those concepts
# sit out (missing, never faked) for a ticker flagged with this profile. v0.3 sector-neutral ranking
# already compares them only to their own peers, limiting the damage.
EDGAR_FINANCIAL_SECTORS = {"Financials", "Real Estate"}
