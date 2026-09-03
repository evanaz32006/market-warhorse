# market-warhorse — Daily Log

_Machine-appended after every run. Regenerated from the `journal` table; do not edit by hand. Newest entry first._

---

## 2026-09-02 — v0.5_expanded_universe (live)

_Run: scored 1522 tickers in 2397.1s · fetch fresh=1522 / cached=5 / failed=1 (CWEN-A)_
_Warnings: 1 ticker(s) failed price fetch; 6 ticker(s) skipped (stale / no data)_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | CF | Materials | 82.0 | strong | 62d |
| 2 | HCI | Financials | 81.4 | strong | 63d |
| 3 | ESNT | Financials | 79.9 | decent | 64d |
| 4 | MRP | Real Estate | 79.8 | decent | 69d |
| 5 | HRMY | Health Care | 79.8 | decent | 61d |
| 6 | MPC | Energy | 79.4 | decent | 61d |
| 7 | REGN | Health Care | 79.4 | decent | 55d |
| 8 | RNR | Financials | 79.3 | decent | 61d |
| 9 | PSX | Energy | 78.9 | decent | 56d |
| 10 | PR | Energy | 78.8 | decent | 62d |

**vs prev live run (2026-09-01):** entered [ESNT, REGN] · exited [AMGN, VRTX]
**Movers:** ↑ DELL +27.4, BF-B +25.7, EEFT +20.1, SIRI +20.0, RDDT +19.6  ↓ APH -29.8, PANW -16.4, WLY -15.4, QLYS -14.6, FTNT -13.9

### 2. Predictions that came due today

**Live predictions** (v0.5_expanded_universe)

- **2026-08-26 · v0.5_expanded_universe → 5d** (n=1515): Strong n/a (n=0) vs Weak 47.1% (n=805)

**Simulated — same model, backfilled over history**

- **2026-03-12 · v0.5_expanded_universe → 120d** (n=515): Strong n/a (n=3) vs Weak 46.3% (n=268)
- **2026-08-05 · v0.5_expanded_universe → 20d** (n=1511): Strong n/a (n=15) vs Weak 44.5% (n=582)
- **2026-06-08 · v0.5_expanded_universe → 60d** (n=515): Strong n/a (n=4) vs Weak 56.5% (n=262)

_Simulated cohorts are this exact model scored point-in-time on an earlier date, so they show how it is performing in the CURRENT market regime rather than waiting for a live track record to accrue. They are reconstructions: no slippage, no missed fills, and the universe is as constituted today._

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | n/a (n=12) | 47.2% (n=3218) | 48.6% (n=2211) | 49.8% (n=239781) |
| 20d | n/a (n=0) | n/a (n=0) | 47.9% (n=5981) | 47.9% (n=218213) |
| 60d | n/a (n=0) | n/a (n=0) | 48.8% (n=6965) | 44.7% (n=190051) |
| 120d | n/a (n=0) | n/a (n=0) | 49.7% (n=6925) | 40.4% (n=143715) |

_Backfill baseline: v0.5_expanded_universe (541 sessions, 2024-06-24 → 2026-08-19)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 10 live trading day(s) since 2026-08-20. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: 5d +0.111 (n=6027)
  - quality_component: 5d -0.012 (n=6023)
  - short_interest_component: 5d +0.028 (n=5980)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.012 (n=757742), 20d +0.022 (n=736906), 60d +0.040 (n=677998), 120d +0.062 (n=589544)
  - quality_component: 5d -0.008 (n=763125), 20d -0.018 (n=742143), 60d -0.033 (n=682653), 120d -0.044 (n=593355)
  - short_interest_component: 5d +0.028 (n=5980)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (13 component-horizon(s) in range)

---

## 2026-09-01 — v0.5_expanded_universe (live)

_Run: scored 1522 tickers in 1959.9s · fetch fresh=1522 / cached=5 / failed=1 (CWEN-A)_
_Warnings: 1 ticker(s) failed price fetch; 6 ticker(s) skipped (stale / no data)_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | HCI | Financials | 81.7 | strong | 64d |
| 2 | RNR | Financials | 80.2 | strong | 62d |
| 3 | CF | Materials | 80.1 | strong | 63d |
| 4 | MRP | Real Estate | 79.9 | decent | 70d |
| 5 | PR | Energy | 79.4 | decent | 63d |
| 6 | MPC | Energy | 78.6 | decent | 62d |
| 7 | HRMY | Health Care | 78.6 | decent | 62d |
| 8 | VRTX | Health Care | 78.5 | decent | 61d |
| 9 | PSX | Energy | 78.2 | decent | 57d |
| 10 | AMGN | Health Care | 78.0 | decent | 62d |

**vs prev live run (2026-08-31):** entered [CF] · exited [MATX]
**Movers:** ↑ MDT +17.4, ALHC +16.5, NHC +15.0, HUM +14.4, CI +13.9  ↓ WHR -22.8, RUSHA -21.9, OSK -20.7, NX -19.1, SABR -17.7

### 2. Predictions that came due today

**Live predictions** (v0.5_expanded_universe)

- **2026-08-25 · v0.5_expanded_universe → 5d** (n=1515): Strong n/a (n=3) vs Weak 48.6% (n=797)

**Simulated — same model, backfilled over history**

- **2026-03-11 · v0.5_expanded_universe → 120d** (n=515): Strong n/a (n=4) vs Weak 45.5% (n=255)
- **2026-08-04 · v0.5_expanded_universe → 20d** (n=1511): Strong n/a (n=15) vs Weak 45.6% (n=559)
- **2026-06-05 · v0.5_expanded_universe → 60d** (n=515): Strong n/a (n=4) vs Weak 58.8% (n=250)

_Simulated cohorts are this exact model scored point-in-time on an earlier date, so they show how it is performing in the CURRENT market regime rather than waiting for a live track record to accrue. They are reconstructions: no slippage, no missed fills, and the universe is as constituted today._

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | n/a (n=12) | 47.3% (n=2413) | 48.6% (n=2211) | 49.8% (n=239781) |
| 20d | n/a (n=0) | n/a (n=0) | 47.9% (n=5966) | 47.9% (n=217631) |
| 60d | n/a (n=0) | n/a (n=0) | 48.9% (n=6946) | 44.6% (n=189311) |
| 120d | n/a (n=0) | n/a (n=0) | 49.8% (n=6915) | 40.4% (n=142906) |

_Backfill baseline: v0.5_expanded_universe (541 sessions, 2024-06-24 → 2026-08-19)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 9 live trading day(s) since 2026-08-20. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: 5d +0.081 (n=4520)
  - quality_component: 5d -0.006 (n=4517)
  - short_interest_component: 5d +0.046 (n=4484)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.011 (n=756235), 20d +0.022 (n=735434), 60d +0.040 (n=676528), 120d +0.062 (n=588075)
  - quality_component: 5d -0.008 (n=761619), 20d -0.018 (n=740656), 60d -0.033 (n=681169), 120d -0.044 (n=591873)
  - short_interest_component: 5d +0.046 (n=4484)

**4b. Drift on established components** (recent-window IC vs full history)
  - **DRIFT** medium_momentum_component@5d: -0.001 → +0.055 (recent n=6063)
  - **DRIFT** relative_strength_component_120d@5d: -0.000 → +0.051 (recent n=6063)

---

## 2026-08-31 — v0.5_expanded_universe (live)

_Run: scored 1522 tickers in 2500.5s · fetch fresh=1522 / cached=5 / failed=1 (CWEN-A)_
_Warnings: 1 ticker(s) failed price fetch; 6 ticker(s) skipped (stale / no data)_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | HCI | Financials | 79.9 | decent | 66d |
| 2 | RNR | Financials | 79.1 | decent | 64d |
| 3 | MRP | Real Estate | 79.0 | decent | 72d |
| 4 | VRTX | Health Care | 78.6 | decent | 63d |
| 5 | MPC | Energy | 78.1 | decent | 64d |
| 6 | HRMY | Health Care | 78.0 | decent | 64d |
| 7 | PSX | Energy | 77.7 | decent | 59d |
| 8 | PR | Energy | 77.6 | decent | 65d |
| 9 | AMGN | Health Care | 77.6 | decent | 64d |
| 10 | MATX | Industrials | 77.6 | decent | 65d |

**vs prev live run (2026-08-28):** entered [AMGN, MPC, PR, PSX] · exited [BDX, ESNT, MTG, NEM]
**Movers:** ↑ FFIV +16.9, KRYS +15.6, KMI +15.2, AVT +14.8, JAZZ +13.3  ↓ AON -23.6, CLX -21.0, APLE -20.1, WSM -17.6, ACHC -17.5

### 2. Predictions that came due today

**Live predictions** (v0.5_expanded_universe)

_None matured today._

**Simulated — same model, backfilled over history**

- **2026-03-10 · v0.5_expanded_universe → 120d** (n=515): Strong n/a (n=6) vs Weak 46.9% (n=254)
- **2026-08-03 · v0.5_expanded_universe → 20d** (n=1511): Strong 50.0% (n=20) vs Weak 44.8% (n=614)
- **2026-06-04 · v0.5_expanded_universe → 60d** (n=515): Strong n/a (n=5) vs Weak 63.6% (n=264)

_Simulated cohorts are this exact model scored point-in-time on an earlier date, so they show how it is performing in the CURRENT market regime rather than waiting for a live track record to accrue. They are reconstructions: no slippage, no missed fills, and the universe is as constituted today._

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | n/a (n=9) | 46.7% (n=1616) | 48.6% (n=2211) | 49.8% (n=239781) |
| 20d | n/a (n=0) | n/a (n=0) | 47.8% (n=5951) | 47.9% (n=217072) |
| 60d | n/a (n=0) | n/a (n=0) | 48.9% (n=6926) | 44.6% (n=188594) |
| 120d | n/a (n=0) | n/a (n=0) | 49.8% (n=6903) | 40.3% (n=142128) |

_Backfill baseline: v0.5_expanded_universe (541 sessions, 2024-06-24 → 2026-08-19)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 8 live trading day(s) since 2026-08-20. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: 5d +0.057 (n=3013)
  - quality_component: 5d -0.003 (n=3011)
  - short_interest_component: 5d +0.031 (n=2989)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.011 (n=754728), 20d +0.022 (n=733963), 60d +0.040 (n=675058), 120d +0.062 (n=586606)
  - quality_component: 5d -0.008 (n=760113), 20d -0.018 (n=739170), 60d -0.033 (n=679685), 120d -0.043 (n=590391)
  - short_interest_component: 5d +0.031 (n=2989)

**4b. Drift on established components** (recent-window IC vs full history)
  - **DRIFT** trend_component@5d: -0.004 → +0.049 (recent n=4544)
  - **DRIFT** momentum_component_20d@5d: -0.004 → +0.047 (recent n=4552)
  - **DRIFT** medium_momentum_component@5d: -0.001 → +0.077 (recent n=4547)
  - **DRIFT** long_momentum_component@5d: -0.000 → +0.050 (recent n=4547)
  - **DRIFT** relative_strength_component_20d@5d: -0.002 → +0.050 (recent n=4552)
  - **DRIFT** relative_strength_component_60d@5d: -0.001 → +0.066 (recent n=4547)
  - **DRIFT** relative_strength_component_120d@5d: -0.000 → +0.076 (recent n=4547)
  - **DRIFT** setup_component@5d: -0.012 → +0.044 (recent n=4553)

---

## 2026-08-28 — v0.5_expanded_universe (live)

_Run: scored 1522 tickers in 1922.0s · fetch fresh=1522 / cached=5 / failed=1 (CWEN-A)_
_Warnings: 1 ticker(s) failed price fetch; 6 ticker(s) skipped (stale / no data)_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | MRP | Real Estate | 81.0 | strong | 73d |
| 2 | RNR | Financials | 79.6 | decent | 65d |
| 3 | ESNT | Financials | 79.2 | decent | 68d |
| 4 | MTG | Financials | 79.2 | decent | 59d |
| 5 | MATX | Industrials | 78.6 | decent | 66d |
| 6 | NEM | Materials | 78.4 | decent | 53d |
| 7 | HCI | Financials | 78.2 | decent | 67d |
| 8 | VRTX | Health Care | 78.1 | decent | 64d |
| 9 | BDX | Health Care | 77.7 | decent | 67d |
| 10 | HRMY | Health Care | 77.6 | decent | 65d |

**vs prev live run (2026-08-27):** entered [BDX, ESNT, RNR, VRTX] · exited [ADAM, AMGN, IOSP, JLL]
**Movers:** ↑ GAP +23.6, CHDN +22.9, GDDY +19.1, ADM +18.5, DLTR +18.5  ↓ PYPL -29.1, PCG -27.9, BDC -23.7, VTOL -22.6, FFIV -21.7

### 2. Predictions that came due today

**Live predictions** (v0.5_expanded_universe)

- **2026-08-21 · v0.5_expanded_universe → 5d** (n=1514): Strong n/a (n=3) vs Weak 49.4% (n=798)

**Simulated — same model, backfilled over history**

- **2026-03-09 · v0.5_expanded_universe → 120d** (n=515): Strong n/a (n=7) vs Weak 45.6% (n=248)
- **2026-07-31 · v0.5_expanded_universe → 20d** (n=517): Strong n/a (n=4) vs Weak 44.7% (n=246)
- **2026-06-03 · v0.5_expanded_universe → 60d** (n=515): Strong n/a (n=4) vs Weak 61.1% (n=270)

_Simulated cohorts are this exact model scored point-in-time on an earlier date, so they show how it is performing in the CURRENT market regime rather than waiting for a live track record to accrue. They are reconstructions: no slippage, no missed fills, and the universe is as constituted today._

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | n/a (n=9) | 46.7% (n=1616) | 48.6% (n=2211) | 49.8% (n=239781) |
| 20d | n/a (n=0) | n/a (n=0) | 47.8% (n=5931) | 47.9% (n=216458) |
| 60d | n/a (n=0) | n/a (n=0) | 48.9% (n=6908) | 44.5% (n=187866) |
| 120d | n/a (n=0) | n/a (n=0) | 49.8% (n=6889) | 40.3% (n=141381) |

_Backfill baseline: v0.5_expanded_universe (541 sessions, 2024-06-24 → 2026-08-19)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 7 live trading day(s) since 2026-08-20. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: 5d +0.057 (n=3013)
  - quality_component: 5d -0.003 (n=3011)
  - short_interest_component: 5d +0.031 (n=2989)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.011 (n=754728), 20d +0.022 (n=732493), 60d +0.040 (n=673588), 120d +0.062 (n=585137)
  - quality_component: 5d -0.008 (n=760113), 20d -0.018 (n=737685), 60d -0.034 (n=678201), 120d -0.043 (n=588909)
  - short_interest_component: 5d +0.031 (n=2989)

**4b. Drift on established components** (recent-window IC vs full history)
  - **DRIFT** trend_component@5d: -0.003 → +0.078 (recent n=3029)
  - **DRIFT** momentum_component_20d@5d: -0.004 → +0.071 (recent n=3034)
  - **DRIFT** medium_momentum_component@5d: -0.001 → +0.119 (recent n=3031)
  - **DRIFT** long_momentum_component@5d: -0.000 → +0.064 (recent n=3031)
  - **DRIFT** relative_strength_component_20d@5d: -0.002 → +0.087 (recent n=3034)
  - **DRIFT** relative_strength_component_60d@5d: -0.001 → +0.112 (recent n=3031)
  - **DRIFT** relative_strength_component_120d@5d: -0.000 → +0.103 (recent n=3031)
  - **DRIFT** setup_component@5d: -0.012 → +0.074 (recent n=3035)

---

## 2026-08-27 — v0.5_expanded_universe (live)

_Run: scored 1522 tickers in 2185.4s · fetch fresh=1523 / cached=4 / failed=1 (CWEN-A)_
_Warnings: 1 ticker(s) failed price fetch; 6 ticker(s) skipped (stale / no data)_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | MRP | Real Estate | 81.2 | strong | 76d |
| 2 | JLL | Real Estate | 80.7 | strong | 69d |
| 3 | ADAM | Real Estate | 80.0 | decent | 62d |
| 4 | MATX | Industrials | 79.6 | decent | 69d |
| 5 | MTG | Financials | 79.5 | decent | 62d |
| 6 | NEM | Materials | 79.3 | decent | 56d |
| 7 | HRMY | Health Care | 79.3 | decent | 68d |
| 8 | HCI | Financials | 79.2 | decent | 70d |
| 9 | IOSP | Materials | 78.1 | decent | 68d |
| 10 | AMGN | Health Care | 78.1 | decent | 68d |

**vs prev live run (2026-08-26):** entered [AMGN, HRMY, IOSP] · exited [ESNT, NMIH, REGN]
**Movers:** ↑ OKTA +42.8, SNPS +28.6, CRWD +27.1, NVDA +24.3, CRM +23.0  ↓ HQY -26.8, FMC -19.3, PBF -19.2, AEO -19.2, CHE -19.0

### 2. Predictions that came due today

**Live predictions** (v0.5_expanded_universe)

- **2026-08-20 · v0.5_expanded_universe → 5d** (n=1514): Strong n/a (n=6) vs Weak 44.1% (n=817)

**Simulated — same model, backfilled over history**

- **2026-03-06 · v0.5_expanded_universe → 120d** (n=515): Strong n/a (n=7) vs Weak 44.5% (n=245)
- **2026-07-30 · v0.5_expanded_universe → 20d** (n=517): Strong n/a (n=4) vs Weak 45.2% (n=230)
- **2026-06-02 · v0.5_expanded_universe → 60d** (n=515): Strong n/a (n=3) vs Weak 58.8% (n=274)

_Simulated cohorts are this exact model scored point-in-time on an earlier date, so they show how it is performing in the CURRENT market regime rather than waiting for a live track record to accrue. They are reconstructions: no slippage, no missed fills, and the universe is as constituted today._

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | n/a (n=6) | 44.1% (n=817) | 48.6% (n=2211) | 49.8% (n=239781) |
| 20d | n/a (n=0) | n/a (n=0) | 47.9% (n=5918) | 47.9% (n=215766) |
| 60d | n/a (n=0) | n/a (n=0) | 49.0% (n=6890) | 44.4% (n=187138) |
| 120d | n/a (n=0) | n/a (n=0) | 49.8% (n=6865) | 40.3% (n=140666) |

_Backfill baseline: v0.5_expanded_universe (541 sessions, 2024-06-24 → 2026-08-19)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 6 live trading day(s) since 2026-08-20. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: 5d +0.008 (n=1506)
  - quality_component: 5d -0.044 (n=1505)
  - short_interest_component: 5d +0.046 (n=1494)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.011 (n=753221), 20d +0.022 (n=731023), 60d +0.039 (n=672117), 120d +0.062 (n=583667)
  - quality_component: 5d -0.008 (n=758607), 20d -0.018 (n=736200), 60d -0.034 (n=676716), 120d -0.043 (n=587426)
  - short_interest_component: 5d +0.046 (n=1494)

**4b. Drift on established components** (recent-window IC vs full history)
  - **DRIFT** trend_component@5d: -0.004 → +0.075 (recent n=1514)
  - **DRIFT** momentum_component_20d@5d: -0.004 → +0.062 (recent n=1516)
  - **DRIFT** medium_momentum_component@5d: -0.001 → +0.129 (recent n=1515)
  - **DRIFT** long_momentum_component@5d: -0.000 → +0.137 (recent n=1515)
  - **DRIFT** relative_strength_component_20d@5d: -0.002 → +0.084 (recent n=1516)
  - **DRIFT** relative_strength_component_60d@5d: -0.001 → +0.134 (recent n=1515)
  - **DRIFT** relative_strength_component_120d@5d: -0.000 → +0.157 (recent n=1515)
  - **DRIFT** risk_component@5d: -0.019 → -0.077 (recent n=1516)

---

## 2026-08-26 — v0.5_expanded_universe (live)

_Run: scored 1523 tickers in 3370.1s · fetch fresh=1523 / cached=4 / failed=1 (CWEN-A)_
_Warnings: 1 ticker(s) failed price fetch; 5 ticker(s) skipped (stale / no data)_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | MRP | Real Estate | 82.3 | strong | — |
| 2 | JLL | Real Estate | 81.7 | strong | — |
| 3 | NMIH | Financials | 81.3 | strong | — |
| 4 | HCI | Financials | 80.2 | strong | 71d |
| 5 | MTG | Financials | 80.0 | strong | 63d |
| 6 | ESNT | Financials | 79.6 | decent | 72d |
| 7 | REGN | Health Care | 79.6 | decent | 63d |
| 8 | MATX | Industrials | 79.1 | decent | — |
| 9 | NEM | Materials | 79.0 | decent | 57d |
| 10 | ADAM | Real Estate | 78.9 | decent | 63d |

**vs prev live run (2026-08-25):** entered [NEM] · exited [PR]
**Movers:** ↑ SMTC +24.8, AEO +20.2, BG +19.3, FLR +19.0, SANM +18.0  ↓ VMRK -26.0, CHWY -18.9, CVCO -18.3, VNO -17.1, WGO -16.8

### 2. Predictions that came due today

**Live predictions** (v0.5_expanded_universe)

_None matured today._

**Simulated — same model, backfilled over history**

- **2026-03-05 · v0.5_expanded_universe → 120d** (n=515): Strong n/a (n=7) vs Weak 42.1% (n=240)
- **2026-07-29 · v0.5_expanded_universe → 20d** (n=517): Strong n/a (n=4) vs Weak 48.6% (n=218)
- **2026-08-19 · v0.5_expanded_universe → 5d** (n=1515): Strong n/a (n=4) vs Weak 46.7% (n=732)
- **2026-06-01 · v0.5_expanded_universe → 60d** (n=515): Strong n/a (n=5) vs Weak 57.4% (n=270)

_Simulated cohorts are this exact model scored point-in-time on an earlier date, so they show how it is performing in the CURRENT market regime rather than waiting for a live track record to accrue. They are reconstructions: no slippage, no missed fills, and the universe is as constituted today._

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | n/a (n=0) | n/a (n=0) | 48.6% (n=2211) | 49.8% (n=239781) |
| 20d | n/a (n=0) | n/a (n=0) | 47.9% (n=5909) | 47.9% (n=215093) |
| 60d | n/a (n=0) | n/a (n=0) | 49.0% (n=6873) | 44.4% (n=186425) |
| 120d | n/a (n=0) | n/a (n=0) | 49.9% (n=6836) | 40.2% (n=139965) |

_Backfill baseline: v0.5_expanded_universe (541 sessions, 2024-06-24 → 2026-08-19)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 5 live trading day(s) since 2026-08-20. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.011 (n=751715), 20d +0.022 (n=729554), 60d +0.039 (n=670647), 120d +0.062 (n=582198)
  - quality_component: 5d -0.008 (n=757102), 20d -0.018 (n=734716), 60d -0.034 (n=675232), 120d -0.043 (n=585944)
  - short_interest_component: no IC yet

**4b. Drift on established components** (recent-window IC vs full history)
  - too early — accruing (5/60 live days)

---

## 2026-08-25 — v0.5_expanded_universe (live)

_Run: scored 1523 tickers in 2867.8s · fetch fresh=1523 / cached=4 / failed=1 (CWEN-A)_
_Warnings: 1 ticker(s) failed price fetch; 5 ticker(s) skipped (stale / no data)_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | NMIH | Financials | 82.5 | strong | — |
| 2 | MRP | Real Estate | 81.6 | strong | — |
| 3 | JLL | Real Estate | 81.4 | strong | — |
| 4 | HCI | Financials | 79.7 | decent | 72d |
| 5 | REGN | Health Care | 79.6 | decent | 64d |
| 6 | ADAM | Real Estate | 79.5 | decent | 64d |
| 7 | MATX | Industrials | 79.4 | decent | — |
| 8 | MTG | Financials | 78.8 | decent | 64d |
| 9 | PR | Energy | 78.7 | decent | 71d |
| 10 | ESNT | Financials | 78.0 | decent | 73d |

**vs prev live run (2026-08-24):** entered [ESNT, HCI, MATX] · exited [SABR, TGT, THC]
**Movers:** ↑ LEU +17.3, VNO +17.1, SMH +16.3, UPS +15.9, AMD +15.7  ↓ KSS -25.9, DG -25.9, BBWI -20.7, BBY -19.2, KTB -18.2

### 2. Predictions that came due today

**Live predictions** (v0.5_expanded_universe)

_None matured today._

**Simulated — same model, backfilled over history**

- **2026-03-04 · v0.5_expanded_universe → 120d** (n=515): Strong n/a (n=9) vs Weak 46.8% (n=233)
- **2026-07-28 · v0.5_expanded_universe → 20d** (n=517): Strong n/a (n=4) vs Weak 45.6% (n=206)
- **2026-08-18 · v0.5_expanded_universe → 5d** (n=1515): Strong n/a (n=6) vs Weak 53.5% (n=778)
- **2026-05-29 · v0.5_expanded_universe → 60d** (n=515): Strong n/a (n=5) vs Weak 58.1% (n=253)

_Simulated cohorts are this exact model scored point-in-time on an earlier date, so they show how it is performing in the CURRENT market regime rather than waiting for a live track record to accrue. They are reconstructions: no slippage, no missed fills, and the universe is as constituted today._

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | n/a (n=0) | n/a (n=0) | 48.6% (n=2207) | 49.8% (n=239049) |
| 20d | n/a (n=0) | n/a (n=0) | 47.9% (n=5894) | 47.9% (n=214495) |
| 60d | n/a (n=0) | n/a (n=0) | 49.1% (n=6854) | 44.3% (n=185719) |
| 120d | n/a (n=0) | n/a (n=0) | 50.0% (n=6804) | 40.2% (n=139271) |

_Backfill baseline: v0.5_expanded_universe (541 sessions, 2024-06-24 → 2026-08-19)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 4 live trading day(s) since 2026-08-20. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.011 (n=750239), 20d +0.022 (n=728084), 60d +0.039 (n=669176), 120d +0.061 (n=580728)
  - quality_component: 5d -0.008 (n=755611), 20d -0.018 (n=733231), 60d -0.034 (n=673747), 120d -0.043 (n=584462)
  - short_interest_component: no IC yet

**4b. Drift on established components** (recent-window IC vs full history)
  - too early — accruing (4/60 live days)

---

## 2026-08-24 — v0.5_expanded_universe (recovered)

_Run: scored 1524 tickers in unknown time · fetch fresh=0 / cached=0 / failed=0_
_Fundamentals: recovered — fundamentals stamped 2026-08-25 (not point-in-time)_
_Warnings: recovered missed day; fundamentals as of 2026-08-25, excluded from factor IC_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | NMIH | Financials | 82.3 | strong | — |
| 2 | JLL | Real Estate | 81.1 | strong | — |
| 3 | ADAM | Real Estate | 80.9 | strong | — |
| 4 | MRP | Real Estate | 80.3 | strong | — |
| 5 | TGT | Consumer Staples | 79.4 | decent | — |
| 6 | THC | Health Care | 79.3 | decent | — |
| 7 | REGN | Health Care | 79.0 | decent | — |
| 8 | PR | Energy | 78.7 | decent | — |
| 9 | MTG | Financials | 78.6 | decent | — |
| 10 | SABR | Consumer Discretionary | 78.2 | decent | — |

**vs prev live run (2026-08-21):** entered [SABR] · exited [GEF]
**Movers:** ↑ KSS +26.4, GAP +21.1, ULTA +18.2, MZTI +17.9, BXP +17.4  ↓ BWA -22.6, IESC -19.9, VC -19.2, QQQ -17.5, SMP -16.8

### 2. Predictions that came due today

**Live predictions** (v0.5_expanded_universe)

_None matured today._

**Simulated — same model, backfilled over history**

- **2026-03-03 · v0.5_expanded_universe → 120d** (n=515): Strong n/a (n=8) vs Weak 45.8% (n=225)
- **2026-07-27 · v0.5_expanded_universe → 20d** (n=1512): Strong n/a (n=14) vs Weak 46.9% (n=620)
- **2026-08-17 · v0.5_expanded_universe → 5d** (n=1515): Strong n/a (n=4) vs Weak 64.1% (n=728)
- **2026-05-28 · v0.5_expanded_universe → 60d** (n=515): Strong n/a (n=6) vs Weak 60.4% (n=250)

_Simulated cohorts are this exact model scored point-in-time on an earlier date, so they show how it is performing in the CURRENT market regime rather than waiting for a live track record to accrue. They are reconstructions: no slippage, no missed fills, and the universe is as constituted today._

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | n/a (n=0) | n/a (n=0) | 48.5% (n=2201) | 49.8% (n=238271) |
| 20d | n/a (n=0) | n/a (n=0) | 47.9% (n=5890) | 47.9% (n=214289) |
| 60d | n/a (n=0) | n/a (n=0) | 49.1% (n=6849) | 44.3% (n=185466) |
| 120d | n/a (n=0) | n/a (n=0) | 50.1% (n=6795) | 40.2% (n=139038) |

_Backfill baseline: v0.5_expanded_universe (541 sessions, 2024-06-24 → 2026-08-19)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 4 live trading day(s) since 2026-08-20. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.011 (n=750239), 20d +0.022 (n=728084), 60d +0.039 (n=669176), 120d +0.061 (n=580728)
  - quality_component: 5d -0.008 (n=755611), 20d -0.018 (n=733231), 60d -0.034 (n=673747), 120d -0.043 (n=584462)
  - short_interest_component: no IC yet

**4b. Drift on established components** (recent-window IC vs full history)
  - too early — accruing (4/60 live days)

---

## 2026-08-21 — v0.5_expanded_universe (live)

_Run: regenerated from stored snapshots (original run metrics not recorded)._


### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | NMIH | Financials | 82.2 | strong | — |
| 2 | JLL | Real Estate | 82.1 | strong | — |
| 3 | ADAM | Real Estate | 81.4 | strong | 66d |
| 4 | THC | Health Care | 81.4 | strong | 65d |
| 5 | REGN | Health Care | 79.5 | decent | 66d |
| 6 | GEF | Materials | 79.2 | decent | 66d |
| 7 | TGT | Consumer Staples | 79.0 | decent | 87d |
| 8 | MRP | Real Estate | 78.9 | decent | — |
| 9 | MTG | Financials | 78.8 | decent | 66d |
| 10 | PR | Energy | 78.5 | decent | 73d |

**vs prev live run (2026-08-20):** entered [TGT] · exited [NLY]
**Movers:** ↑ BJ +37.2, BKE +24.6, HOOD +22.9, EZPW +22.4, IBKR +20.0  ↓ SFBS -30.3, THRM -17.2, SWX -16.0, OGS -15.9, SUPN -15.8

### 2. Predictions that came due today

**Live predictions** (v0.5_expanded_universe)

_None matured today._

**Simulated — same model, backfilled over history**

- **2026-03-02 · v0.5_expanded_universe → 120d** (n=904): Strong 33.3% (n=24) vs Weak 49.7% (n=394)
- **2026-07-24 · v0.5_expanded_universe → 20d** (n=1514): Strong n/a (n=15) vs Weak 49.5% (n=646)
- **2026-08-14 · v0.5_expanded_universe → 5d** (n=1517): Strong n/a (n=3) vs Weak 53.0% (n=696)
- **2026-05-27 · v0.5_expanded_universe → 60d** (n=904): Strong n/a (n=12) vs Weak 58.3% (n=422)

_Simulated cohorts are this exact model scored point-in-time on an earlier date, so they show how it is performing in the CURRENT market regime rather than waiting for a live track record to accrue. They are reconstructions: no slippage, no missed fills, and the universe is as constituted today._

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | n/a (n=0) | n/a (n=0) | 48.5% (n=2197) | 49.7% (n=237543) |
| 20d | n/a (n=0) | n/a (n=0) | 47.9% (n=5876) | 47.9% (n=213669) |
| 60d | n/a (n=0) | n/a (n=0) | 49.2% (n=6843) | 44.3% (n=185216) |
| 120d | n/a (n=0) | n/a (n=0) | 50.1% (n=6787) | 40.2% (n=138813) |

_Backfill baseline: v0.5_expanded_universe (541 sessions, 2024-06-24 → 2026-08-19)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 4 live trading day(s) since 2026-08-20. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.011 (n=750239), 20d +0.022 (n=728084), 60d +0.039 (n=669176), 120d +0.061 (n=580728)
  - quality_component: 5d -0.008 (n=755611), 20d -0.018 (n=733231), 60d -0.034 (n=673747), 120d -0.043 (n=584462)
  - short_interest_component: no IC yet

**4b. Drift on established components** (recent-window IC vs full history)
  - too early — accruing (4/60 live days)

---

## 2026-08-20 — v0.3_sector_neutral (live)

_Run: scored 1522 tickers in 5328.0s · fetch fresh=8 / cached=1518 / failed=1 (CWEN-A)_
_Warnings: 1 ticker(s) failed price fetch_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | JLL | Real Estate | 81.7 | strong | — |
| 2 | NMIH | Financials | 81.5 | strong | — |
| 3 | ADAM | Real Estate | 81.2 | strong | 69d |
| 4 | THC | Health Care | 81.1 | strong | — |
| 5 | MRP | Real Estate | 80.8 | strong | — |
| 6 | REGN | Health Care | 79.6 | decent | — |
| 7 | MTG | Financials | 79.5 | decent | — |
| 8 | PR | Energy | 78.7 | decent | — |
| 9 | GEF | Materials | 78.7 | decent | 69d |
| 10 | BDX | Health Care | 78.1 | decent | 77d |

**vs prev live run (2026-08-19):** entered [ADAM, BDX, MRP, MTG, NMIH, PR, REGN] · exited [GKOS, ICUI, ITGR, NEU, RGEN, SAFT, VCTR]
**Movers:** ↑ ARE +28.8, CNH +28.6, SCSC +26.9, MWA +21.4, PBI +20.5  ↓ PI -32.5, LGIH -30.9, RS -30.4, RCUS -29.8, JBSS -29.8

### 2. Predictions that came due today

**Live predictions**

_None matured today._

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | 48.0% (n=25) | 54.7% (n=6197) | 48.4% (n=2219) | 49.7% (n=237068) |
| 20d | 43.2% (n=44) | 62.6% (n=2332) | 47.8% (n=5921) | 47.9% (n=212799) |
| 60d | n/a (n=0) | n/a (n=0) | 49.2% (n=6789) | 44.1% (n=183594) |
| 120d | n/a (n=0) | n/a (n=0) | 50.3% (n=6699) | 40.0% (n=137292) |

_Backfill baseline: v0.5_expanded_universe (542 sessions, 2024-06-24 → 2026-08-20)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 33 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.039 (n=11657), 20d +0.154 (n=5064)
  - quality_component: 5d -0.025 (n=11634), 20d -0.037 (n=5054)
  - short_interest_component: 5d -0.033 (n=11542), 20d -0.079 (n=5014)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (26 component-horizon(s) in range)

---

## 2026-08-19 — v0.3_sector_neutral (live)

_Run: scored 1523 tickers in 1070.7s · fetch fresh=1 / cached=1525 / failed=1 (CWEN-A)_
_Warnings: 1 ticker(s) failed price fetch; 4 ticker(s) skipped (stale / no data)_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | SAFT | Financials | 92.1 | strong | — |
| 2 | ITGR | Health Care | 91.7 | strong | — |
| 3 | VCTR | Financials | 91.5 | strong | — |
| 4 | ICUI | Health Care | 91.3 | strong | — |
| 5 | GKOS | Health Care | 91.2 | strong | — |
| 6 | JLL | Real Estate | 90.6 | strong | — |
| 7 | THC | Health Care | 89.7 | strong | — |
| 8 | RGEN | Health Care | 89.6 | strong | — |
| 9 | NEU | Materials | 89.4 | strong | — |
| 10 | GEF | Materials | 89.0 | strong | — |

**vs prev live run (2026-08-18):** entered [GEF, GKOS, ICUI, ITGR, JLL, NEU, RGEN, SAFT, THC, VCTR] · exited [AMGN, BAC, BKNG, GD, JPM, LH, PH, REGN, RTX, SCHW]
**Movers:** ↑ CMG +24.0, CVNA +21.0, JKHY +21.0, OTIS +20.8, DHI +20.7  ↓ KEYS -22.5, STX -20.8, DELL -17.9, IRM -15.6, TER -14.7

### 2. Predictions that came due today

**Live predictions**

- **2026-07-22 · v0.3_sector_neutral → 20d** (n=514): Strong n/a (n=5) vs Weak 58.3% (n=247)
- **2026-08-12 · v0.3_sector_neutral → 5d** (n=515): Strong n/a (n=1) vs Weak 53.7% (n=246)

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | 48.0% (n=25) | 54.7% (n=6195) | 40.0% (n=25) | 60.3% (n=224) |
| 20d | 43.2% (n=44) | 62.6% (n=2332) | 35.7% (n=70) | 68.8% (n=215) |
| 60d | n/a (n=0) | n/a (n=0) | n/a (n=0) | n/a (n=0) |
| 120d | n/a (n=0) | n/a (n=0) | n/a (n=0) | n/a (n=0) |

_Backfill baseline: v0.3_sector_neutral (1 sessions, 2026-07-06 → 2026-07-06)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 32 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.039 (n=11655), 20d +0.155 (n=5062)
  - quality_component: 5d -0.025 (n=11632), 20d -0.036 (n=5052)
  - short_interest_component: 5d -0.033 (n=11540), 20d -0.079 (n=5012)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (26 component-horizon(s) in range)

---

## 2026-08-18 — v0.3_sector_neutral (recovered)

_Run: scored 520 tickers in unknown time · fetch fresh=0 / cached=0 / failed=0_
_Fundamentals: recovered — fundamentals stamped 2026-08-19 (not point-in-time)_
_Warnings: recovered missed day; fundamentals as of 2026-08-19, excluded from factor IC_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | SCHW | Financials | 78.7 | decent | — |
| 2 | BAC | Financials | 78.3 | decent | — |
| 3 | REGN | Health Care | 78.1 | decent | — |
| 4 | GD | Industrials | 78.1 | decent | — |
| 5 | RTX | Industrials | 77.8 | decent | — |
| 6 | JPM | Financials | 77.7 | decent | — |
| 7 | AMGN | Health Care | 77.7 | decent | — |
| 8 | BKNG | Consumer Discretionary | 77.2 | decent | — |
| 9 | LH | Health Care | 76.5 | decent | — |
| 10 | PH | Industrials | 75.5 | decent | — |

**vs prev live run (2026-08-17):** entered [BKNG, GD, PH, RTX] · exited [A, EMR, MU, NUE]
**Movers:** ↑ WMT +23.4, JKHY +20.7, GDDY +19.2, EFX +18.4, XLP +17.4  ↓ SMH -32.8, COHR -25.6, CVNA -24.7, WDC -23.7, TEL -23.4

### 2. Predictions that came due today

**Live predictions**

- **2026-07-21 · v0.3_sector_neutral → 20d** (n=515): Strong n/a (n=5) vs Weak 58.0% (n=269)
- **2026-08-11 · v0.3_sector_neutral → 5d** (n=516): Strong n/a (n=1) vs Weak 46.7% (n=240)

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | 38.2% (n=34) | 55.0% (n=6420) | 49.9% (n=4722) | 50.2% (n=171659) |
| 20d | 39.7% (n=58) | 63.7% (n=2539) | 48.1% (n=12851) | 48.4% (n=158274) |
| 60d | n/a (n=0) | n/a (n=0) | 51.3% (n=20383) | 45.7% (n=135952) |
| 120d | n/a (n=0) | n/a (n=0) | 52.6% (n=23048) | 41.1% (n=103487) |

_Backfill baseline: v0.4_edgar_pit_fundamentals (539 sessions, 2024-06-24 → 2026-08-17)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 32 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.039 (n=11655), 20d +0.155 (n=5062)
  - quality_component: 5d -0.025 (n=11632), 20d -0.036 (n=5052)
  - short_interest_component: 5d -0.033 (n=11540), 20d -0.079 (n=5012)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (26 component-horizon(s) in range)

---

## 2026-08-17 — v0.3_sector_neutral (live)

_Run: scored 519 tickers in 610.6s · fetch fresh=1 / cached=520 / failed=0_
_Warnings: 2 ticker(s) skipped (stale / no data)_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | NUE | Materials | 78.3 | decent | 70d |
| 2 | BAC | Financials | 78.1 | decent | 58d |
| 3 | JPM | Financials | 77.9 | decent | 57d |
| 4 | AMGN | Health Care | 77.5 | decent | 78d |
| 5 | REGN | Health Care | 77.4 | decent | 72d |
| 6 | MU | Semiconductors | 76.6 | decent | 37d |
| 7 | LH | Health Care | 76.5 | decent | 78d |
| 8 | EMR | Industrials | 76.4 | decent | 79d |
| 9 | SCHW | Financials | 76.2 | decent | 59d |
| 10 | A | Health Care | 76.1 | decent | 9d |

**vs prev live run (2026-08-14):** entered [A, LH, MU, SCHW] · exited [GD, GRMN, RTX, USB]
**Movers:** ↑ AMAT +15.0, UNP +14.7, CMG +14.6, NSC +12.4, CASY +11.7  ↓ STZ -24.9, ALGN -21.4, TAP -21.2, KDP -18.7, INVH -16.7

### 2. Predictions that came due today

**Live predictions**

- **2026-08-10 · v0.3_sector_neutral → 5d** (n=516): Strong n/a (n=0) vs Weak 49.1% (n=232)

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | 36.4% (n=33) | 55.3% (n=6179) | 49.9% (n=4721) | 50.2% (n=171423) |
| 20d | 37.7% (n=53) | 64.4% (n=2270) | 48.1% (n=12842) | 48.4% (n=158014) |
| 60d | n/a (n=0) | n/a (n=0) | 51.3% (n=20308) | 45.7% (n=135445) |
| 120d | n/a (n=0) | n/a (n=0) | 52.7% (n=22926) | 41.1% (n=103049) |

_Backfill baseline: v0.4_edgar_pit_fundamentals (539 sessions, 2024-06-24 → 2026-08-17)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 30 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.037 (n=10643), 20d +0.166 (n=4053)
  - quality_component: 5d -0.035 (n=10622), 20d -0.047 (n=4045)
  - short_interest_component: 5d -0.036 (n=10538), 20d -0.082 (n=4013)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (26 component-horizon(s) in range)

---

## 2026-08-14 — v0.3_sector_neutral (live)

_Run: scored 520 tickers in 533.6s · fetch fresh=520 / cached=1 / failed=0_
_Warnings: 1 ticker(s) skipped (stale / no data)_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | JPM | Financials | 77.5 | decent | 58d |
| 2 | BAC | Financials | 77.3 | decent | 59d |
| 3 | GRMN | Consumer Discretionary | 76.9 | decent | 73d |
| 4 | REGN | Health Care | 76.8 | decent | 73d |
| 5 | USB | Financials | 76.3 | decent | 60d |
| 6 | EMR | Industrials | 76.3 | decent | 80d |
| 7 | AMGN | Health Care | 76.1 | decent | 79d |
| 8 | RTX | Industrials | 76.0 | decent | 65d |
| 9 | GD | Industrials | 75.8 | decent | 73d |
| 10 | NUE | Materials | 75.5 | decent | 71d |

**vs prev live run (2026-08-13):** entered [RTX, USB] · exited [BKNG, PH]
**Movers:** ↑ AMD +19.3, F +14.3, ISRG +12.0, ALGN +11.2, SNPS +11.1  ↓ FFIV -19.5, JKHY -19.0, DE -16.9, HD -16.5, TJX -16.2

### 2. Predictions that came due today

**Live predictions**

- **2026-07-17 · v0.3_sector_neutral → 20d** (n=516): Strong n/a (n=5) vs Weak 62.6% (n=257)
- **2026-08-07 · v0.3_sector_neutral → 5d** (n=517): Strong n/a (n=0) vs Weak 50.9% (n=232)

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | 36.4% (n=33) | 55.6% (n=5947) | 49.6% (n=3652) | 50.0% (n=84437) |
| 20d | 37.7% (n=53) | 64.4% (n=2270) | 48.2% (n=10265) | 48.1% (n=78383) |
| 60d | n/a (n=0) | n/a (n=0) | 51.1% (n=17061) | 45.9% (n=67027) |
| 120d | n/a (n=0) | n/a (n=0) | 53.0% (n=19583) | 41.5% (n=50683) |

_Backfill baseline: v0.1_price_volume_only (504 sessions, 2024-06-24 → 2026-06-26)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 29 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.045 (n=10137), 20d +0.166 (n=4053)
  - quality_component: 5d -0.033 (n=10117), 20d -0.047 (n=4045)
  - short_interest_component: 5d -0.039 (n=10037), 20d -0.082 (n=4013)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (26 component-horizon(s) in range)

---

## 2026-08-13 — v0.3_sector_neutral (recovered)

_Run: scored 520 tickers in unknown time · fetch fresh=0 / cached=0 / failed=0_
_Fundamentals: recovered — fundamentals stamped 2026-08-16 (not point-in-time)_
_Warnings: recovered missed day; fundamentals as of 2026-08-16, excluded from factor IC_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | JPM | Financials | 77.6 | decent | — |
| 2 | BAC | Financials | 77.3 | decent | — |
| 3 | REGN | Health Care | 77.1 | decent | — |
| 4 | NUE | Materials | 76.9 | decent | — |
| 5 | GRMN | Consumer Discretionary | 76.9 | decent | — |
| 6 | AMGN | Health Care | 76.5 | decent | — |
| 7 | EMR | Industrials | 76.5 | decent | — |
| 8 | PH | Industrials | 76.0 | decent | — |
| 9 | GD | Industrials | 75.6 | decent | — |
| 10 | BKNG | Consumer Discretionary | 75.4 | decent | — |

**vs prev live run (2026-08-12):** entered [BKNG, REGN] · exited [DGX, USB]
**Movers:** ↑ SNDK +22.0, FISV +20.6, XYZ +16.0, HOOD +14.8, WDC +14.8  ↓ TPR -27.3, MCD -16.7, RL -15.4, CTAS -12.8, CSCO -11.7

### 2. Predictions that came due today

**Live predictions**

- **2026-07-16 · v0.3_sector_neutral → 20d** (n=516): Strong n/a (n=4) vs Weak 64.4% (n=225)
- **2026-08-06 · v0.3_sector_neutral → 5d** (n=516): Strong n/a (n=1) vs Weak 53.1% (n=241)

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | 36.4% (n=33) | 55.7% (n=5715) | 49.6% (n=3652) | 50.0% (n=84437) |
| 20d | 39.6% (n=48) | 64.6% (n=2013) | 48.2% (n=10265) | 48.1% (n=78383) |
| 60d | n/a (n=0) | n/a (n=0) | 51.1% (n=17012) | 45.8% (n=66747) |
| 120d | n/a (n=0) | n/a (n=0) | 53.0% (n=19478) | 41.4% (n=50466) |

_Backfill baseline: v0.1_price_volume_only (504 sessions, 2024-06-24 → 2026-06-26)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 29 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.045 (n=10137), 20d +0.166 (n=4053)
  - quality_component: 5d -0.033 (n=10117), 20d -0.047 (n=4045)
  - short_interest_component: 5d -0.039 (n=10037), 20d -0.082 (n=4013)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (26 component-horizon(s) in range)

---

## 2026-08-12 — v0.3_sector_neutral (live)

_Run: scored 520 tickers in 578.1s · fetch fresh=520 / cached=1 / failed=0_
_Warnings: 1 ticker(s) skipped (stale / no data)_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | BAC | Financials | 78.4 | decent | 63d |
| 2 | JPM | Financials | 77.6 | decent | 62d |
| 3 | GD | Industrials | 77.4 | decent | 77d |
| 4 | GRMN | Consumer Discretionary | 77.3 | decent | 77d |
| 5 | USB | Financials | 76.7 | decent | 64d |
| 6 | EMR | Industrials | 76.6 | decent | 84d |
| 7 | AMGN | Health Care | 76.4 | decent | 83d |
| 8 | NUE | Materials | 76.4 | decent | 75d |
| 9 | PH | Industrials | 76.3 | decent | 85d |
| 10 | DGX | Health Care | 75.7 | decent | 69d |

**vs prev live run (2026-08-11):** entered [AMGN, DGX, GD, PH] · exited [ALL, BKNG, MMM, TRV]
**Movers:** ↑ SMCI +27.3, LITE +22.5, STX +20.2, MU +16.7, DELL +16.4  ↓ FISV -18.4, NVR -14.5, DHI -14.0, FSLR -13.5, LEN -12.2

### 2. Predictions that came due today

**Live predictions**

- **2026-07-15 · v0.3_sector_neutral → 20d** (n=516): Strong n/a (n=5) vs Weak 62.7% (n=249)
- **2026-08-05 · v0.3_sector_neutral → 5d** (n=516): Strong n/a (n=0) vs Weak 48.7% (n=273)

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | 37.5% (n=32) | 55.9% (n=5474) | 49.6% (n=3652) | 50.0% (n=84437) |
| 20d | 40.9% (n=44) | 64.7% (n=1788) | 48.2% (n=10265) | 48.1% (n=78383) |
| 60d | n/a (n=0) | n/a (n=0) | 51.1% (n=16961) | 45.8% (n=66469) |
| 120d | n/a (n=0) | n/a (n=0) | 53.1% (n=19363) | 41.4% (n=50256) |

_Backfill baseline: v0.1_price_volume_only (504 sessions, 2024-06-24 → 2026-06-26)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 27 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.059 (n=9124), 20d +0.187 (n=3041)
  - quality_component: 5d -0.028 (n=9106), 20d -0.037 (n=3035)
  - short_interest_component: 5d -0.035 (n=9034), 20d -0.083 (n=3011)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (26 component-horizon(s) in range)

---

## 2026-08-11 — v0.3_sector_neutral (live)

_Run: scored 520 tickers in 566.2s · fetch fresh=521 / cached=0 / failed=0_
_Warnings: 1 ticker(s) skipped (stale / no data)_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | GRMN | Consumer Discretionary | 77.6 | decent | 78d |
| 2 | BAC | Financials | 77.6 | decent | 64d |
| 3 | TRV | Financials | 77.4 | decent | 65d |
| 4 | ALL | Financials | 77.2 | decent | 85d |
| 5 | EMR | Industrials | 76.8 | decent | 85d |
| 6 | JPM | Financials | 76.5 | decent | 63d |
| 7 | MMM | Industrials | 76.1 | decent | 70d |
| 8 | USB | Financials | 76.0 | decent | 65d |
| 9 | BKNG | Consumer Discretionary | 75.9 | decent | 77d |
| 10 | NUE | Materials | 75.8 | decent | 76d |

**vs prev live run (2026-08-10):** entered [EMR, GRMN, USB] · exited [AMGN, GD, PH]
**Movers:** ↑ NVR +15.1, IBM +14.3, DHI +13.5, SBUX +11.6, JBL +10.3  ↓ GOOG -20.7, GOOGL -19.5, DDOG -19.0, MNST -18.1, VTR -14.7

### 2. Predictions that came due today

**Live predictions**

- **2026-08-04 · v0.3_sector_neutral → 5d** (n=516): Strong n/a (n=1) vs Weak 49.8% (n=281)

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | 37.5% (n=32) | 56.2% (n=5201) | 49.6% (n=3652) | 50.0% (n=84437) |
| 20d | 38.5% (n=39) | 65.0% (n=1539) | 48.2% (n=10265) | 48.1% (n=78383) |
| 60d | n/a (n=0) | n/a (n=0) | 51.2% (n=16912) | 45.7% (n=66170) |
| 120d | n/a (n=0) | n/a (n=0) | 53.1% (n=19261) | 41.4% (n=50041) |

_Backfill baseline: v0.1_price_volume_only (504 sessions, 2024-06-24 → 2026-06-26)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 26 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.068 (n=8618), 20d +0.196 (n=2535)
  - quality_component: 5d -0.025 (n=8601), 20d -0.033 (n=2530)
  - short_interest_component: 5d -0.037 (n=8533), 20d -0.081 (n=2510)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (26 component-horizon(s) in range)

---

## 2026-08-10 — v0.3_sector_neutral (live)

_Run: scored 520 tickers in 507.4s · fetch fresh=520 / cached=1 / failed=0_
_Warnings: 1 ticker(s) skipped (stale / no data)_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | ALL | Financials | 80.1 | strong | 86d |
| 2 | BAC | Financials | 79.1 | decent | 65d |
| 3 | NUE | Materials | 77.8 | decent | 77d |
| 4 | JPM | Financials | 77.5 | decent | 64d |
| 5 | TRV | Financials | 77.4 | decent | 66d |
| 6 | BKNG | Consumer Discretionary | 76.8 | decent | 78d |
| 7 | GD | Industrials | 76.3 | decent | 79d |
| 8 | AMGN | Health Care | 76.3 | decent | 85d |
| 9 | MMM | Industrials | 75.7 | decent | 71d |
| 10 | PH | Industrials | 75.5 | decent | 87d |

**vs prev live run (2026-08-07):** entered [GD] · exited [BMY]
**Movers:** ↑ DDOG +20.1, CF +15.0, LYB +14.6, XLE +14.6, EOG +14.2  ↓ DG -20.0, VRSK -18.4, XLRE -15.3, CCL -14.4, VICI -13.1

### 2. Predictions that came due today

**Live predictions**

- **2026-07-13 · v0.3_sector_neutral → 20d** (n=516): Strong n/a (n=3) vs Weak 63.4% (n=232)
- **2026-08-03 · v0.3_sector_neutral → 5d** (n=516): Strong n/a (n=1) vs Weak 51.5% (n=305)

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | 38.7% (n=31) | 56.6% (n=4919) | 49.6% (n=3652) | 50.0% (n=84437) |
| 20d | 38.5% (n=39) | 65.0% (n=1539) | 48.2% (n=10265) | 48.1% (n=78383) |
| 60d | n/a (n=0) | n/a (n=0) | 51.2% (n=16848) | 45.6% (n=65905) |
| 120d | n/a (n=0) | n/a (n=0) | 53.2% (n=19150) | 41.4% (n=49840) |

_Backfill baseline: v0.1_price_volume_only (504 sessions, 2024-06-24 → 2026-06-26)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 25 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.074 (n=8111), 20d +0.196 (n=2534)
  - quality_component: 5d -0.024 (n=8095), 20d -0.033 (n=2529)
  - short_interest_component: 5d -0.039 (n=8031), 20d -0.081 (n=2509)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (26 component-horizon(s) in range)

---

## 2026-08-07 — v0.3_sector_neutral (live)

_Run: scored 521 tickers in 539.1s · fetch fresh=520 / cached=1 / failed=0_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | ALL | Financials | 79.9 | decent | 87d |
| 2 | TRV | Financials | 79.9 | decent | 67d |
| 3 | NUE | Materials | 78.6 | decent | 78d |
| 4 | BAC | Financials | 77.6 | decent | 66d |
| 5 | JPM | Financials | 77.5 | decent | 65d |
| 6 | BKNG | Consumer Discretionary | 76.9 | decent | 79d |
| 7 | MMM | Industrials | 76.5 | decent | 72d |
| 8 | PH | Industrials | 76.2 | decent | 88d |
| 9 | BMY | Health Care | 76.2 | decent | 81d |
| 10 | AMGN | Health Care | 76.0 | decent | 86d |

**vs prev live run (2026-08-06):** entered [AMGN, BMY, PH] · exited [ADP, GRMN, RTX]
**Movers:** ↑ TTWO +31.6, WBD +26.6, MCHP +24.9, CEG +23.0, FOXA +20.0  ↓ CDW -15.1, CSCO -14.6, EQIX -13.1, FFIV -12.9, DOW -12.3

### 2. Predictions that came due today

**Live predictions**

- **2026-07-10 · v0.3_sector_neutral → 20d** (n=517): Strong n/a (n=2) vs Weak 68.1% (n=204)
- **2026-07-31 · v0.3_sector_neutral → 5d** (n=517): Strong n/a (n=0) vs Weak 59.3% (n=312)

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | 40.0% (n=30) | 57.0% (n=4614) | 49.6% (n=3652) | 50.0% (n=84437) |
| 20d | 36.1% (n=36) | 65.3% (n=1307) | 48.2% (n=10265) | 48.1% (n=78383) |
| 60d | n/a (n=0) | n/a (n=0) | 51.3% (n=16786) | 45.5% (n=65632) |
| 120d | n/a (n=0) | n/a (n=0) | 53.2% (n=19042) | 41.4% (n=49630) |

_Backfill baseline: v0.1_price_volume_only (504 sessions, 2024-06-24 → 2026-06-26)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 24 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.080 (n=7605), 20d +0.207 (n=2028)
  - quality_component: 5d -0.021 (n=7590), 20d -0.036 (n=2024)
  - short_interest_component: 5d -0.038 (n=7530), 20d -0.083 (n=2008)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (26 component-horizon(s) in range)

---

## 2026-08-06 — v0.3_sector_neutral (live)

_Run: scored 519 tickers in 566.1s · fetch fresh=520 / cached=0 / failed=0_
_Warnings: 1 ticker(s) skipped (stale / no data)_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | ALL | Financials | 84.0 | strong | 90d |
| 2 | TRV | Financials | 80.8 | strong | 70d |
| 3 | NUE | Materials | 78.9 | decent | 81d |
| 4 | BAC | Financials | 78.0 | decent | 69d |
| 5 | JPM | Financials | 77.5 | decent | 68d |
| 6 | GRMN | Consumer Discretionary | 76.8 | decent | 83d |
| 7 | MMM | Industrials | 76.4 | decent | 75d |
| 8 | ADP | Industrials | 76.4 | decent | 83d |
| 9 | RTX | Industrials | 76.2 | decent | 75d |
| 10 | BKNG | Consumer Discretionary | 76.0 | decent | 82d |

**vs prev live run (2026-08-05):** entered [ADP, ALL, BKNG, GRMN] · exited [AMGN, DGX, EMR, SWK]
**Movers:** ↑ APA +34.7, OXY +27.0, DIS +22.1, MSI +21.1, COR +19.8  ↓ DDOG -30.7, NCLH -24.8, VTRS -22.5, DHI -19.7, LITE -16.9

### 2. Predictions that came due today

**Live predictions**

- **2026-07-09 · v0.3_sector_neutral → 20d** (n=516): Strong n/a (n=4) vs Weak 65.3% (n=222)

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | 40.0% (n=30) | 56.8% (n=4302) | 49.6% (n=3652) | 50.0% (n=84437) |
| 20d | 35.3% (n=34) | 64.7% (n=1103) | 48.2% (n=10265) | 48.1% (n=78383) |
| 60d | n/a (n=0) | n/a (n=0) | 51.4% (n=16722) | 45.4% (n=65368) |
| 120d | n/a (n=0) | n/a (n=0) | 53.2% (n=18937) | 41.4% (n=49417) |

_Backfill baseline: v0.1_price_volume_only (504 sessions, 2024-06-24 → 2026-06-26)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 23 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.079 (n=7098), 20d +0.208 (n=1520)
  - quality_component: 5d -0.012 (n=7084), 20d -0.039 (n=1517)
  - short_interest_component: 5d -0.032 (n=7028), 20d -0.088 (n=1505)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (26 component-horizon(s) in range)

---

## 2026-08-05 — v0.3_sector_neutral (live)

_Run: scored 519 tickers in 610.9s · fetch fresh=520 / cached=0 / failed=0_
_Warnings: 1 ticker(s) skipped (stale / no data)_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | NUE | Materials | 79.4 | decent | 82d |
| 2 | TRV | Financials | 79.0 | decent | 71d |
| 3 | JPM | Financials | 78.6 | decent | 69d |
| 4 | BAC | Financials | 78.3 | decent | 70d |
| 5 | MMM | Industrials | 76.7 | decent | 76d |
| 6 | RTX | Industrials | 76.6 | decent | 76d |
| 7 | EMR | Industrials | 76.2 | decent | 91d |
| 8 | SWK | Industrials | 76.1 | decent | — |
| 9 | DGX | Health Care | 75.8 | decent | 76d |
| 10 | AMGN | Health Care | 75.6 | decent | 90d |

**vs prev live run (2026-08-04):** entered [AMGN, DGX, EMR, RTX] · exited [ADP, BMY, GRMN, VRSN]
**Movers:** ↑ MCD +25.8, IFF +25.7, WYNN +24.8, SYY +22.7, KMB +19.7  ↓ PODD -21.6, CVS -21.4, AKAM -18.1, WDC -17.4, XLE -15.3

### 2. Predictions that came due today

**Live predictions**

- **2026-07-08 · v0.3_sector_neutral → 20d** (n=516): Strong n/a (n=5) vs Weak 60.3% (n=224)
- **2026-07-29 · v0.3_sector_neutral → 5d** (n=516): Strong n/a (n=2) vs Weak 53.4% (n=279)

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | 40.0% (n=30) | 56.8% (n=4302) | 49.6% (n=3652) | 50.0% (n=84437) |
| 20d | 33.3% (n=30) | 64.6% (n=881) | 48.2% (n=10265) | 48.1% (n=78383) |
| 60d | n/a (n=0) | n/a (n=0) | 51.4% (n=16663) | 45.3% (n=65107) |
| 120d | n/a (n=0) | n/a (n=0) | 53.2% (n=18837) | 41.4% (n=49204) |

_Backfill baseline: v0.1_price_volume_only (504 sessions, 2024-06-24 → 2026-06-26)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 22 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.079 (n=7097), 20d +0.202 (n=1013)
  - quality_component: 5d -0.012 (n=7083), 20d -0.062 (n=1011)
  - short_interest_component: 5d -0.032 (n=7027), 20d -0.103 (n=1003)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (26 component-horizon(s) in range)

---

## 2026-08-04 — v0.3_sector_neutral (live)

_Run: scored 520 tickers in 496.8s · fetch fresh=520 / cached=0 / failed=0_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | BMY | Health Care | 79.2 | decent | 86d |
| 2 | BAC | Financials | 78.1 | decent | 71d |
| 3 | TRV | Financials | 78.0 | decent | 72d |
| 4 | JPM | Financials | 77.5 | decent | 70d |
| 5 | MMM | Industrials | 76.1 | decent | 77d |
| 6 | NUE | Materials | 76.0 | decent | 83d |
| 7 | SWK | Industrials | 75.2 | decent | — |
| 8 | ADP | Industrials | 74.9 | decent | 85d |
| 9 | VRSN | Information Technology | 74.8 | decent | 79d |
| 10 | GRMN | Consumer Discretionary | 74.6 | decent | 85d |

**vs prev live run (2026-08-03):** entered [NUE, SWK, VRSN] · exited [GL, RTX, TGT]
**Movers:** ↑ PLTR +51.7, HUBB +25.3, SBAC +24.4, TER +23.5, CLX +21.5  ↓ CMG -26.5, GWW -23.1, ROK -22.3, PLD -17.3, ARE -15.9

### 2. Predictions that came due today

**Live predictions**

- **2026-07-07 · v0.3_sector_neutral → 20d** (n=517): Strong n/a (n=6) vs Weak 64.5% (n=203)
- **2026-07-28 · v0.3_sector_neutral → 5d** (n=517): Strong n/a (n=1) vs Weak 57.5% (n=280)

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | 42.9% (n=28) | 57.0% (n=4023) | 49.6% (n=3652) | 50.0% (n=84437) |
| 20d | 36.0% (n=25) | 66.1% (n=657) | 48.2% (n=10265) | 48.1% (n=78383) |
| 60d | n/a (n=0) | n/a (n=0) | 51.5% (n=16611) | 45.3% (n=64839) |
| 120d | n/a (n=0) | n/a (n=0) | 53.3% (n=18732) | 41.4% (n=48997) |

_Backfill baseline: v0.1_price_volume_only (504 sessions, 2024-06-24 → 2026-06-26)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 21 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.097 (n=6591), 20d +0.200 (n=507)
  - quality_component: 5d -0.003 (n=6578), 20d -0.069 (n=506)
  - short_interest_component: 5d -0.041 (n=6526), 20d -0.099 (n=502)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (26 component-horizon(s) in range)

---

## 2026-08-03 — v0.3_sector_neutral (live)

_Run: scored 520 tickers in 487.8s · fetch fresh=520 / cached=0 / failed=0_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | BMY | Health Care | 79.8 | decent | 87d |
| 2 | TRV | Financials | 78.6 | decent | 73d |
| 3 | BAC | Financials | 78.3 | decent | 72d |
| 4 | JPM | Financials | 76.7 | decent | 71d |
| 5 | ADP | Industrials | 75.7 | decent | 86d |
| 6 | MMM | Industrials | 75.6 | decent | 78d |
| 7 | GRMN | Consumer Discretionary | 74.9 | decent | 86d |
| 8 | RTX | Industrials | 74.9 | decent | 78d |
| 9 | GL | Financials | 74.6 | decent | 79d |
| 10 | TGT | Consumer Staples | 74.6 | decent | 16d |

**vs prev live run (2026-07-31):** entered [ADP, GL, GRMN, RTX, TGT] · exited [BNY, KO, SCHW, SPG, STT]
**Movers:** ↑ NCLH +25.2, XLC +23.7, GDDY +22.2, BA +20.1, TSN +18.6  ↓ EBAY -19.1, MAR -17.5, STX -16.6, WDC -12.8, DVA -12.7

### 2. Predictions that came due today

**Live predictions**

- **2026-07-27 · v0.3_sector_neutral → 5d** (n=517): Strong n/a (n=0) vs Weak 52.7% (n=317)

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | 44.4% (n=27) | 57.0% (n=3743) | 49.6% (n=3652) | 50.0% (n=84437) |
| 20d | n/a (n=19) | 66.7% (n=454) | 48.2% (n=10265) | 48.1% (n=78383) |
| 60d | n/a (n=0) | n/a (n=0) | 51.5% (n=16554) | 45.2% (n=64575) |
| 120d | n/a (n=0) | n/a (n=0) | 53.3% (n=18623) | 41.4% (n=48795) |

_Backfill baseline: v0.1_price_volume_only (504 sessions, 2024-06-24 → 2026-06-26)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 20 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.112 (n=6084)
  - quality_component: 5d +0.002 (n=6072)
  - short_interest_component: 5d -0.046 (n=6024)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (13 component-horizon(s) in range)

---

## 2026-07-31 — v0.3_sector_neutral (live)

_Run: scored 520 tickers in 484.6s · fetch fresh=520 / cached=0 / failed=0_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | BAC | Financials | 79.0 | decent | 72d |
| 2 | TRV | Financials | 78.9 | decent | 73d |
| 3 | BMY | Health Care | 78.3 | decent | 87d |
| 4 | JPM | Financials | 78.1 | decent | 71d |
| 5 | STT | Financials | 76.8 | decent | 74d |
| 6 | SPG | Real Estate | 75.7 | decent | 7d |
| 7 | SCHW | Financials | 75.6 | decent | 73d |
| 8 | BNY | Financials | 75.3 | decent | 73d |
| 9 | MMM | Industrials | 74.8 | decent | 78d |
| 10 | KO | Consumer Staples | 74.8 | decent | 78d |

**vs prev live run (2026-07-30):** entered [BMY, BNY, MMM, SCHW, STT] · exited [ALL, EIX, HST, PCG, SOLV]
**Movers:** ↑ WY +27.9, XLY +26.7, SPY +26.5, ETN +25.4, AMZN +23.9  ↓ CTVA -34.7, TSN -34.3, GDDY -32.1, XLB -30.0, MOS -24.6

### 2. Predictions that came due today

**Live predictions**

- **2026-07-02 · v0.2_fundamentals_added → 20d** (n=517): Strong n/a (n=9) vs Weak 65.5% (n=226)
- **2026-07-24 · v0.3_sector_neutral → 5d** (n=517): Strong n/a (n=1) vs Weak 57.4% (n=329)

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | 44.4% (n=27) | 57.4% (n=3426) | 49.6% (n=3652) | 50.0% (n=84437) |
| 20d | n/a (n=19) | 66.7% (n=454) | 48.3% (n=10195) | 48.0% (n=78168) |
| 60d | n/a (n=0) | n/a (n=0) | 51.5% (n=16492) | 45.2% (n=64317) |
| 120d | n/a (n=0) | n/a (n=0) | 53.3% (n=18509) | 41.4% (n=48596) |

_Backfill baseline: v0.1_price_volume_only (504 sessions, 2024-06-24 → 2026-06-26)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 19 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.116 (n=5577)
  - quality_component: 5d +0.003 (n=5566)
  - short_interest_component: 5d -0.049 (n=5522)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (13 component-horizon(s) in range)

---

## 2026-07-30 — v0.3_sector_neutral (recovered)

_Run: scored 520 tickers in unknown time · fetch fresh=0 / cached=0 / failed=0_
_Fundamentals: recovered — fundamentals stamped 2026-07-31 (not point-in-time)_
_Warnings: recovered missed day; fundamentals as of 2026-07-31, excluded from factor IC_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | ALL | Financials | 82.6 | strong | — |
| 2 | TRV | Financials | 80.0 | strong | — |
| 3 | BAC | Financials | 77.9 | decent | — |
| 4 | HST | Real Estate | 76.9 | decent | — |
| 5 | EIX | Utilities | 76.9 | decent | — |
| 6 | SPG | Real Estate | 76.6 | decent | — |
| 7 | JPM | Financials | 76.3 | decent | — |
| 8 | KO | Consumer Staples | 75.6 | decent | — |
| 9 | SOLV | Health Care | 75.5 | decent | — |
| 10 | PCG | Utilities | 75.4 | decent | — |

**vs prev live run (2026-07-29):** entered [EIX, HST, JPM, KO, PCG] · exited [ACGL, HIG, INCY, KHC, PM]
**Movers:** ↑ MSFT +31.1, HII +30.8, YUM +30.8, EME +30.4, APH +27.3  ↓ RSG -21.4, FICO -18.1, GIS -16.7, EQR -16.2, AVB -15.9

### 2. Predictions that came due today

**Live predictions**

- **2026-07-01 · v0.2_fundamentals_added → 20d** (n=517): Strong n/a (n=10) vs Weak 68.0% (n=228)

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | 42.3% (n=26) | 57.4% (n=3097) | 49.6% (n=3652) | 50.0% (n=84437) |
| 20d | n/a (n=10) | 68.0% (n=228) | 48.3% (n=10195) | 48.0% (n=78168) |
| 60d | n/a (n=0) | n/a (n=0) | 51.6% (n=16437) | 45.1% (n=64059) |
| 120d | n/a (n=0) | n/a (n=0) | 53.3% (n=18392) | 41.4% (n=48396) |

_Backfill baseline: v0.1_price_volume_only (504 sessions, 2024-06-24 → 2026-06-26)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 19 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.116 (n=5577)
  - quality_component: 5d +0.003 (n=5566)
  - short_interest_component: 5d -0.049 (n=5522)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (13 component-horizon(s) in range)

---

## 2026-07-29 — v0.3_sector_neutral (live)

_Run: scored 520 tickers in 607.9s · fetch fresh=520 / cached=0 / failed=0_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | ALL | Financials | 85.4 | strong | 7d |
| 2 | TRV | Financials | 81.7 | strong | 78d |
| 3 | SPG | Real Estate | 76.5 | decent | 12d |
| 4 | PM | Consumer Staples | 76.3 | decent | 84d |
| 5 | SOLV | Health Care | 76.2 | decent | 7d |
| 6 | ACGL | Financials | 75.9 | decent | 89d |
| 7 | KHC | Consumer Staples | 75.9 | decent | 7d |
| 8 | BAC | Financials | 75.4 | decent | 77d |
| 9 | INCY | Health Care | 75.2 | decent | 90d |
| 10 | HIG | Financials | 75.1 | decent | — |

**vs prev live run (2026-07-28):** entered [ACGL, HIG, INCY] · exited [JPM, MMM, RTX]
**Movers:** ↑ AMT +29.1, EXE +22.7, GEHC +18.5, MDLZ +18.5, BXP +15.2  ↓ MAS -30.0, FTV -25.1, XLI -18.8, SMCI -18.4, PG -17.9

### 2. Predictions that came due today

**Live predictions**

- **2026-07-22 · v0.3_sector_neutral → 5d** (n=517): Strong n/a (n=4) vs Weak 65.0% (n=280)

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | 42.3% (n=26) | 57.4% (n=3097) | 49.6% (n=3652) | 50.0% (n=84437) |
| 20d | n/a (n=0) | n/a (n=0) | 48.3% (n=10195) | 48.0% (n=78168) |
| 60d | n/a (n=0) | n/a (n=0) | 51.6% (n=16382) | 45.1% (n=63801) |
| 120d | n/a (n=0) | n/a (n=0) | 53.4% (n=18300) | 41.4% (n=48176) |

_Backfill baseline: v0.1_price_volume_only (504 sessions, 2024-06-24 → 2026-06-26)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 17 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.120 (n=5070)
  - quality_component: 5d -0.005 (n=5060)
  - short_interest_component: 5d -0.051 (n=5020)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (13 component-horizon(s) in range)

---

## 2026-07-28 — v0.3_sector_neutral (live)

_Run: scored 520 tickers in 474.5s · fetch fresh=520 / cached=0 / failed=0_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | ALL | Financials | 83.9 | strong | 8d |
| 2 | TRV | Financials | 82.0 | strong | 79d |
| 3 | PM | Consumer Staples | 77.6 | decent | 85d |
| 4 | BAC | Financials | 77.3 | decent | 78d |
| 5 | JPM | Financials | 77.0 | decent | 77d |
| 6 | RTX | Industrials | 76.3 | decent | 84d |
| 7 | SPG | Real Estate | 76.1 | decent | 13d |
| 8 | MMM | Industrials | 76.0 | decent | 84d |
| 9 | KHC | Consumer Staples | 75.2 | decent | 8d |
| 10 | SOLV | Health Care | 74.0 | decent | 8d |

**vs prev live run (2026-07-27):** entered [KHC, MMM, SOLV] · exited [BNY, CSX, STT]
**Movers:** ↑ BA +21.9, BRO +20.7, DECK +19.5, SHW +18.1, NUE +17.5  ↓ TXT -25.6, UPS -24.6, JCI -18.3, CARR -18.0, HUBB -15.2

### 2. Predictions that came due today

**Live predictions**

- **2026-07-21 · v0.3_sector_neutral → 5d** (n=517): Strong n/a (n=1) vs Weak 62.9% (n=283)

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | 31.8% (n=22) | 56.6% (n=2817) | 49.6% (n=3652) | 50.0% (n=84437) |
| 20d | n/a (n=0) | n/a (n=0) | 48.3% (n=10195) | 48.0% (n=78168) |
| 60d | n/a (n=0) | n/a (n=0) | 51.6% (n=16317) | 45.0% (n=63565) |
| 120d | n/a (n=0) | n/a (n=0) | 53.4% (n=18202) | 41.4% (n=47960) |

_Backfill baseline: v0.1_price_volume_only (504 sessions, 2024-06-24 → 2026-06-26)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 16 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.112 (n=4563)
  - quality_component: 5d -0.016 (n=4554)
  - short_interest_component: 5d -0.039 (n=4518)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (13 component-horizon(s) in range)

---

## 2026-07-27 — v0.3_sector_neutral (live)

_Run: scored 520 tickers in 471.5s · fetch fresh=520 / cached=0 / failed=0_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | TRV | Financials | 82.8 | strong | 80d |
| 2 | ALL | Financials | 82.8 | strong | 9d |
| 3 | PM | Consumer Staples | 81.0 | strong | 86d |
| 4 | JPM | Financials | 79.4 | decent | 78d |
| 5 | BAC | Financials | 79.2 | decent | 79d |
| 6 | RTX | Industrials | 78.3 | decent | 85d |
| 7 | CSX | Industrials | 77.0 | decent | 87d |
| 8 | BNY | Financials | 76.9 | decent | 80d |
| 9 | SPG | Real Estate | 76.5 | decent | 14d |
| 10 | STT | Financials | 76.1 | decent | 81d |

**vs prev live run (2026-07-24):** entered [SPG, STT] · exited [PCG, UNP]
**Movers:** ↑ BF-B +23.7, TSN +23.5, BKR +20.6, DG +19.3, TTWO +18.7  ↓ TRGP -19.0, CHRW -18.0, OKE -14.2, KMI -13.5, DOW -13.0

### 2. Predictions that came due today

**Live predictions**

_None matured today._

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | 28.6% (n=21) | 55.9% (n=2534) | 49.6% (n=3652) | 50.0% (n=84437) |
| 20d | n/a (n=0) | n/a (n=0) | 48.3% (n=10195) | 48.0% (n=78168) |
| 60d | n/a (n=0) | n/a (n=0) | 51.6% (n=16236) | 45.0% (n=63337) |
| 120d | n/a (n=0) | n/a (n=0) | 53.4% (n=18105) | 41.4% (n=47747) |

_Backfill baseline: v0.1_price_volume_only (504 sessions, 2024-06-24 → 2026-06-26)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 15 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.099 (n=4056)
  - quality_component: 5d -0.024 (n=4048)
  - short_interest_component: 5d -0.024 (n=4016)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (13 component-horizon(s) in range)

---

## 2026-07-24 — v0.3_sector_neutral (live)

_Run: scored 520 tickers in 477.7s · fetch fresh=520 / cached=0 / failed=0_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | ALL | Financials | 84.4 | strong | 10d |
| 2 | TRV | Financials | 82.7 | strong | 81d |
| 3 | BAC | Financials | 79.6 | decent | 80d |
| 4 | CSX | Industrials | 79.5 | decent | 88d |
| 5 | PM | Consumer Staples | 79.1 | decent | 87d |
| 6 | PCG | Utilities | 78.5 | decent | 88d |
| 7 | JPM | Financials | 77.6 | decent | 79d |
| 8 | BNY | Financials | 77.3 | decent | 81d |
| 9 | RTX | Industrials | 76.9 | decent | 86d |
| 10 | UNP | Industrials | 76.7 | decent | 88d |

**vs prev live run (2026-07-23):** entered [PCG, RTX] · exited [EIX, GD]
**Movers:** ↑ DLR +17.3, NOW +15.0, XLB +14.9, MSI +14.7, XLP +14.5  ↓ CHRW -30.5, ETN -27.4, HOOD -26.9, STX -23.7, WST -21.4

### 2. Predictions that came due today

**Live predictions**

- **2026-07-17 · v0.3_sector_neutral → 5d** (n=517): Strong n/a (n=2) vs Weak 53.9% (n=282)

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | 28.6% (n=21) | 55.9% (n=2534) | 49.6% (n=3652) | 50.0% (n=84437) |
| 20d | n/a (n=0) | n/a (n=0) | 48.3% (n=10152) | 48.0% (n=77945) |
| 60d | n/a (n=0) | n/a (n=0) | 51.6% (n=16174) | 44.9% (n=63073) |
| 120d | n/a (n=0) | n/a (n=0) | 53.4% (n=18004) | 41.4% (n=47536) |

_Backfill baseline: v0.1_price_volume_only (504 sessions, 2024-06-24 → 2026-06-26)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 14 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.099 (n=4056)
  - quality_component: 5d -0.024 (n=4048)
  - short_interest_component: 5d -0.024 (n=4016)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (13 component-horizon(s) in range)

---

## 2026-07-23 — v0.3_sector_neutral (recovered)

_Run: scored 520 tickers in unknown time · fetch fresh=0 / cached=0 / failed=0_
_Fundamentals: recovered — fundamentals stamped 2026-07-24 (not point-in-time)_
_Warnings: recovered missed day; fundamentals as of 2026-07-24, excluded from factor IC_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | EIX | Utilities | 83.9 | strong | — |
| 2 | ALL | Financials | 83.8 | strong | — |
| 3 | TRV | Financials | 82.7 | strong | — |
| 4 | GD | Industrials | 81.9 | strong | — |
| 5 | CSX | Industrials | 81.1 | strong | — |
| 6 | BAC | Financials | 80.4 | strong | — |
| 7 | BNY | Financials | 79.8 | decent | — |
| 8 | PM | Consumer Staples | 78.8 | decent | — |
| 9 | JPM | Financials | 78.3 | decent | — |
| 10 | UNP | Industrials | 78.1 | decent | — |

**vs prev live run (2026-07-22):** entered [CSX, JPM, UNP] · exited [MTB, PNC, USB]
**Movers:** ↑ LMT +39.2, URI +38.5, ROP +28.9, RTX +23.4, LHX +22.6  ↓ XLP -23.3, SPY -18.9, TGT -18.7, DG -17.6, XLY -16.8

### 2. Predictions that came due today

**Live predictions**

- **2026-07-16 · v0.3_sector_neutral → 5d** (n=517): Strong n/a (n=1) vs Weak 56.2% (n=233)

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | n/a (n=19) | 56.2% (n=2252) | 49.6% (n=3652) | 50.0% (n=84437) |
| 20d | n/a (n=0) | n/a (n=0) | 48.4% (n=10118) | 47.9% (n=77717) |
| 60d | n/a (n=0) | n/a (n=0) | 51.6% (n=16101) | 44.9% (n=62833) |
| 120d | n/a (n=0) | n/a (n=0) | 53.4% (n=17910) | 41.4% (n=47340) |

_Backfill baseline: v0.1_price_volume_only (504 sessions, 2024-06-24 → 2026-06-26)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 14 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.099 (n=4056)
  - quality_component: 5d -0.024 (n=4048)
  - short_interest_component: 5d -0.024 (n=4016)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (13 component-horizon(s) in range)

---

## 2026-07-22 — v0.3_sector_neutral (live)

_Run: scored 520 tickers in 1094.4s · fetch fresh=520 / cached=0 / failed=0_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | EIX | Utilities | 85.1 | strong | — |
| 2 | TRV | Financials | 82.4 | strong | 85d |
| 3 | ALL | Financials | 82.4 | strong | — |
| 4 | USB | Financials | 81.0 | strong | 85d |
| 5 | PM | Consumer Staples | 79.8 | decent | — |
| 6 | BAC | Financials | 79.3 | decent | 84d |
| 7 | BNY | Financials | 78.6 | decent | 85d |
| 8 | GD | Industrials | 78.3 | decent | 7d |
| 9 | MTB | Financials | 78.2 | decent | 86d |
| 10 | PNC | Financials | 77.1 | decent | 85d |

**vs prev live run (2026-07-21):** entered [PM, PNC] · exited [FRT, MO]
**Movers:** ↑ WAB +27.8, NRG +18.6, DE +17.9, ETN +17.7, SRE +17.0  ↓ CDNS -16.7, NOW -15.3, FFIV -14.2, BRO -14.1, UHS -13.8

### 2. Predictions that came due today

**Live predictions**

- **2026-07-15 · v0.3_sector_neutral → 5d** (n=517): Strong n/a (n=1) vs Weak 53.6% (n=263)

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | n/a (n=18) | 56.2% (n=2019) | 49.6% (n=3652) | 50.0% (n=84437) |
| 20d | n/a (n=0) | n/a (n=0) | 48.4% (n=10083) | 47.9% (n=77479) |
| 60d | n/a (n=0) | n/a (n=0) | 51.6% (n=16034) | 44.9% (n=62583) |
| 120d | n/a (n=0) | n/a (n=0) | 53.3% (n=17811) | 41.4% (n=47134) |

_Backfill baseline: v0.1_price_volume_only (504 sessions, 2024-06-24 → 2026-06-26)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 12 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.111 (n=3042)
  - quality_component: 5d -0.013 (n=3036)
  - short_interest_component: 5d -0.055 (n=3012)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (13 component-horizon(s) in range)

---

## 2026-07-21 — v0.3_sector_neutral (live)

_Run: scored 520 tickers in 1147.4s · fetch fresh=520 / cached=0 / failed=0_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | ALL | Financials | 83.2 | strong | — |
| 2 | TRV | Financials | 81.7 | strong | 86d |
| 3 | EIX | Utilities | 80.8 | strong | — |
| 4 | USB | Financials | 79.2 | decent | 86d |
| 5 | BAC | Financials | 78.0 | decent | — |
| 6 | MO | Consumer Staples | 77.6 | decent | — |
| 7 | BNY | Financials | 76.8 | decent | 86d |
| 8 | MTB | Financials | 76.7 | decent | 87d |
| 9 | FRT | Real Estate | 76.6 | decent | 10d |
| 10 | GD | Industrials | 76.6 | decent | 8d |

**vs prev live run (2026-07-20):** entered [BAC, BNY, FRT, GD] · exited [ACGL, EG, GL, PM]
**Movers:** ↑ SPY +26.2, HAS +18.7, GM +18.5, COIN +16.3, A +14.3  ↓ MSCI -42.1, DHR -38.6, OTIS -25.4, HAL -23.3, TXN -19.4

### 2. Predictions that came due today

**Live predictions**

_None matured today._

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | n/a (n=17) | 56.5% (n=1756) | 49.6% (n=3652) | 50.0% (n=84437) |
| 20d | n/a (n=0) | n/a (n=0) | 48.4% (n=10050) | 47.9% (n=77237) |
| 60d | n/a (n=0) | n/a (n=0) | 51.6% (n=15966) | 44.9% (n=62340) |
| 120d | n/a (n=0) | n/a (n=0) | 53.3% (n=17720) | 41.5% (n=46920) |

_Backfill baseline: v0.1_price_volume_only (504 sessions, 2024-06-24 → 2026-06-26)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 12 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.111 (n=3042)
  - quality_component: 5d -0.013 (n=3036)
  - short_interest_component: 5d -0.055 (n=3012)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (13 component-horizon(s) in range)

---

## 2026-07-20 — v0.3_sector_neutral (recovered)

_Run: scored 520 tickers in unknown time · fetch fresh=0 / cached=0 / failed=0_
_Fundamentals: recovered — fundamentals stamped 2026-07-21 (not point-in-time)_
_Warnings: recovered missed day; fundamentals as of 2026-07-21, excluded from factor IC_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | ALL | Financials | 84.7 | strong | — |
| 2 | MO | Consumer Staples | 82.5 | strong | — |
| 3 | TRV | Financials | 82.1 | strong | — |
| 4 | EIX | Utilities | 80.4 | strong | — |
| 5 | GL | Financials | 80.4 | strong | — |
| 6 | USB | Financials | 79.0 | decent | — |
| 7 | PM | Consumer Staples | 78.4 | decent | — |
| 8 | EG | Financials | 77.8 | decent | — |
| 9 | MTB | Financials | 77.8 | decent | — |
| 10 | ACGL | Financials | 77.2 | decent | — |

**vs prev live run (2026-07-17):** entered [ACGL, GL, MTB, PM] · exited [BAC, ES, INCY, SPG]
**Movers:** ↑ NOC +23.3, CHTR +18.8, RTX +18.5, EFX +18.4, KMI +17.7  ↓ SPY -17.3, WBD -16.7, CVNA -16.6, ROK -12.8, SRE -11.8

### 2. Predictions that came due today

**Live predictions**

- **2026-07-13 · v0.3_sector_neutral → 5d** (n=517): Strong n/a (n=1) vs Weak 52.8% (n=269)

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | n/a (n=17) | 56.5% (n=1756) | 49.6% (n=3652) | 50.0% (n=84437) |
| 20d | n/a (n=0) | n/a (n=0) | 48.4% (n=10023) | 47.8% (n=76980) |
| 60d | n/a (n=0) | n/a (n=0) | 51.6% (n=15901) | 44.9% (n=62089) |
| 120d | n/a (n=0) | n/a (n=0) | 53.3% (n=17621) | 41.5% (n=46719) |

_Backfill baseline: v0.1_price_volume_only (504 sessions, 2024-06-24 → 2026-06-26)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 12 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.111 (n=3042)
  - quality_component: 5d -0.013 (n=3036)
  - short_interest_component: 5d -0.055 (n=3012)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (13 component-horizon(s) in range)

---

## 2026-07-17 — v0.3_sector_neutral (live)

_Run: scored 520 tickers in 1716.1s · fetch fresh=519 / cached=1 / failed=0_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | ALL | Financials | 82.9 | strong | — |
| 2 | TRV | Financials | 82.4 | strong | 88d |
| 3 | MO | Consumer Staples | 81.8 | strong | 11d |
| 4 | EIX | Utilities | 81.0 | strong | 11d |
| 5 | USB | Financials | 79.4 | decent | 88d |
| 6 | BAC | Financials | 79.2 | decent | 87d |
| 7 | EG | Financials | 78.2 | decent | 10d |
| 8 | INCY | Health Care | 77.3 | decent | 9d |
| 9 | SPG | Real Estate | 77.0 | decent | 22d |
| 10 | ES | Utilities | 76.9 | decent | 11d |

**vs prev live run (2026-07-16):** entered [EG, INCY, SPG, TRV, USB] · exited [BNY, CSX, GL, MTB, UNP]
**Movers:** ↑ TRV +18.0, ABT +14.7, UNH +14.4, PLD +14.1, GE +13.5  ↓ TSCO -23.2, NVR -20.7, VZ -20.4, HOOD -18.9, EW -18.1

### 2. Predictions that came due today

**Live predictions**

- **2026-07-10 · v0.3_sector_neutral → 5d** (n=517): Strong n/a (n=0) vs Weak 55.6% (n=275)

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | n/a (n=16) | 57.2% (n=1487) | 49.6% (n=3652) | 50.0% (n=84437) |
| 20d | n/a (n=0) | n/a (n=0) | 48.4% (n=10006) | 47.7% (n=76718) |
| 60d | n/a (n=0) | n/a (n=0) | 51.6% (n=15842) | 45.0% (n=61835) |
| 120d | n/a (n=0) | n/a (n=0) | 53.3% (n=17520) | 41.5% (n=46525) |

_Backfill baseline: v0.1_price_volume_only (504 sessions, 2024-06-24 → 2026-06-26)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 12 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.111 (n=3042)
  - quality_component: 5d -0.013 (n=3036)
  - short_interest_component: 5d -0.055 (n=3012)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (13 component-horizon(s) in range)

---

## 2026-07-16 — v0.3_sector_neutral (live)

_Run: scored 520 tickers in 1122.2s · fetch fresh=520 / cached=0 / failed=0_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | EIX | Utilities | 83.0 | strong | 14d |
| 2 | GL | Financials | 81.1 | strong | 6d |
| 3 | ALL | Financials | 79.5 | decent | — |
| 4 | BNY | Financials | 79.1 | decent | 91d |
| 5 | MO | Consumer Staples | 78.9 | decent | 14d |
| 6 | ES | Utilities | 78.7 | decent | 14d |
| 7 | BAC | Financials | 78.1 | decent | 90d |
| 8 | MTB | Financials | 78.0 | decent | 92d |
| 9 | CSX | Industrials | 77.5 | decent | 6d |
| 10 | UNP | Industrials | 77.2 | decent | 7d |

**vs prev live run (2026-07-15):** entered [BNY, CSX, MO, MTB, UNP] · exited [AAPL, INCY, JPM, NTRS, TROW]
**Movers:** ↑ JBHT +29.2, XLP +25.6, BIIB +18.8, PPL +18.4, TSCO +17.9  ↓ IBKR -27.7, CI -21.6, VST -20.5, GOOG -20.2, ETN -19.6

### 2. Predictions that came due today

**Live predictions**

- **2026-07-09 · v0.3_sector_neutral → 5d** (n=517): Strong n/a (n=2) vs Weak 57.8% (n=263)

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | n/a (n=16) | 57.6% (n=1212) | 49.6% (n=3652) | 50.0% (n=84437) |
| 20d | n/a (n=0) | n/a (n=0) | 48.4% (n=9989) | 47.7% (n=76453) |
| 60d | n/a (n=0) | n/a (n=0) | 51.5% (n=15784) | 45.0% (n=61580) |
| 120d | n/a (n=0) | n/a (n=0) | 53.3% (n=17420) | 41.5% (n=46327) |

_Backfill baseline: v0.1_price_volume_only (504 sessions, 2024-06-24 → 2026-06-26)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 12 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.111 (n=3042)
  - quality_component: 5d -0.013 (n=3036)
  - short_interest_component: 5d -0.055 (n=3012)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (13 component-horizon(s) in range)

---

## 2026-07-15 — v0.3_sector_neutral (live)

_Run: scored 520 tickers in 1022.2s · fetch fresh=520 / cached=0 / failed=0_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | BAC | Financials | 80.6 | strong | 91d |
| 2 | GL | Financials | 80.4 | strong | 7d |
| 3 | EIX | Utilities | 80.1 | strong | 15d |
| 4 | JPM | Financials | 78.2 | decent | 90d |
| 5 | TROW | Financials | 77.4 | decent | 16d |
| 6 | NTRS | Financials | 76.8 | decent | 7d |
| 7 | INCY | Health Care | 76.7 | decent | 13d |
| 8 | ES | Utilities | 76.3 | decent | 15d |
| 9 | AAPL | Information Technology | 75.9 | decent | 15d |
| 10 | ALL | Financials | 75.8 | decent | — |

**vs prev live run (2026-07-14):** entered [AAPL, INCY, NTRS, TROW] · exited [ACGL, BNY, STT, TRV]
**Movers:** ↑ CBRE +18.1, MMM +18.0, PM +17.7, FISV +15.4, XLC +15.0  ↓ PGR -43.3, ELV -36.9, WRB -23.3, ERIE -20.9, JNJ -19.4

### 2. Predictions that came due today

**Live predictions**

- **2026-07-08 · v0.3_sector_neutral → 5d** (n=517): Strong n/a (n=2) vs Weak 56.4% (n=250)

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | n/a (n=14) | 57.5% (n=949) | 49.6% (n=3652) | 50.0% (n=84437) |
| 20d | n/a (n=0) | n/a (n=0) | 48.4% (n=9960) | 47.7% (n=76239) |
| 60d | n/a (n=0) | n/a (n=0) | 51.5% (n=15727) | 45.0% (n=61335) |
| 120d | n/a (n=0) | n/a (n=0) | 53.2% (n=17308) | 41.6% (n=46134) |

_Backfill baseline: v0.1_price_volume_only (504 sessions, 2024-06-24 → 2026-06-26)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 12 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.111 (n=3042)
  - quality_component: 5d -0.013 (n=3036)
  - short_interest_component: 5d -0.055 (n=3012)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (13 component-horizon(s) in range)

---

## 2026-07-14 — v0.3_sector_neutral (recovered)

_Run: scored 520 tickers in unknown time · fetch fresh=0 / cached=0 / failed=0_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | ALL | Financials | 84.9 | strong | — |
| 2 | GL | Financials | 79.5 | decent | — |
| 3 | BAC | Financials | 78.9 | decent | — |
| 4 | STT | Financials | 78.8 | decent | — |
| 5 | EIX | Utilities | 78.6 | decent | — |
| 6 | TRV | Financials | 78.1 | decent | — |
| 7 | ES | Utilities | 78.1 | decent | — |
| 8 | ACGL | Financials | 77.7 | decent | — |
| 9 | JPM | Financials | 76.7 | decent | — |
| 10 | BNY | Financials | 76.6 | decent | — |

**vs prev live run (2026-07-13):** entered [BAC, BNY, JPM, STT, TRV] · exited [AIZ, AVB, CB, EG, MO]
**Movers:** ↑ CVNA +26.4, GS +26.3, CTAS +21.9, MS +18.9, ETN +17.2  ↓ IBM -35.1, BIIB -20.5, SYK -17.1, MO -16.6, CBRE -16.6

### 2. Predictions that came due today

**Live predictions**

- **2026-07-07 · v0.3_sector_neutral → 5d** (n=517): Strong n/a (n=2) vs Weak 58.3% (n=228)

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | n/a (n=12) | 57.9% (n=699) | 49.6% (n=3652) | 50.0% (n=84437) |
| 20d | n/a (n=0) | n/a (n=0) | 48.5% (n=9933) | 47.7% (n=76015) |
| 60d | n/a (n=0) | n/a (n=0) | 51.5% (n=15675) | 45.0% (n=61090) |
| 120d | n/a (n=0) | n/a (n=0) | 53.2% (n=17208) | 41.6% (n=45937) |

_Backfill baseline: v0.1_price_volume_only (504 sessions, 2024-06-24 → 2026-06-26)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 12 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.111 (n=3042)
  - quality_component: 5d -0.013 (n=3036)
  - short_interest_component: 5d -0.055 (n=3012)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (13 component-horizon(s) in range)

---

## 2026-07-13 — v0.3_sector_neutral (live)

_Run: scored 520 tickers in 1997.9s · fetch fresh=520 / cached=0 / failed=0_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | ALL | Financials | 86.2 | strong | — |
| 2 | GL | Financials | 78.9 | decent | 9d |
| 3 | ACGL | Financials | 78.7 | decent | 15d |
| 4 | EG | Financials | 78.3 | decent | 16d |
| 5 | ES | Utilities | 78.0 | decent | 17d |
| 6 | EIX | Utilities | 76.6 | decent | 17d |
| 7 | MO | Consumer Staples | 76.3 | decent | 17d |
| 8 | AVB | Real Estate | 76.3 | decent | 9d |
| 9 | AIZ | Financials | 76.0 | decent | 22d |
| 10 | CB | Financials | 75.9 | decent | 8d |

**vs prev live run (2026-07-10):** entered [AIZ, AVB, CB, EIX, MO] · exited [BNY, FFIV, GD, TROW, TRV]
**Movers:** ↑ XLE +22.2, FDS +18.3, EOG +14.9, FANG +11.0, CI +10.5  ↓ QQQ -27.8, SMH -27.4, SNDK -24.6, APP -21.6, RL -21.2

### 2. Predictions that came due today

**Live predictions**

_None matured today._

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | n/a (n=10) | 57.7% (n=471) | 49.6% (n=3652) | 50.0% (n=84437) |
| 20d | n/a (n=0) | n/a (n=0) | 48.5% (n=9898) | 47.7% (n=75778) |
| 60d | n/a (n=0) | n/a (n=0) | 51.5% (n=15627) | 45.0% (n=60831) |
| 120d | n/a (n=0) | n/a (n=0) | 53.2% (n=17123) | 41.6% (n=45727) |

_Backfill baseline: v0.1_price_volume_only (504 sessions, 2024-06-24 → 2026-06-26)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 12 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.111 (n=3042)
  - quality_component: 5d -0.013 (n=3036)
  - short_interest_component: 5d -0.055 (n=3012)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (13 component-horizon(s) in range)

---

## 2026-07-10 — v0.3_sector_neutral (live)

_Run: scored 520 tickers in 1273.8s · fetch fresh=520 / cached=0 / failed=0_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | ALL | Financials | 85.0 | strong | — |
| 2 | GL | Financials | 81.2 | strong | 11d |
| 3 | TRV | Financials | 79.9 | decent | 6d |
| 4 | TROW | Financials | 79.3 | decent | 20d |
| 5 | ES | Utilities | 78.4 | decent | 19d |
| 6 | FFIV | Information Technology | 77.8 | decent | 16d |
| 7 | ACGL | Financials | 77.3 | decent | 17d |
| 8 | GD | Industrials | 77.3 | decent | 18d |
| 9 | EG | Financials | 77.2 | decent | 18d |
| 10 | BNY | Financials | 76.1 | decent | — |

**vs prev live run (2026-07-09):** entered [BNY, ES, FFIV, GD] · exited [AIZ, INCY, STT, USB]
**Movers:** ↑ PNR +18.6, NKE +17.7, DHI +15.6, PEP +13.6, CLX +13.3  ↓ KMI -20.2, PLD -16.9, UAL -16.7, ISRG -16.1, GE -15.9

### 2. Predictions that came due today

**Live predictions**

- **2026-07-02 · v0.2_fundamentals_added → 5d** (n=517): Strong n/a (n=6) vs Weak 54.8% (n=230)

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | n/a (n=10) | 57.7% (n=471) | 49.7% (n=3627) | 50.0% (n=84213) |
| 20d | n/a (n=0) | n/a (n=0) | 48.5% (n=9864) | 47.7% (n=75528) |
| 60d | n/a (n=0) | n/a (n=0) | 51.4% (n=15588) | 44.9% (n=60564) |
| 120d | n/a (n=0) | n/a (n=0) | 53.1% (n=17017) | 41.6% (n=45533) |

_Backfill baseline: v0.1_price_volume_only (504 sessions, 2024-06-24 → 2026-06-26)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 12 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.111 (n=3042)
  - quality_component: 5d -0.013 (n=3036)
  - short_interest_component: 5d -0.055 (n=3012)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (13 component-horizon(s) in range)

---

## 2026-07-09 — v0.3_sector_neutral (live)

_Run: scored 520 tickers in 1173.9s · fetch fresh=520 / cached=0 / failed=0_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | ALL | Financials | 85.2 | strong | — |
| 2 | GL | Financials | 82.6 | strong | 13d |
| 3 | TRV | Financials | 80.2 | strong | 8d |
| 4 | TROW | Financials | 79.4 | decent | 22d |
| 5 | EG | Financials | 79.3 | decent | 20d |
| 6 | USB | Financials | 79.1 | decent | 7d |
| 7 | ACGL | Financials | 78.8 | decent | 19d |
| 8 | INCY | Health Care | 78.2 | decent | 19d |
| 9 | AIZ | Financials | 78.1 | decent | 26d |
| 10 | STT | Financials | 78.0 | decent | 7d |

**vs prev live run (2026-07-08):** entered [AIZ, STT, USB] · exited [CINF, GD, PM]
**Movers:** ↑ QQQ +26.4, GLW +20.8, CIEN +19.1, IVZ +17.9, HPE +17.7  ↓ XLP -25.4, SJM -15.5, LMT -13.6, PEP -13.5, FAST -13.2

### 2. Predictions that came due today

**Live predictions**

- **2026-07-01 · v0.2_fundamentals_added → 5d** (n=517): Strong n/a (n=4) vs Weak 60.6% (n=241)

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | n/a (n=4) | 60.6% (n=241) | 49.7% (n=3627) | 50.0% (n=84213) |
| 20d | n/a (n=0) | n/a (n=0) | 48.4% (n=9840) | 47.7% (n=75258) |
| 60d | n/a (n=0) | n/a (n=0) | 51.4% (n=15546) | 44.9% (n=60306) |
| 120d | n/a (n=0) | n/a (n=0) | 53.1% (n=16904) | 41.6% (n=45339) |

_Backfill baseline: v0.1_price_volume_only (504 sessions, 2024-06-24 → 2026-06-26)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 12 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.111 (n=3042)
  - quality_component: 5d -0.013 (n=3036)
  - short_interest_component: 5d -0.055 (n=3012)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (13 component-horizon(s) in range)

---

## 2026-07-08 — v0.3_sector_neutral (live)

_Run: scored 520 tickers in 1089.4s · fetch fresh=520 / cached=0 / failed=0_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | ALL | Financials | 86.5 | strong | — |
| 2 | GL | Financials | 82.0 | strong | 14d |
| 3 | TRV | Financials | 80.9 | strong | 9d |
| 4 | TROW | Financials | 80.1 | strong | 23d |
| 5 | ACGL | Financials | 79.5 | decent | 20d |
| 6 | CINF | Financials | 79.4 | decent | 19d |
| 7 | EG | Financials | 79.3 | decent | 21d |
| 8 | PM | Consumer Staples | 78.0 | decent | 14d |
| 9 | INCY | Health Care | 78.0 | decent | 20d |
| 10 | GD | Industrials | 77.9 | decent | 21d |

**vs prev live run (2026-07-07):** entered [GD, INCY, PM] · exited [SPG, USB, VRTX]
**Movers:** ↑ CASY +16.2, TGT +13.9, TXN +13.1, AKAM +12.9, VRT +11.0  ↓ SYF -25.8, XLY -24.5, XLB -18.3, TPR -16.9, TXT -16.5

### 2. Predictions that came due today

**Live predictions**

_None matured today._

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | n/a (n=0) | n/a (n=0) | 49.7% (n=3627) | 50.0% (n=84213) |
| 20d | n/a (n=0) | n/a (n=0) | 48.5% (n=9809) | 47.7% (n=75003) |
| 60d | n/a (n=0) | n/a (n=0) | 51.4% (n=15512) | 44.9% (n=60044) |
| 120d | n/a (n=0) | n/a (n=0) | 53.1% (n=16799) | 41.6% (n=45136) |

_Backfill baseline: v0.1_price_volume_only (504 sessions, 2024-06-24 → 2026-06-26)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 12 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.111 (n=3042)
  - quality_component: 5d -0.013 (n=3036)
  - short_interest_component: 5d -0.055 (n=3012)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (13 component-horizon(s) in range)

---

## 2026-07-07 — v0.3_sector_neutral (live)

_Run: scored 520 tickers in 212.5s · fetch fresh=0 / cached=520 / failed=0_

### 1. Today's Rankings

_Research ranking, NOT a buy recommendation._

| # | Ticker | Sector | score_20d | Label | Earnings in |
|---|--------|--------|-----------|-------|-------------|
| 1 | ALL | Financials | 84.9 | strong | — |
| 2 | CINF | Financials | 81.6 | strong | 19d |
| 3 | TROW | Financials | 80.3 | strong | 23d |
| 4 | TRV | Financials | 80.1 | strong | 9d |
| 5 | USB | Financials | 79.8 | decent | 8d |
| 6 | GL | Financials | 79.7 | decent | 14d |
| 7 | SPG | Real Estate | 78.2 | decent | 33d |
| 8 | VRTX | Health Care | 77.5 | decent | 26d |
| 9 | ACGL | Financials | 77.5 | decent | 20d |
| 10 | EG | Financials | 77.5 | decent | 21d |

**vs prev live run:** none yet (first live run for this version)

### 2. Predictions that came due today

**Live predictions**

_None matured today._

### 3. Running scoreboard — cumulative Strong vs Weak hit rate

| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |
|---------|-------------|-----------|-----------------|---------------|
| 5d | n/a (n=0) | n/a (n=0) | 49.7% (n=3627) | 50.0% (n=84213) |
| 20d | n/a (n=0) | n/a (n=0) | 48.5% (n=9786) | 47.7% (n=74727) |
| 60d | n/a (n=0) | n/a (n=0) | 51.4% (n=15475) | 44.9% (n=59779) |
| 120d | n/a (n=0) | n/a (n=0) | 53.1% (n=16693) | 41.6% (n=44920) |

_Backfill baseline: v0.1_price_volume_only (504 sessions, 2024-06-24 → 2026-06-26)._
_Backfill is survivorship-flattered: today's S&P constituents, delisted names absent — read the backfill columns as optimistic._

### 4. Live validation tracker

**4a. Fundamental-factor IC** — do value/quality earn their weight?

_Live only — 12 live trading day(s) since 2026-07-07. The genuine out-of-sample read, and the one 4a exists for._
  - value_component: too early (no live IC yet)
  - quality_component: too early (no live IC yet)
  - short_interest_component: too early (no live IC yet)

_Full panel — includes backfilled rows. Large sample, but the weights were chosen on this data, so treat it as in-sample and flattering._
  - value_component: 5d +0.111 (n=3042)
  - quality_component: 5d -0.013 (n=3036)
  - short_interest_component: 5d -0.055 (n=3012)

**4b. Drift on established components** (recent-window IC vs full history)
  - no material drift (13 component-horizon(s) in range)

---

## 2026-07-02 — v0.2_fundamentals_added (live)

**Run:** scored 520 tickers in 1062.3s · fetch fresh=520 / cached=0 / failed=0

**Top 10 (score_20d):** ALL 87.5, GL 85.6, CINF 85.3, TRV 82.6, USB 82.2, TROW 81.4, BAC 80.5, PNC 80.4, XLV 80.2, CFG 80.0
**vs prev live run (2026-07-01):** entered [XLV] · exited [KEY]
**Movers:** ↑ BA +23.0, LMT +21.1, NWS +19.8, NKE +16.6, FDS +16.3  ↓ CRWD -40.6, TER -27.1, TSLA -23.9, JBL -23.4, SNDK -21.4

**Evaluation state:** no evaluable snapshots for this version yet.

**v0.2 live-validation:** 2 live trading day(s) accrued.
  - value/quality/short-interest IC: pending (needs forward returns to elapse on live data).

---

## 2026-07-01 — v0.2_fundamentals_added (live)

**Run:** scored 517 tickers in unknown time · fetch fresh=0 / cached=0 / failed=0
**Fundamentals:** live run

**Top 10 (score_20d):** GL 87.2, ALL 86.8, CINF 84.7, USB 83.3, TRV 82.6, PNC 82.5, CFG 82.4, BAC 81.7, TROW 81.3, KEY 80.8
**vs prev live run:** none yet (first live run for this version)

**Evaluation state:** no evaluable snapshots for this version yet.

**v0.2 live-validation:** 1 live trading day(s) accrued.
  - value/quality/short-interest IC: pending (needs forward returns to elapse on live data).

---

