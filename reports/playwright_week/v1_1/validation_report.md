# FIM Engine v1.1 — Technical Validation Report

**Release Version:** FIM Engine v1.1.0  
**Audit Date:** November 15, 2026  
**Dataset Target:** Microsoft Playwright CI Parquet Dataset (August 1–7, 2024)  
**Total Records Analyzed:** 2,056,823  
**Unique Test Cases:** 4,042 across 43 target environments and 93 pipelines  
**Report Artifacts Location:** `reports/playwright_week/v1_1/`

---

## 1. Executive Summary

FIM Engine Version 1.1 implements four methodological corrections identified during the validation audit against prior independent Microsoft Playwright research. 

All corrections were achieved non-destructively:
- **Zero changes** to existing application databases (`fim.db`, `comparison_fim.db`, `real_flaky.db`), backend code, or frontend templates.
- **Zero modifications** to the original v1.0 outputs in `reports/playwright_week/`.
- All 14 engine unit tests and all 20 existing regression tests pass with zero failures.

---

## 2. Implemented Corrections

### Correction 1: Candidate Sub-Categorization
The single `Flaky candidate` label has been split into two empirically distinct categories:
1. **`Flaky candidate (In-batch retry verified)` (36 candidates):**
   Tests exhibiting within-job fail-to-pass retry evidence on identical commits, runners, and environments. This isolates non-determinism from code regressions.
2. **`Intermittent candidate (Cross-pipeline observational)` (43 candidates):**
   Tests exhibiting pass/fail outcome variation across pipelines but with **zero verified in-batch retry recoveries**. These are explicitly designated as observational candidates requiring commit-level diff analysis rather than confirmed flakiness.

*Consistently failing (1 test)*, *consistently passing (3,962 tests)*, and *insufficient evidence (0 tests)* classifications remain strictly separated.

---

### Correction 2: Dual Retry Recovery Reporting (Macro vs. Micro Average)
To resolve the discrepancy between per-test averages and aggregate CI throughput efficiency, both metrics are now computed and labeled:
- **Pre-Exclusion Pooled Micro-Average:** **88.82%** ($294 / 331$), matching the expected result from prior research to the hundredth of a percent.
- **Post-Exclusion Pooled Micro-Average:** **88.72%** ($291 / 328$), reflecting the exclusion of 3 duplicate-index sequence anomaly recoveries.
- **Macro-Average Recovery Rate:** **66.18%** (the unweighted arithmetic mean across candidates).
Both metrics are clearly exported in `ranked_candidates.csv`, `ranked_candidates.json`, and `analysis_summary.json`.

---

### Correction 3: Evidence-Aware Stratified Ranking
To eliminate the small-sample rank distortion where candidate #2 (`should show canvas content`, 12 runs, score 0.3000) outranked systemic flaky tests, an **Evidence-Stratified Ranking Architecture** was introduced:
$$\text{Rank Order: } \text{Active Candidates} \to \text{In-Batch Verified First} \to \text{High Evidence} \to \text{Moderate Evidence} \to \text{Low Evidence} \to \text{Priority Score}$$

- The original exploratory baseline formula is fully preserved:
  $$\text{Priority} = 0.60 \times \text{Pipeline Recurrence} + 0.40 \times \text{Mixed Batch Frequency}$$
- Candidate `should show canvas content` is properly placed in the **Low evidence tier**, preventing it from outranking high-confidence candidates.
- Execution count (`total_executions`) and distinct pipeline count (`total_pipelines`) are now included in all ranked exports.

---

### Correction 4: Retry Sequence Anomaly Validation
Batches are evaluated for duplicate retry indices within the same `(pipeline_id, job_id, test_case_environment)` tuple:
- Any batch with `len(retries) != len(set(retries))` is flagged as `SEQUENCE_ANOMALY`.
- Recoveries from anomalous batches are excluded from verified fail-to-pass counts until resolved.
- **Pipeline 10189692513 Findings:**
  - Three batches with `0 -> 0 -> 1 -> 1` were detected:
    1. `tests/page/page-event-popup.spec.ts/should work with clicking target=_blank and rel=noopener`
    2. `tests/playwright-test/ui-mode-test-screencast.spec.ts/should show screenshots`
    3. `tests/playwright-test/ui-mode-test-setup.spec.ts/should show errors in config`
  - Exactly **3 recoveries were excluded**.
  - `page-event-popup` had only 1 recovery across the week; with that anomaly excluded, it was properly classified as `Intermittent candidate (Cross-pipeline observational)`.
  - `ui-mode-test-screencast` and `ui-mode-test-setup` retain 31 and 34 verified recoveries respectively, remaining in `Flaky candidate (In-batch retry verified)` with their excluded anomaly explicitly noted.

---

## 3. Comparison: Version 1.0 vs. Version 1.1

| Metric / Dimension | Version 1.0 | Version 1.1 (Correction Release) | Impact / Rationale |
| :--- | :---: | :---: | :--- |
| **Flaky Classification** | 1 generic label (79) | 2 sub-categories: 36 Verified In-Batch, 43 Cross-Pipeline | Separates high-confidence flakiness from unretried observational variation |
| **Ranking Order** | Linear Score Descending | Evidence-Stratified (High $\to$ Mod $\to$ Low) | Eliminates low-sample rank distortion |
| **Top Rank #2** | `should show canvas content` (12 runs, Low) | `ui-mode-test-watch.spec.ts/should watch all` (514 runs, High) | Systemic flaky test restored to top tier |
| **Macro Recovery Rate** | 66.80% | 66.18% | Preserved as unweighted per-test average |
| **Pooled Micro Recovery** | *Not reported* | **88.72%** (post) / **88.82%** (pre) | Correct CI-level throughput efficiency reported |
| **Sequence Anomaly Accounting** | Silent Ingestion | 3 recoveries excluded, batches flagged | Pipeline 10189692513 duplicates prevented from corrupting verified metrics |
| **Verified Recoveries** | 294 | 291 verified (+3 excluded anomalies) | Exact alignment with 291 validated sequences in prior research |
| **Export Fields** | 18 columns in CSV | 21 columns (added pipelines, anomalies, excluded counts) | Full transparency into sample size and data quality |

---

## 4. Top 10 Ranked Candidates in Version 1.1

| Rank | Priority Score | Recurrence (60%) | Batch Freq (40%) | Execs | Pipes | Evidence Level | Sub-Classification | Test Case Name |
| :---: | :---: | :---: | :---: | :---: | :---: | :--- | :--- | :--- |
| **1** | **0.3413** | 0.5054 | 0.0952 | 615 | 93 | High | In-Batch Retry Verified | `tests/library/browsercontext-fetch-happy-eyeballs.spec.ts/get should work` |
| **2** | **0.2935** | 0.4239 | 0.0978 | 514 | 92 | High | In-Batch Retry Verified | `tests/playwright-test/ui-mode-test-watch.spec.ts/should watch all` |
| **3** | **0.2774** | 0.4130 | 0.0739 | 522 | 92 | High | In-Batch Retry Verified | `tests/playwright-test/ui-mode-test-setup.spec.ts/should show errors in config` |
| **4** | **0.2096** | 0.3043 | 0.0674 | 499 | 92 | High | In-Batch Retry Verified | `tests/playwright-test/ui-mode-test-screencast.spec.ts/should show screenshots` |
| **5** | **0.1786** | 0.2688 | 0.0432 | 593 | 93 | High | In-Batch Retry Verified | `tests/page/page-goto.spec.ts/should properly cancel Cross-Origin-Opener-Policy navigation` |
| **6** | **0.0951** | 0.1398 | 0.0280 | 481 | 93 | High | In-Batch Retry Verified | `tests/page/workers.spec.ts/should support offline` |
| **7** | **0.0766** | 0.1127 | 0.0225 | 363 | 71 | High | In-Batch Retry Verified | `tests/playwright-test/ui-mode-test-attachments.spec.ts/should linkify string attachments` |
| **8** | **0.0591** | 0.0870 | 0.0174 | 473 | 92 | High | In-Batch Retry Verified | `tests/playwright-test/ui-mode-test-progress.spec.ts/should update tracing network live` |
| **9** | **0.0574** | 0.0860 | 0.0144 | 570 | 93 | High | In-Batch Retry Verified | `tests/page/frame-goto.spec.ts/should continue after client redirect` |
| **10** | **0.0517** | 0.0761 | 0.0152 | 472 | 92 | High | In-Batch Retry Verified | `tests/playwright-test/ui-mode-test-progress.spec.ts/should update trace live` |

---

## 5. Verification & System Health

1. **Test Suites:**
   - `tests/test_fim_engine.py`: **14 passed** in 0.78s (includes dedicated tests for sub-categorization, duplicate retry sequence anomalies, evidence-stratified ranking, and dual recovery reporting).
   - `tests/test_metrics.py`: **12 passed** in 0.04s.
   - `tests/test_real_dataset.py`: **8 passed** in 0.03s.
   - Total test suite: **34 passed, 0 failures**.
2. **Database Integrity Verification (SHA-256):**
   - `data/fim.db`: `431064FB44D3162AF009111EDF9CDB32FEF66259966C2AB9B7D982B947D8E181` (Unmodified)
   - `data/comparison_fim.db`: `6984D3FCC6D9546EA0C6CF8E40E658DF345D57F08E53618C04F9BD44C80033F0` (Unmodified)
   - `data/real_flaky.db`: `3315EECF83D76024A9B14B11BE5B52E6E6A7F6DC9070206F1A0E673FDC3F8F28` (Unmodified)
3. **Artifact Integrity:**
   - v1.0 original reports preserved in `reports/playwright_week/`.
   - v1.1 reports delivered in `reports/playwright_week/v1_1/`.

