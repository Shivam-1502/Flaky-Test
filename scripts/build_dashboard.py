"""
FIM - Dashboard Builder Script
Extracts all baseline and comparative metrics, formats them into a high-density,
professional engineering analytics dashboard (inspired by Linear, Grafana, GitHub Actions),
and outputs both app/templates/dashboard.html and the conversation artifact.
"""

import json
import os
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.metrics import (
    suite_metrics, pipeline_metrics, systemic_metrics,
    environment_metrics, all_test_metrics
)

DATA_DIR = PROJECT_ROOT / "data"
FIM_DB_PATH = DATA_DIR / "fim.db"
COMPARISON_JSON_PATH = DATA_DIR / "comparison_results.json"
TEMPLATES_DIR = PROJECT_ROOT / "app" / "templates"
TEMPLATES_DIR.mkdir(exist_ok=True, parents=True)
DASHBOARD_HTML_PATH = TEMPLATES_DIR / "dashboard.html"

ARTIFACT_DIR = Path(r"C:\Users\LAKSHAY CHAUDHARY\.gemini\antigravity\brain\0f158b9d-7c93-4f9f-a9c8-46c63df3bfa5")
ARTIFACT_HTML_PATH = ARTIFACT_DIR / "fim_analytics_platform.html"

def load_data():
    # 1. Baseline metrics
    b_suite = suite_metrics()
    b_pipe = pipeline_metrics()
    b_sys = systemic_metrics()
    b_env = environment_metrics()
    b_tests = all_test_metrics()

    # 2. Pipeline runs and test executions from baseline DB
    con = sqlite3.connect(FIM_DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    pipelines_raw = [dict(r) for r in cur.execute("SELECT * FROM pipelines ORDER BY rowid").fetchall()]
    executions_raw = [dict(r) for r in cur.execute("SELECT * FROM test_executions ORDER BY id").fetchall()]
    con.close()

    # Group executions by pipeline_id
    pipeline_exec_map = {}
    for ex in executions_raw:
        pid = ex["pipeline_id"]
        if pid not in pipeline_exec_map:
            pipeline_exec_map[pid] = []
        pipeline_exec_map[pid].append({
            "test_id": ex["test_id"],
            "result": ex["result"],
            "duration_ms": round(ex["duration_seconds"] * 1000, 3),
            "is_rerun": bool(ex["is_rerun"]),
            "parent_run_id": ex["parent_run_id"],
            "error_type": ex["error_type"],
            "error_message": ex["error_message"],
            "stack_trace": ex["stack_trace"],
        })

    pipeline_list = []
    for p in pipelines_raw:
        pid = p["pipeline_id"]
        pipeline_list.append({
            "id": pid,
            "commit": p["commit_id"],
            "env": p["environment"],
            "result": p["result"],
            "duration_ms": round(p["duration_seconds"] * 1000, 2),
            "base_fails": p["base_failures"],
            "reruns": p["rerun_count"],
            "recovered": p["recovered_count"],
            "tests": pipeline_exec_map.get(pid, []),
        })

    # 3. Comparative results
    comp_results = {}
    if COMPARISON_JSON_PATH.exists():
        with open(COMPARISON_JSON_PATH, "r", encoding="utf-8") as f:
            comp_results = json.load(f)

    # 4. CSV data
    summary_csv = ""
    test_csv = ""
    summary_csv_p = DATA_DIR / "comparison_summary.csv"
    test_csv_p = DATA_DIR / "comparison_test_metrics.csv"
    if summary_csv_p.exists():
        summary_csv = summary_csv_p.read_text(encoding="utf-8")
    if test_csv_p.exists():
        test_csv = test_csv_p.read_text(encoding="utf-8")

    return {
        "baseline": {
            "suite": b_suite,
            "pipeline": b_pipe,
            "systemic": b_sys,
            "environments": b_env,
            "tests": b_tests,
            "pipelines": pipeline_list,
        },
        "comparison": comp_results,
        "csv_summary": summary_csv,
        "csv_test": test_csv,
    }

def generate_html(data):
    data_json_str = json.dumps(data)

    html = f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>FIM // Software Quality Analytics Platform</title>
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
  <style>
    :root {{
      color-scheme: dark;
    }}
    body {{
      background-color: #0d1117;
      color: #e6edf3;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif;
    }}
    .font-mono {{
      font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
    }}
    /* Custom scrollbars */
    ::-webkit-scrollbar {{
      width: 8px;
      height: 8px;
    }}
    ::-webkit-scrollbar-track {{
      background: #0d1117;
    }}
    ::-webkit-scrollbar-thumb {{
      background: #30363d;
      border-radius: 4px;
    }}
    ::-webkit-scrollbar-thumb:hover {{
      background: #484f58;
    }}
    .tab-btn.active {{
      background-color: #21262d;
      color: #ffffff;
      border-color: #388bfd;
    }}
    .drawer-open {{
      transform: translateX(0);
    }}
    .drawer-closed {{
      transform: translateX(100%);
    }}
  </style>
</head>
<body class="min-h-screen flex flex-col antialiased">

  <!-- TOP NAVIGATION HEADER -->
  <header class="border-b border-[#30363d] bg-[#161b22] sticky top-0 z-40">
    <div class="px-5 py-2.5 flex items-center justify-between">
      <!-- Left: Logo & Identity -->
      <div class="flex items-center space-x-3">
        <div class="flex items-center space-x-2">
          <span class="w-2.5 h-2.5 rounded-full bg-[#3fb950] inline-block"></span>
          <span class="font-mono font-bold tracking-wider text-sm text-[#ffffff] bg-[#21262d] px-2 py-0.5 rounded border border-[#30363d]">FIM</span>
          <span class="text-[#8b949e] text-xs font-mono">//</span>
          <span class="text-xs font-medium text-[#c9d1d9] tracking-wide">FLAKINESS IMPACT MEASUREMENT</span>
        </div>
        <span class="text-[#484f58] text-xs">|</span>
        <span class="text-xs text-[#8b949e] hidden md:inline">Quality Impact Analytics in CI</span>
      </div>

      <!-- Center: Navigation Tabs (Linear-style segmented pill bar) -->
      <nav class="flex items-center space-x-1 bg-[#0d1117] p-1 rounded border border-[#30363d]">
        <button onclick="switchTab('overview')" id="tab-overview" class="tab-btn active px-3 py-1 text-xs font-medium rounded text-[#8b949e] hover:text-[#e6edf3] border border-transparent transition-colors flex items-center">
          <span>Overview</span>
          <kbd class="text-[9px] text-[#8b949e] bg-[#21262d] px-1 py-0.2 rounded ml-1.5 font-mono">1</kbd>
        </button>
        <button onclick="switchTab('pipelines')" id="tab-pipelines" class="tab-btn px-3 py-1 text-xs font-medium rounded text-[#8b949e] hover:text-[#e6edf3] border border-transparent transition-colors flex items-center">
          <span>Pipeline Runs</span>
          <kbd class="text-[9px] text-[#8b949e] bg-[#21262d] px-1 py-0.2 rounded ml-1.5 font-mono">2</kbd>
        </button>
        <button onclick="switchTab('tests')" id="tab-tests" class="tab-btn px-3 py-1 text-xs font-medium rounded text-[#8b949e] hover:text-[#e6edf3] border border-transparent transition-colors flex items-center">
          <span>Test Matrix</span>
          <kbd class="text-[9px] text-[#8b949e] bg-[#21262d] px-1 py-0.2 rounded ml-1.5 font-mono">3</kbd>
        </button>
        <button onclick="switchTab('environments')" id="tab-environments" class="tab-btn px-3 py-1 text-xs font-medium rounded text-[#8b949e] hover:text-[#e6edf3] border border-transparent transition-colors flex items-center">
          <span>Environments</span>
          <kbd class="text-[9px] text-[#8b949e] bg-[#21262d] px-1 py-0.2 rounded ml-1.5 font-mono">4</kbd>
        </button>
        <button onclick="switchTab('systemic')" id="tab-systemic" class="tab-btn px-3 py-1 text-xs font-medium rounded text-[#8b949e] hover:text-[#e6edf3] border border-transparent transition-colors flex items-center">
          <span>Systemic Clusters</span>
          <kbd class="text-[9px] text-[#8b949e] bg-[#21262d] px-1 py-0.2 rounded ml-1.5 font-mono">5</kbd>
        </button>
        <button onclick="switchTab('comparative')" id="tab-comparative" class="tab-btn px-3 py-1 text-xs font-medium rounded text-[#8b949e] hover:text-[#e6edf3] border border-transparent transition-colors flex items-center">
          <span>Comparative Research</span>
          <kbd class="text-[9px] text-[#8b949e] bg-[#21262d] px-1 py-0.2 rounded ml-1.5 font-mono">6</kbd>
        </button>
      </nav>

      <!-- Right: Meta Pills -->
      <div class="flex items-center space-x-2">
        <div class="flex items-center space-x-1.5 bg-[#0d1117] px-2.5 py-1 rounded border border-[#30363d]">
          <span class="text-[11px] text-[#8b949e] uppercase font-mono">Dataset:</span>
          <span id="active-dataset-label" class="text-xs font-mono font-medium text-[#e6edf3]">Baseline (fim.db)</span>
        </div>
        <div class="hidden sm:flex items-center space-x-1 text-xs font-mono bg-[#0d1117] px-2.5 py-1 rounded border border-[#30363d] text-[#8b949e]">
          <span>Runs:</span>
          <span class="text-[#3fb950] font-semibold">200</span>
          <span class="text-[#484f58] mx-0.5">/</span>
          <span>Execs:</span>
          <span class="text-[#e6edf3] font-semibold">1,393</span>
        </div>
      </div>
    </div>
  </header>

  <!-- SUBHEADER STATUS METRICS STRIP -->
  <div class="bg-[#161b22] border-b border-[#30363d] px-5 py-2">
    <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
      <!-- Metric 1 -->
      <div class="border border-[#30363d] bg-[#0d1117] p-2.5 rounded">
        <div class="text-[11px] font-mono uppercase tracking-wider text-[#8b949e]">Suite Failure Rate</div>
        <div class="flex items-baseline justify-between mt-1">
          <span id="meta-suite-fail-rate" class="text-lg font-bold font-mono text-[#f85149]">16.08%</span>
          <span class="text-[11px] font-mono text-[#8b949e]">193 / 1,200</span>
        </div>
        <div class="w-full bg-[#21262d] h-1 rounded mt-1.5 overflow-hidden">
          <div class="bg-[#f85149] h-full" style="width: 16.08%"></div>
        </div>
      </div>
      <!-- Metric 2 -->
      <div class="border border-[#30363d] bg-[#0d1117] p-2.5 rounded">
        <div class="text-[11px] font-mono uppercase tracking-wider text-[#8b949e]">Pipeline Disruption</div>
        <div class="flex items-baseline justify-between mt-1">
          <span id="meta-pipe-fail-rate" class="text-lg font-bold font-mono text-[#f85149]">65.50%</span>
          <span class="text-[11px] font-mono text-[#8b949e]">131 / 200 pipes</span>
        </div>
        <div class="w-full bg-[#21262d] h-1 rounded mt-1.5 overflow-hidden">
          <div class="bg-[#f85149] h-full" style="width: 65.5%"></div>
        </div>
      </div>
      <!-- Metric 3 -->
      <div class="border border-[#30363d] bg-[#0d1117] p-2.5 rounded">
        <div class="text-[11px] font-mono uppercase tracking-wider text-[#8b949e]">Flaky Candidate Rate</div>
        <div class="flex items-baseline justify-between mt-1">
          <span id="meta-flaky-cand-rate" class="text-lg font-bold font-mono text-[#e3b341]">83.33%</span>
          <span class="text-[11px] font-mono text-[#8b949e]">5 / 6 tests</span>
        </div>
        <div class="w-full bg-[#21262d] h-1 rounded mt-1.5 overflow-hidden">
          <div class="bg-[#e3b341] h-full" style="width: 83.33%"></div>
        </div>
      </div>
      <!-- Metric 4 -->
      <div class="border border-[#30363d] bg-[#0d1117] p-2.5 rounded">
        <div class="text-[11px] font-mono uppercase tracking-wider text-[#8b949e]">Rerun Recovery Rate</div>
        <div class="flex items-baseline justify-between mt-1">
          <span id="meta-rerun-rec-rate" class="text-lg font-bold font-mono text-[#3fb950]">76.68%</span>
          <span class="text-[11px] font-mono text-[#8b949e]">148 / 193 reruns</span>
        </div>
        <div class="w-full bg-[#21262d] h-1 rounded mt-1.5 overflow-hidden">
          <div class="bg-[#3fb950] h-full" style="width: 76.68%"></div>
        </div>
      </div>
      <!-- Metric 5 -->
      <div class="border border-[#30363d] bg-[#0d1117] p-2.5 rounded">
        <div class="text-[11px] font-mono uppercase tracking-wider text-[#8b949e]">Rerun Overhead</div>
        <div class="flex items-baseline justify-between mt-1">
          <span id="meta-rerun-overhead" class="text-lg font-bold font-mono text-[#58a6ff]">335.75 ms</span>
          <span class="text-[11px] font-mono text-[#8b949e]">193 executions</span>
        </div>
        <div class="text-[10px] font-mono text-[#8b949e] mt-1 truncate">Strict `is_rerun=1` test duration</div>
      </div>
      <!-- Metric 6 -->
      <div class="border border-[#30363d] bg-[#0d1117] p-2.5 rounded">
        <div class="text-[11px] font-mono uppercase tracking-wider text-[#8b949e]">Systemic Flakiness Ratio</div>
        <div class="flex items-baseline justify-between mt-1">
          <span id="meta-systemic-ratio" class="text-lg font-bold font-mono text-[#a371f7]">40.00%</span>
          <span class="text-[11px] font-mono text-[#8b949e]">2 / 5 flaky tests</span>
        </div>
        <div class="w-full bg-[#21262d] h-1 rounded mt-1.5 overflow-hidden">
          <div class="bg-[#a371f7] h-full" style="width: 40.0%"></div>
        </div>
      </div>
    </div>
  </div>

  <!-- MAIN VIEWPORT CONTAINER -->
  <main class="flex-1 p-5 max-w-[1600px] w-full mx-auto space-y-6">

    <!-- =================================================================== -->
    <!-- TAB 1: OVERVIEW & SQA KPI MATRIX -->
    <!-- =================================================================== -->
    <div id="view-overview" class="space-y-6">
      <!-- Section: Execution Timeline Strip (All 200 Pipelines) -->
      <section class="border border-[#30363d] bg-[#161b22] rounded p-4">
        <div class="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-[#30363d] gap-2">
          <div>
            <h2 class="text-sm font-semibold text-[#ffffff] flex items-center space-x-2">
              <span>Pipeline Execution Timeline</span>
              <span class="text-[11px] font-mono font-normal text-[#8b949e] bg-[#0d1117] px-2 py-0.5 rounded border border-[#30363d]">200 sequential runs</span>
            </h2>
            <p class="text-xs text-[#8b949e] mt-0.5">Chronological execution sequence ordered by commit and execution ID</p>
          </div>
          <div class="flex items-center space-x-4">
            <!-- View Mode Switcher -->
            <div class="flex items-center space-x-1 bg-[#0d1117] p-0.5 rounded border border-[#30363d] text-xs font-mono">
              <button id="btn-timeline-strip" onclick="setTimelineMode('strip')" class="px-2 py-0.5 rounded bg-[#21262d] text-[#ffffff] transition-colors">Strip</button>
              <button id="btn-timeline-grid" onclick="setTimelineMode('grid')" class="px-2 py-0.5 rounded text-[#8b949e] hover:text-[#e6edf3] transition-colors">Grid (50×4)</button>
            </div>
            <!-- Legend -->
            <div class="flex items-center space-x-3 text-xs font-mono">
              <span class="flex items-center space-x-1.5"><span class="w-2.5 h-2.5 rounded-xs bg-[#238636]"></span><span class="text-[#8b949e]">Pass (69)</span></span>
              <span class="flex items-center space-x-1.5"><span class="w-2.5 h-2.5 rounded-xs bg-[#d29922]"></span><span class="text-[#8b949e]">Recovered (80)</span></span>
              <span class="flex items-center space-x-1.5"><span class="w-2.5 h-2.5 rounded-xs bg-[#da3633]"></span><span class="text-[#8b949e]">Failed (51)</span></span>
            </div>
          </div>
        </div>

        <!-- Timeline Ribbon -->
        <div class="mt-3">
          <div class="bg-[#0d1117] p-2.5 rounded border border-[#30363d]">
            <div id="timeline-ribbon" class="w-full">
              <!-- Rendered by JS -->
            </div>
            <!-- Axis scale -->
            <div class="flex justify-between items-center text-[10px] font-mono text-[#8b949e] mt-2 px-0.5 pt-1.5 border-t border-[#30363d]/40">
              <span>Run #1 (Earliest)</span>
              <span>#50</span>
              <span>#100</span>
              <span>#150</span>
              <span>Run #200 (Latest)</span>
            </div>
          </div>
          <!-- Dynamic High-Density Inspection HUD -->
          <div id="timeline-hover-info" class="text-xs font-mono text-[#8b949e] mt-2 py-1.5 px-3 bg-[#0d1117] rounded border border-[#30363d] min-h-[36px] flex flex-wrap items-center justify-between gap-2">
            <span>Hover over any run block to preview details • Click to open step inspector drawer</span>
            <span class="text-[10px] text-[#484f58] hidden sm:inline">200 runs recorded</span>
          </div>
        </div>
      </section>

      <!-- Section: Quadrant Analysis & Failure Distribution -->
      <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <!-- Left: Quadrant Scatter (7 cols) -->
        <div class="lg:col-span-7 border border-[#30363d] bg-[#161b22] rounded p-4 flex flex-col justify-between">
          <div class="pb-3 border-b border-[#30363d]">
            <h3 class="text-sm font-semibold text-[#ffffff] flex items-center justify-between">
              <span>Failure Rate vs. Recovery Rate Quadrant</span>
              <span class="text-xs font-mono text-[#8b949e]">FIM Quality Space</span>
            </h3>
            <p class="text-xs text-[#8b949e] mt-0.5">Demonstrating how identical failure rates differentiate based on recovery behavior</p>
          </div>

          <div class="py-4">
            <!-- Custom Clean SVG Quadrant Chart -->
            <div class="bg-[#0d1117] rounded border border-[#30363d] p-3 relative h-[300px]">
              <svg viewBox="0 0 500 260" class="w-full h-full">
                <!-- Grid Lines -->
                <line x1="50" y1="20" x2="50" y2="220" stroke="#30363d" stroke-width="1" />
                <line x1="50" y1="220" x2="470" y2="220" stroke="#30363d" stroke-width="1" />
                <!-- 50% Thresholds -->
                <line x1="50" y1="120" x2="470" y2="120" stroke="#21262d" stroke-dasharray="3,3" stroke-width="1" />
                <line x1="260" y1="20" x2="260" y2="220" stroke="#21262d" stroke-dasharray="3,3" stroke-width="1" />

                <!-- Quadrant Labels -->
                <text x="55" y="35" fill="#484f58" font-size="10" font-family="monospace">HIGH RECOVERY // LOW FAILURE (BENIGN FLAKY)</text>
                <text x="265" y="35" fill="#484f58" font-size="10" font-family="monospace">HIGH RECOVERY // HIGH FAILURE (RECOVERABLE IMPACT)</text>
                <text x="55" y="210" fill="#484f58" font-size="10" font-family="monospace">LOW RECOVERY // LOW FAILURE</text>
                <text x="265" y="210" fill="#484f58" font-size="10" font-family="monospace">LOW RECOVERY // HIGH FAILURE (CRITICAL FLAKY)</text>

                <!-- Axis Labels -->
                <text x="240" y="245" fill="#8b949e" font-size="11" font-family="monospace" text-anchor="middle">Base Failure Rate (0% → 35%)</text>
                <text x="18" y="125" fill="#8b949e" font-size="11" font-family="monospace" text-anchor="middle" transform="rotate(-90 18,125)">Rerun Recovery Rate (0% → 100%)</text>

                <!-- Plotted Points -->
                <!-- stable: 0%, 0% -->
                <circle cx="50" cy="220" r="5" fill="#3fb950" />
                <text x="60" y="218" fill="#3fb950" font-size="10" font-family="monospace">stable (0%)</text>

                <!-- random_flaky: 10%, 95% -->
                <circle cx="170" cy="30" r="5" fill="#e3b341" />
                <text x="180" y="32" fill="#e3b341" font-size="10" font-family="monospace">random_flaky (10%, 95% rec)</text>

                <!-- environment_flaky: 5.5%, 81.8% -->
                <circle cx="116" cy="56" r="5" fill="#58a6ff" />
                <text x="126" y="58" fill="#58a6ff" font-size="10" font-family="monospace">environment_flaky (5.5%, 82% rec)</text>

                <!-- shared_state_flaky_a: 22.5%, 68.9% -->
                <circle cx="320" cy="82" r="5" fill="#a371f7" />
                <text x="330" y="80" fill="#a371f7" font-size="10" font-family="monospace">shared_state_a (22.5%, 68.9%)</text>

                <!-- shared_state_flaky_b: 29.5%, 88.1% -->
                <circle cx="404" cy="44" r="5" fill="#a371f7" />
                <text x="310" y="44" fill="#a371f7" font-size="10" font-family="monospace">shared_state_b (29.5%, 88.1%)</text>

                <!-- timing_flaky: 29.0%, 63.8% -->
                <circle cx="398" cy="92" r="5" fill="#f85149" />
                <text x="340" y="105" fill="#f85149" font-size="10" font-family="monospace">timing_flaky (29%, 63.8%)</text>
              </svg>
            </div>
          </div>

          <div class="text-xs font-mono text-[#8b949e] border-t border-[#30363d] pt-2 flex items-center justify-between">
            <span>Points plotted from verified baseline test executions ($N=1,200$).</span>
            <span class="text-[#388bfd] cursor-pointer" onclick="switchTab('tests')">Inspect Test Details →</span>
          </div>
        </div>

        <!-- Right: Failure Distribution & Environment Summary (5 cols) -->
        <div class="lg:col-span-5 space-y-6">
          <!-- Failure Distribution -->
          <div class="border border-[#30363d] bg-[#161b22] rounded p-4">
            <h3 class="text-sm font-semibold text-[#ffffff] pb-2 border-b border-[#30363d] flex items-center justify-between">
              <span>Failure Share by Test</span>
              <span class="text-xs font-mono text-[#8b949e]">Total: 193</span>
            </h3>
            <div id="test-failure-bars" class="space-y-3 mt-3">
              <!-- Rendered by JS -->
            </div>
          </div>

          <!-- Environment Health Breakdown -->
          <div class="border border-[#30363d] bg-[#161b22] rounded p-4">
            <h3 class="text-sm font-semibold text-[#ffffff] pb-2 border-b border-[#30363d] flex items-center justify-between">
              <span>Environment Disruption Matrix</span>
              <span class="text-xs font-mono text-[#8b949e]">Sensitivity: 4.33%</span>
            </h3>
            <div id="overview-env-grid" class="grid grid-cols-2 gap-2 mt-3">
              <!-- Rendered by JS -->
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- =================================================================== -->
    <!-- TAB 2: PIPELINE RUNS (GITHUB ACTIONS STYLE) -->
    <!-- =================================================================== -->
    <div id="view-pipelines" class="space-y-4 hidden">
      <!-- Search and Filter Bar -->
      <div class="flex flex-col sm:flex-row items-stretch sm:items-center justify-between bg-[#161b22] border border-[#30363d] rounded p-3 gap-3">
        <div class="flex items-center space-x-2 flex-1 max-w-md">
          <span class="text-xs font-mono text-[#8b949e]">Search:</span>
          <input type="text" id="pipe-search-input" oninput="filterPipelines()" placeholder="Filter by pipeline ID, commit, or error..." class="w-full bg-[#0d1117] border border-[#30363d] rounded px-3 py-1 text-xs text-[#e6edf3] font-mono focus:outline-none focus:border-[#388bfd]">
        </div>
        <div class="flex items-center space-x-2">
          <!-- Status Filter -->
          <select id="pipe-status-filter" onchange="filterPipelines()" class="bg-[#0d1117] border border-[#30363d] rounded px-2.5 py-1 text-xs text-[#e6edf3] font-mono focus:outline-none focus:border-[#388bfd]">
            <option value="ALL">All Outcomes (200)</option>
            <option value="PASS">Passed (69)</option>
            <option value="FAIL">Failed (131)</option>
            <option value="RECOVERED">Recovered via Rerun (80)</option>
            <option value="UNRECOVERED">Persistent Failure (51)</option>
          </select>
          <!-- Environment Filter -->
          <select id="pipe-env-filter" onchange="filterPipelines()" class="bg-[#0d1117] border border-[#30363d] rounded px-2.5 py-1 text-xs text-[#e6edf3] font-mono focus:outline-none focus:border-[#388bfd]">
            <option value="ALL">All Environments</option>
            <option value="local">local</option>
            <option value="linux">linux</option>
            <option value="windows">windows</option>
            <option value="docker">docker</option>
          </select>
          <span id="pipe-count-display" class="text-xs font-mono text-[#8b949e]">200 shown</span>
        </div>
      </div>

      <!-- Pipelines Data Table -->
      <div class="border border-[#30363d] bg-[#161b22] rounded overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs">
            <thead class="bg-[#21262d] text-[#8b949e] font-mono uppercase text-[11px] border-b border-[#30363d]">
              <tr>
                <th class="px-4 py-2.5 w-10 text-center">Status</th>
                <th class="px-4 py-2.5">Pipeline ID</th>
                <th class="px-4 py-2.5">Commit</th>
                <th class="px-4 py-2.5">Environment</th>
                <th class="px-4 py-2.5 text-right">Duration (ms)</th>
                <th class="px-4 py-2.5 text-center">Base Fails</th>
                <th class="px-4 py-2.5 text-center">Reruns</th>
                <th class="px-4 py-2.5">Intervention Outcome</th>
                <th class="px-4 py-2.5 text-right w-24">Actions</th>
              </tr>
            </thead>
            <tbody id="pipelines-table-body" class="divide-y divide-[#30363d] font-mono">
              <!-- Rendered by JS -->
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- =================================================================== -->
    <!-- TAB 3: TEST QUALITY MATRIX (LINEAR SQA TABLE STYLE) -->
    <!-- =================================================================== -->
    <div id="view-tests" class="space-y-4 hidden">
      <div class="border border-[#30363d] bg-[#161b22] rounded p-4">
        <div class="flex items-center justify-between pb-3 border-b border-[#30363d]">
          <div>
            <h2 class="text-sm font-semibold text-[#ffffff]">Test Quality Metrics Matrix</h2>
            <p class="text-xs text-[#8b949e] mt-0.5">Comprehensive multi-dimensional evaluation of benchmark test suite ($N=200$ base executions each)</p>
          </div>
          <div class="text-xs font-mono text-[#8b949e]">
            Formula: $\text{{Failure Rate}} = \text{{Base Failures}} / 200$
          </div>
        </div>

        <div class="overflow-x-auto mt-4">
          <table class="w-full text-left text-xs">
            <thead class="bg-[#21262d] text-[#8b949e] font-mono uppercase text-[11px] border-b border-[#30363d]">
              <tr>
                <th class="px-4 py-2.5">Test Identifier</th>
                <th class="px-3 py-2.5 text-center">Base Execs</th>
                <th class="px-3 py-2.5 text-center">Base Fails</th>
                <th class="px-4 py-2.5">Base Failure Rate</th>
                <th class="px-3 py-2.5 text-right">Mean Dur. (ms)</th>
                <th class="px-3 py-2.5 text-right">Duration CV</th>
                <th class="px-3 py-2.5 text-right">Outcome Trans.</th>
                <th class="px-3 py-2.5 text-center">Reruns</th>
                <th class="px-3 py-2.5 text-right">Recovery Rate</th>
                <th class="px-3 py-2.5 text-right">Overhead (ms)</th>
                <th class="px-3 py-2.5 text-right">Failed Base Time</th>
                <th class="px-3 py-2.5 text-center">Env Sensitivity</th>
                <th class="px-4 py-2.5">Classification</th>
              </tr>
            </thead>
            <tbody id="test-matrix-body" class="divide-y divide-[#30363d] font-mono">
              <!-- Rendered by JS -->
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- =================================================================== -->
    <!-- TAB 4: ENVIRONMENT ANALYSIS -->
    <!-- =================================================================== -->
    <div id="view-environments" class="space-y-6 hidden">
      <!-- Top Env Cards -->
      <div id="env-detail-cards" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <!-- Rendered by JS -->
      </div>

      <!-- Environment Cross-Matrix -->
      <div class="border border-[#30363d] bg-[#161b22] rounded p-4">
        <h3 class="text-sm font-semibold text-[#ffffff] pb-2 border-b border-[#30363d] flex items-center justify-between">
          <span>Test × Environment Failure Matrix</span>
          <span class="text-xs font-mono text-[#8b949e]">Distribution across 50 runs per cell</span>
        </h3>
        <div class="overflow-x-auto mt-4">
          <table class="w-full text-left text-xs font-mono">
            <thead class="bg-[#21262d] text-[#8b949e] uppercase text-[11px] border-b border-[#30363d]">
              <tr>
                <th class="px-4 py-2.5">Test Identifier</th>
                <th class="px-4 py-2.5 text-center">Local (50 runs)</th>
                <th class="px-4 py-2.5 text-center">Linux (50 runs)</th>
                <th class="px-4 py-2.5 text-center">Windows (50 runs)</th>
                <th class="px-4 py-2.5 text-center">Docker (50 runs)</th>
                <th class="px-4 py-2.5 text-right">Max Delta (Sensitivity)</th>
              </tr>
            </thead>
            <tbody id="env-cross-matrix-body" class="divide-y divide-[#30363d]">
              <!-- Rendered by JS -->
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- =================================================================== -->
    <!-- TAB 5: SYSTEMIC CLUSTERS -->
    <!-- =================================================================== -->
    <div id="view-systemic" class="space-y-6 hidden">
      <!-- Executive Summary -->
      <div class="border border-[#30363d] bg-[#161b22] rounded p-4">
        <div class="flex items-center justify-between pb-3 border-b border-[#30363d]">
          <div>
            <h2 class="text-sm font-semibold text-[#ffffff]">Failure Signature Clustering & Systemic Diagnosis</h2>
            <p class="text-xs text-[#8b949e] mt-0.5">Grouping base failure records by `(error_type, error_message)` to isolate shared root causes</p>
          </div>
          <div class="flex items-center space-x-2 text-xs font-mono">
            <span class="bg-[#21262d] px-2.5 py-1 rounded text-[#a371f7] border border-[#a371f7]/30">Systemic Flakiness Ratio: 40.0%</span>
          </div>
        </div>

        <div id="systemic-cluster-cards" class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
          <!-- Rendered by JS -->
        </div>
      </div>
    </div>

    <!-- =================================================================== -->
    <!-- TAB 6: COMPARATIVE RESEARCH (EXPERIMENT 2) -->
    <!-- =================================================================== -->
    <div id="view-comparative" class="space-y-6 hidden">
      <!-- Hypothesis Banner -->
      <div class="border border-[#388bfd]/40 bg-[#161b22] rounded p-4 border-l-4 border-l-[#388bfd]">
        <div class="flex items-start justify-between">
          <div>
            <span class="text-[11px] font-mono uppercase tracking-wider text-[#58a6ff] font-semibold">Central Research Hypothesis</span>
            <p class="text-sm font-medium text-[#e6edf3] mt-1">
              "Tests with comparable failure frequencies can have different quality impacts, and multidimensional metrics can reveal those differences."
            </p>
            <p class="text-xs text-[#8b949e] mt-1 font-mono">
              Parity Control: All 4 Scenarios have exactly 200 pipelines, 1,200 base executions, and 40 base failures (3.3333% suite failure rate).
            </p>
          </div>
          <div class="flex items-center space-x-2">
            <button onclick="downloadCSV('summary')" class="bg-[#21262d] hover:bg-[#30363d] text-[#e6edf3] text-xs font-mono px-3 py-1.5 rounded border border-[#30363d] transition-colors">Download Summary CSV</button>
            <button onclick="downloadCSV('test')" class="bg-[#21262d] hover:bg-[#30363d] text-[#e6edf3] text-xs font-mono px-3 py-1.5 rounded border border-[#30363d] transition-colors">Download Test CSV</button>
          </div>
        </div>
      </div>

      <!-- Consolidated Side-by-Side Comparison Table -->
      <div class="border border-[#30363d] bg-[#161b22] rounded p-4">
        <h3 class="text-sm font-semibold text-[#ffffff] pb-2 border-b border-[#30363d]">Consolidated Multi-Scenario Metrics Table</h3>
        <div class="overflow-x-auto mt-4">
          <table class="w-full text-left text-xs font-mono">
            <thead class="bg-[#21262d] text-[#8b949e] uppercase text-[11px] border-b border-[#30363d]">
              <tr>
                <th class="px-4 py-2.5">Evaluation Dimension</th>
                <th class="px-4 py-2.5 text-center">Scenario A<br><span class="text-[10px] text-[#3fb950] font-normal">Recoverable Flaky</span></th>
                <th class="px-4 py-2.5 text-center">Scenario B<br><span class="text-[10px] text-[#f85149] font-normal">Persistent Flaky</span></th>
                <th class="px-4 py-2.5 text-center">Scenario C<br><span class="text-[10px] text-[#58a6ff] font-normal">Env-Concentrated</span></th>
                <th class="px-4 py-2.5 text-center">Scenario D<br><span class="text-[10px] text-[#a371f7] font-normal">Systemic Co-Failure</span></th>
              </tr>
            </thead>
            <tbody id="comparative-table-body" class="divide-y divide-[#30363d]">
              <!-- Rendered by JS -->
            </tbody>
          </table>
        </div>
      </div>

      <!-- Analytical Insights Grid -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div class="border border-[#30363d] bg-[#161b22] rounded p-4 space-y-2">
          <h4 class="text-xs font-mono font-semibold uppercase text-[#3fb950] flex items-center space-x-1.5">
            <span>●</span>
            <span>Recovery Delta: Scenario A vs Scenario B</span>
          </h4>
          <p class="text-xs text-[#8b949e]">
            Holding base failures identical at 40 (3.33%), Scenario A recovers 90% of failures upon rerun, while Scenario B only recovers 20%. Scenario B wastes <strong class="text-[#f85149]">767.8% more rerun execution time</strong> and <strong class="text-[#f85149]">67.1% more total failed test time</strong>.
          </p>
        </div>

        <div class="border border-[#30363d] bg-[#161b22] rounded p-4 space-y-2">
          <h4 class="text-xs font-mono font-semibold uppercase text-[#a371f7] flex items-center space-x-1.5">
            <span>●</span>
            <span>Pipeline Consolidation: Scenario A vs Scenario D</span>
          </h4>
          <p class="text-xs text-[#8b949e]">
            Scenario D produces the exact same 40 base failures as Scenario A, but co-locates them across two tests in 20 shared pipelines. Consequently, <strong class="text-[#ffffff]">only 20 pipelines fail (10.0%)</strong> in D versus <strong class="text-[#f85149]">40 pipelines (20.0%)</strong> in A. Systemic clustering captures this shared infrastructure risk (100% systemic flakiness ratio).
          </p>
        </div>
      </div>
    </div>

  </main>

  <!-- GITHUB ACTIONS STYLE RUN INSPECTOR DRAWER -->
  <div id="inspector-overlay" onclick="closeInspector()" class="fixed inset-0 bg-black/60 z-50 hidden transition-opacity"></div>
  <div id="inspector-drawer" class="fixed right-0 top-0 bottom-0 w-full max-w-2xl bg-[#161b22] border-l border-[#30363d] z-50 drawer-closed transition-transform duration-200 flex flex-col shadow-2xl">
    <!-- Drawer Header -->
    <div class="p-4 border-b border-[#30363d] flex items-center justify-between bg-[#21262d]">
      <div class="flex items-center space-x-2">
        <span id="drawer-status-badge" class="px-2 py-0.5 rounded text-xs font-mono font-semibold">PASS</span>
        <h3 id="drawer-title" class="font-mono text-sm font-semibold text-[#ffffff]">pipeline-1</h3>
      </div>
      <button onclick="closeInspector()" class="text-[#8b949e] hover:text-[#ffffff] text-lg font-mono p-1">✕</button>
    </div>

    <!-- Drawer Meta Strip -->
    <div class="px-4 py-2.5 bg-[#0d1117] border-b border-[#30363d] flex items-center justify-between text-xs font-mono text-[#8b949e]">
      <div>Commit: <span id="drawer-commit" class="text-[#e6edf3]">synthetic-1</span></div>
      <div>Environment: <span id="drawer-env" class="text-[#e6edf3]">local</span></div>
      <div>Duration: <span id="drawer-duration" class="text-[#e6edf3]">3.21 ms</span></div>
    </div>

    <!-- Drawer Content (Step Execution List) -->
    <div id="drawer-steps-list" class="flex-1 overflow-y-auto p-4 space-y-3 font-mono text-xs">
      <!-- Rendered by JS -->
    </div>
  </div>

  <!-- APPLICATION EMBEDDED DATA & SCRIPT ENGINE -->
  <script>
    const FIM_DATA = {data_json_str};

    let currentTab = 'overview';
    let filteredPipelines = [];

    function switchTab(tabId) {{
      currentTab = tabId;
      const tabs = ['overview', 'pipelines', 'tests', 'environments', 'systemic', 'comparative'];
      tabs.forEach(t => {{
        const btn = document.getElementById('tab-' + t);
        const view = document.getElementById('view-' + t);
        if (btn) btn.classList.toggle('active', t === tabId);
        if (view) view.classList.toggle('hidden', t !== tabId);
      }});
      if (tabId === 'pipelines') {{
        filterPipelines();
      }}
    }}

    let timelineMode = 'strip'; // 'strip' or 'grid'

    function setTimelineMode(mode) {{
      timelineMode = mode;
      const btnStrip = document.getElementById('btn-timeline-strip');
      const btnGrid = document.getElementById('btn-timeline-grid');
      if (btnStrip && btnGrid) {{
        btnStrip.className = mode === 'strip' 
          ? 'px-2 py-0.5 rounded bg-[#21262d] text-[#ffffff] transition-colors' 
          : 'px-2 py-0.5 rounded text-[#8b949e] hover:text-[#e6edf3] transition-colors';
        btnGrid.className = mode === 'grid' 
          ? 'px-2 py-0.5 rounded bg-[#21262d] text-[#ffffff] transition-colors' 
          : 'px-2 py-0.5 rounded text-[#8b949e] hover:text-[#e6edf3] transition-colors';
      }}
      renderTimelineRibbon();
    }}

    // Render Timeline Ribbon (Compact High-Density State Timeline)
    function renderTimelineRibbon() {{
      const container = document.getElementById('timeline-ribbon');
      if (!container) return;
      container.innerHTML = '';

      if (timelineMode === 'strip') {{
        container.style.display = 'flex';
        container.style.gap = '2px';
        container.style.alignItems = 'stretch';
        container.style.height = '34px';
        container.style.width = '100%';
      }} else {{
        container.style.display = 'grid';
        container.style.gridTemplateColumns = 'repeat(50, minmax(0, 1fr))';
        container.style.gap = '2.5px';
        container.style.height = 'auto';
        container.style.width = '100%';
      }}

      const pipelines = FIM_DATA.baseline.pipelines;
      pipelines.forEach((p, idx) => {{
        const bar = document.createElement('div');
        
        let color = '#238636'; // Pass
        let status = 'PASS';
        let statusClass = 'text-[#3fb950]';
        if (p.result === 'FAIL') {{
          if (p.recovered > 0 && p.recovered === p.reruns) {{
            color = '#d29922'; // Recovered
            status = 'RECOVERED';
            statusClass = 'text-[#e3b341]';
          }} else {{
            color = '#da3633'; // Failed
            status = 'FAILED';
            statusClass = 'text-[#f85149]';
          }}
        }}

        if (timelineMode === 'strip') {{
          bar.style.flex = '1 1 0';
          bar.style.minWidth = '2px';
          bar.style.height = '100%';
          bar.style.borderRadius = '1px';
        }} else {{
          bar.style.height = '13px';
          bar.style.borderRadius = '2px';
        }}

        bar.style.backgroundColor = color;
        bar.style.cursor = 'pointer';
        bar.style.transition = 'transform 0.1s ease, filter 0.1s ease';
        bar.className = 'hover:scale-y-125 hover:brightness-125';
        bar.title = `${{p.id}} (${{p.env}}) - ${{status}} - ${{p.duration_ms}}ms`;

        bar.onmouseenter = () => {{
          document.getElementById('timeline-hover-info').innerHTML = `
            <div class="flex items-center space-x-2">
              <span class="font-bold text-[#ffffff]">${{p.id}}</span>
              <span class="bg-[#161b22] px-1.5 py-0.5 rounded border border-[#30363d] text-[10px] text-[#e6edf3] font-mono">${{p.env}}</span>
              <span class="${{statusClass}} font-semibold font-mono text-[11px]">${{status}}</span>
              <span class="text-[#8b949e] text-[11px] hidden md:inline">• commit: <span class="text-[#c9d1d9] font-mono">${{p.commit}}</span></span>
              <span class="text-[#8b949e] text-[11px]">• duration: <span class="text-[#c9d1d9] font-mono">${{p.duration_ms}} ms</span></span>
            </div>
            <div class="flex items-center space-x-2 text-[11px]">
              <span class="text-[#8b949e]">Fails: <strong class="text-[#f85149]">${{p.base_fails}}</strong></span>
              <span class="text-[#8b949e]">Reruns: <strong class="text-[#e3b341]">${{p.reruns}}</strong> (Rec: <strong class="text-[#3fb950]">${{p.recovered}}</strong>)</span>
              <span class="text-[#58a6ff] hover:underline cursor-pointer ml-1">Inspect →</span>
            </div>
          `;
        }};
        bar.onclick = () => openInspector(p.id);
        container.appendChild(bar);
      }});
    }}

    // Render Failure Share Bars
    function renderTestFailureBars() {{
      const container = document.getElementById('test-failure-bars');
      if (!container) return;
      container.innerHTML = '';
      const tests = [...FIM_DATA.baseline.tests].sort((a, b) => b.failures - a.failures);
      const totalFails = FIM_DATA.baseline.pipeline.total_reruns || 193;

      tests.forEach(t => {{
        const pct = ((t.failures / totalFails) * 100).toFixed(1);
        const item = document.createElement('div');
        item.className = 'space-y-1 font-mono text-xs';
        item.innerHTML = `
          <div class="flex justify-between text-[#8b949e]">
            <span class="text-[#e6edf3] font-medium">${{t.test_id}}</span>
            <span>${{t.failures}} fails (${{pct}}%)</span>
          </div>
          <div class="w-full bg-[#0d1117] h-1.5 rounded overflow-hidden border border-[#30363d]/50">
            <div class="bg-[#f85149] h-full" style="width: ${{pct}}%"></div>
          </div>
        `;
        container.appendChild(item);
      }});
    }}

    // Render Overview Environment Grid
    function renderOverviewEnvGrid() {{
      const container = document.getElementById('overview-env-grid');
      if (!container) return;
      container.innerHTML = '';
      const envs = FIM_DATA.baseline.environments.environments;
      envs.forEach(e => {{
        const card = document.createElement('div');
        card.className = 'border border-[#30363d] bg-[#0d1117] p-2.5 rounded font-mono text-xs';
        card.innerHTML = `
          <div class="text-[#8b949e] uppercase text-[10px]">${{e.environment}}</div>
          <div class="text-[#e6edf3] font-semibold text-sm mt-0.5">${{(e.failure_rate * 100).toFixed(2)}}% fail</div>
          <div class="text-[#8b949e] text-[11px] mt-1">${{e.failures}} fails / ${{e.executions}} runs</div>
        `;
        container.appendChild(card);
      }});
    }}

    // Render Pipelines Table
    function filterPipelines() {{
      const query = (document.getElementById('pipe-search-input')?.value || '').toLowerCase();
      const statusFilter = document.getElementById('pipe-status-filter')?.value || 'ALL';
      const envFilter = document.getElementById('pipe-env-filter')?.value || 'ALL';

      const pipelines = FIM_DATA.baseline.pipelines;
      filteredPipelines = pipelines.filter(p => {{
        if (query && !p.id.toLowerCase().includes(query) && !p.commit.toLowerCase().includes(query)) return false;
        if (envFilter !== 'ALL' && p.env !== envFilter) return false;
        if (statusFilter === 'PASS' && p.result !== 'PASS') return false;
        if (statusFilter === 'FAIL' && p.result !== 'FAIL') return false;
        if (statusFilter === 'RECOVERED' && !(p.result === 'FAIL' && p.recovered > 0 && p.recovered === p.reruns)) return false;
        if (statusFilter === 'UNRECOVERED' && !(p.result === 'FAIL' && p.recovered < p.reruns)) return false;
        return true;
      }});

      document.getElementById('pipe-count-display').innerText = `${{filteredPipelines.length}} / ${{pipelines.length}} shown`;

      const tbody = document.getElementById('pipelines-table-body');
      tbody.innerHTML = '';

      filteredPipelines.slice(0, 100).forEach(p => {{
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-[#21262d]/50 transition-colors';

        let badge = '<span class="text-[#3fb950]">✔</span>';
        let outcomePill = '<span class="text-[#3fb950] bg-[#3fb950]/10 px-2 py-0.5 rounded border border-[#3fb950]/20">ALL PASS</span>';

        if (p.result === 'FAIL') {{
          badge = '<span class="text-[#f85149]">✕</span>';
          if (p.recovered > 0 && p.recovered === p.reruns) {{
            outcomePill = `<span class="text-[#d29922] bg-[#d29922]/10 px-2 py-0.5 rounded border border-[#d29922]/20">RECOVERED (${{p.recovered}}/${{p.reruns}})</span>`;
          }} else {{
            outcomePill = `<span class="text-[#f85149] bg-[#f85149]/10 px-2 py-0.5 rounded border border-[#f85149]/20">PERSISTENT FAIL (${{p.reruns - p.recovered}} unrec)</span>`;
          }}
        }}

        tr.innerHTML = `
          <td class="px-4 py-2.5 text-center">${{badge}}</td>
          <td class="px-4 py-2.5 font-medium text-[#ffffff]">${{p.id}}</td>
          <td class="px-4 py-2.5 text-[#8b949e]">${{p.commit}}</td>
          <td class="px-4 py-2.5"><span class="bg-[#0d1117] px-2 py-0.5 rounded border border-[#30363d]">${{p.env}}</span></td>
          <td class="px-4 py-2.5 text-right">${{p.duration_ms}} ms</td>
          <td class="px-4 py-2.5 text-center text-[#f85149]">${{p.base_fails}}</td>
          <td class="px-4 py-2.5 text-center text-[#e3b341]">${{p.reruns}}</td>
          <td class="px-4 py-2.5">${{outcomePill}}</td>
          <td class="px-4 py-2.5 text-right">
            <button onclick="openInspector('${{p.id}}')" class="bg-[#21262d] hover:bg-[#30363d] text-[#e6edf3] px-2 py-1 rounded border border-[#30363d]">Inspect</button>
          </td>
        `;
        tbody.appendChild(tr);
      }});
    }}

    // Render Test Matrix Table
    function renderTestMatrix() {{
      const tbody = document.getElementById('test-matrix-body');
      if (!tbody) return;
      tbody.innerHTML = '';
      const tests = FIM_DATA.baseline.tests;

      tests.forEach(t => {{
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-[#21262d]/50 transition-colors';

        let badge = '<span class="text-[#3fb950] bg-[#3fb950]/10 px-2 py-0.5 rounded border border-[#3fb950]/20">STABLE</span>';
        if (t.test_id.includes('shared_state')) {{
          badge = '<span class="text-[#a371f7] bg-[#a371f7]/10 px-2 py-0.5 rounded border border-[#a371f7]/20">SYSTEMIC FLAKY</span>';
        }} else if (t.test_id.includes('environment')) {{
          badge = '<span class="text-[#58a6ff] bg-[#58a6ff]/10 px-2 py-0.5 rounded border border-[#58a6ff]/20">ENV-SENSITIVE</span>';
        }} else if (t.failures > 0) {{
          badge = '<span class="text-[#e3b341] bg-[#e3b341]/10 px-2 py-0.5 rounded border border-[#e3b341]/20">RECOVERABLE FLAKY</span>';
        }}

        tr.innerHTML = `
          <td class="px-4 py-2.5 font-medium text-[#ffffff]">${{t.test_id}}</td>
          <td class="px-3 py-2.5 text-center">${{t.executions}}</td>
          <td class="px-3 py-2.5 text-center text-[#f85149]">${{t.failures}}</td>
          <td class="px-4 py-2.5">
            <div class="flex items-center space-x-2">
              <span class="w-12">${{(t.failure_rate * 100).toFixed(2)}}%</span>
              <div class="w-16 bg-[#0d1117] h-1.5 rounded overflow-hidden border border-[#30363d]">
                <div class="bg-[#f85149] h-full" style="width: ${{t.failure_rate * 100}}%"></div>
              </div>
            </div>
          </td>
          <td class="px-3 py-2.5 text-right">${{(t.mean_duration_seconds * 1000).toFixed(3)}}</td>
          <td class="px-3 py-2.5 text-right text-[#8b949e]">${{t.duration_cv.toFixed(4)}}</td>
          <td class="px-3 py-2.5 text-right">${{t.outcome_transition_rate.toFixed(4)}}</td>
          <td class="px-3 py-2.5 text-center text-[#e3b341]">${{t.reruns}}</td>
          <td class="px-3 py-2.5 text-right text-[#3fb950] font-semibold">${{(t.rerun_recovery_rate * 100).toFixed(1)}}%</td>
          <td class="px-3 py-2.5 text-right">${{(t.rerun_overhead_seconds * 1000).toFixed(2)}}</td>
          <td class="px-3 py-2.5 text-right">${{(t.failed_base_execution_time_seconds * 1000).toFixed(2)}}</td>
          <td class="px-3 py-2.5 text-center text-[#58a6ff]">${{(t.environment_sensitivity * 100).toFixed(1)}}%</td>
          <td class="px-4 py-2.5">${{badge}}</td>
        `;
        tbody.appendChild(tr);
      }});
    }}

    // Render Environment Details
    function renderEnvironmentDetails() {{
      const cardsCont = document.getElementById('env-detail-cards');
      const tableBody = document.getElementById('env-cross-matrix-body');
      if (!cardsCont || !tableBody) return;

      cardsCont.innerHTML = '';
      tableBody.innerHTML = '';

      const envs = FIM_DATA.baseline.environments.environments;
      envs.forEach(e => {{
        const card = document.createElement('div');
        card.className = 'border border-[#30363d] bg-[#161b22] p-4 rounded font-mono';
        card.innerHTML = `
          <div class="text-xs text-[#8b949e] uppercase font-semibold">${{e.environment}}</div>
          <div class="text-xl font-bold text-[#e6edf3] mt-1">${{(e.failure_rate * 100).toFixed(2)}}% <span class="text-xs font-normal text-[#8b949e]">fail rate</span></div>
          <div class="mt-2 text-xs space-y-1 text-[#8b949e]">
            <div>Base Executions: <span class="text-[#e6edf3]">${{e.executions}}</span></div>
            <div>Failures: <span class="text-[#f85149]">${{e.failures}}</span></div>
            <div>Flaky Candidates: <span class="text-[#e3b341]">${{e.flaky_test_count}}</span></div>
          </div>
        `;
        cardsCont.appendChild(card);
      }});

      const tests = FIM_DATA.baseline.tests;
      tests.forEach(t => {{
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-[#21262d]/50 transition-colors';
        const eRates = t.environment_failure_rates;
        tr.innerHTML = `
          <td class="px-4 py-2.5 font-medium text-[#ffffff]">${{t.test_id}}</td>
          <td class="px-4 py-2.5 text-center text-[#8b949e]">${{((eRates.local || 0) * 100).toFixed(1)}}%</td>
          <td class="px-4 py-2.5 text-center text-[#8b949e]">${{((eRates.linux || 0) * 100).toFixed(1)}}%</td>
          <td class="px-4 py-2.5 text-center font-bold text-[#58a6ff]">${{((eRates.windows || 0) * 100).toFixed(1)}}%</td>
          <td class="px-4 py-2.5 text-center text-[#8b949e]">${{((eRates.docker || 0) * 100).toFixed(1)}}%</td>
          <td class="px-4 py-2.5 text-right text-[#58a6ff] font-semibold">${{(t.environment_sensitivity * 100).toFixed(1)}}%</td>
        `;
        tableBody.appendChild(tr);
      }});
    }}

    // Render Systemic Clusters
    function renderSystemicClusters() {{
      const cont = document.getElementById('systemic-cluster-cards');
      if (!cont) return;
      cont.innerHTML = '';

      const clusters = [
        {{
          sig: "RuntimeError::Shared external resource unavailable",
          size: 2,
          tests: ["shared_state_flaky_a", "shared_state_flaky_b"],
          count: 104,
          isSystemic: true,
          desc: "Shared external resource state starvation. Reruns execute against the identical unavailable dependency."
        }},
        {{
          sig: "RuntimeError::Timing threshold violated",
          size: 1,
          tests: ["timing_flaky"],
          count: 58,
          isSystemic: false,
          desc: "Execution latency exceeded deterministic deadline threshold ($p=0.30$)."
        }},
        {{
          sig: "RuntimeError::Random nondeterministic failure",
          size: 1,
          tests: ["random_flaky"],
          count: 20,
          isSystemic: false,
          desc: "Memoryless stochastic failure event ($p=0.10$)."
        }},
        {{
          sig: "RuntimeError::Environment-sensitive dependency failure",
          size: 1,
          tests: ["environment_flaky"],
          count: 11,
          isSystemic: false,
          desc: "OS-specific platform incompatibility concentrated on Windows ($p=0.20$)."
        }}
      ];

      clusters.forEach(c => {{
        const card = document.createElement('div');
        const borderColor = c.isSystemic ? 'border-[#a371f7]/40 bg-[#161b22]' : 'border-[#30363d] bg-[#161b22]';
        const badge = c.isSystemic 
          ? '<span class="text-[#a371f7] bg-[#a371f7]/10 px-2 py-0.5 rounded border border-[#a371f7]/20 text-[11px] font-semibold">SYSTEMIC CLUSTER (≥2 TESTS)</span>'
          : '<span class="text-[#8b949e] bg-[#21262d] px-2 py-0.5 rounded text-[11px]">ISOLATED SIGNATURE</span>';

        card.className = `border ${{borderColor}} rounded p-4 font-mono text-xs space-y-3`;
        card.innerHTML = `
          <div class="flex items-start justify-between">
            ${{badge}}
            <span class="text-[#8b949e]">${{c.count}} occurrences</span>
          </div>
          <div class="font-bold text-[#ffffff] break-all">${{c.sig}}</div>
          <p class="text-[#8b949e] font-sans text-xs">${{c.desc}}</p>
          <div class="pt-2 border-t border-[#30363d] flex items-center space-x-2">
            <span class="text-[#8b949e]">Affected Tests:</span>
            ${{c.tests.map(t => `<span class="bg-[#0d1117] text-[#e6edf3] px-1.5 py-0.5 rounded border border-[#30363d]">${{t}}</span>`).join(' ')}}
          </div>
        `;
        cont.appendChild(card);
      }});
    }}

    // Render Comparative Table
    function renderComparativeTable() {{
      const tbody = document.getElementById('comparative-table-body');
      if (!tbody) return;
      tbody.innerHTML = '';
      const comp = FIM_DATA.comparison;
      if (!comp || !comp.scenario_a) return;

      const rows = [
        ["Total Pipelines Executed", comp.scenario_a.pipeline.pipelines, comp.scenario_b.pipeline.pipelines, comp.scenario_c.pipeline.pipelines, comp.scenario_d.pipeline.pipelines],
        ["Total Base Executions", comp.scenario_a.suite.base_executions, comp.scenario_b.suite.base_executions, comp.scenario_c.suite.base_executions, comp.scenario_d.suite.base_executions],
        ["Total Base Failures", 40, 40, 40, 40],
        ["Suite Base Failure Rate", "3.3333%", "3.3333%", "3.3333%", "3.3333%"],
        ["Target Test Base Failure Rate", "20.00% (test_1)", "20.00% (test_1)", "20.00% (test_1)", "10.00% (test_1, test_2)"],
        ["Total Reruns Triggered", comp.scenario_a.pipeline.total_reruns, comp.scenario_b.pipeline.total_reruns, comp.scenario_c.pipeline.total_reruns, comp.scenario_d.pipeline.total_reruns],
        ["Recovered Reruns (Pass)", comp.scenario_a.pipeline.recovered_failures, comp.scenario_b.pipeline.recovered_failures, comp.scenario_c.pipeline.recovered_failures, comp.scenario_d.pipeline.recovered_failures],
        ["Rerun Recovery Rate", "90.00%", "20.00%", "90.00%", "90.00%"],
        ["Failed Pipeline Runs", "40 (20.0%)", "40 (20.0%)", "40 (20.0%)", "<strong class='text-[#3fb950]'>20 (10.0%)</strong>"],
        ["Target Test Env Sensitivity", "0.00%", "0.00%", "<strong class='text-[#58a6ff]'>80.00% (Windows)</strong>", "0.00%"],
        ["Suite Environment Sensitivity", "0.00%", "0.00%", "13.33%", "0.00%"],
        ["Systemic Clusters (≥2 tests)", 0, 0, 0, "<strong class='text-[#a371f7]'>1</strong>"],
        ["Systemic Flakiness Ratio", "0.00%", "0.00%", "0.00%", "<strong class='text-[#a371f7]'>100.00%</strong>"],
        ["Total Failed Test Time", "27.18 ms", "<strong class='text-[#f85149]'>45.42 ms (+67.1%)</strong>", "27.01 ms", "25.76 ms"],
      ];

      rows.forEach(r => {{
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-[#21262d]/50 transition-colors';
        tr.innerHTML = `
          <td class="px-4 py-2.5 font-medium text-[#ffffff]">${{r[0]}}</td>
          <td class="px-4 py-2.5 text-center text-[#8b949e]">${{r[1]}}</td>
          <td class="px-4 py-2.5 text-center text-[#8b949e]">${{r[2]}}</td>
          <td class="px-4 py-2.5 text-center text-[#8b949e]">${{r[3]}}</td>
          <td class="px-4 py-2.5 text-center text-[#8b949e]">${{r[4]}}</td>
        `;
        tbody.appendChild(tr);
      }});
    }}

    // Inspector Drawer
    function openInspector(pipelineId) {{
      const p = FIM_DATA.baseline.pipelines.find(x => x.id === pipelineId);
      if (!p) return;

      document.getElementById('drawer-title').innerText = p.id;
      document.getElementById('drawer-commit').innerText = p.commit;
      document.getElementById('drawer-env').innerText = p.env;
      document.getElementById('drawer-duration').innerText = `${{p.duration_ms}} ms`;

      const badge = document.getElementById('drawer-status-badge');
      if (p.result === 'PASS') {{
        badge.className = 'px-2 py-0.5 rounded text-xs font-mono font-semibold bg-[#238636] text-[#ffffff]';
        badge.innerText = 'PASS';
      }} else {{
        badge.className = 'px-2 py-0.5 rounded text-xs font-mono font-semibold bg-[#da3633] text-[#ffffff]';
        badge.innerText = 'FAIL';
      }}

      const stepsList = document.getElementById('drawer-steps-list');
      stepsList.innerHTML = '';

      p.tests.forEach((t, idx) => {{
        const step = document.createElement('div');
        const isPass = t.result === 'PASS';
        const borderCls = isPass ? 'border-[#30363d]' : 'border-[#f85149]/40 bg-[#0d1117]';
        const resBadge = isPass 
          ? '<span class="text-[#3fb950] font-bold">✔ PASS</span>' 
          : '<span class="text-[#f85149] font-bold">✕ FAIL</span>';
        const rerunBadge = t.is_rerun 
          ? '<span class="text-[10px] text-[#e3b341] bg-[#e3b341]/10 px-1.5 py-0.5 rounded border border-[#e3b341]/20">RERUN</span>' 
          : '<span class="text-[10px] text-[#8b949e] bg-[#21262d] px-1.5 py-0.5 rounded">BASE</span>';

        step.className = `border ${{borderCls}} rounded p-3 space-y-2`;
        step.innerHTML = `
          <div class="flex items-center justify-between">
            <div class="flex items-center space-x-2">
              <span class="text-[#8b949e] font-mono">0${{idx + 1}}.</span>
              <span class="font-bold text-[#ffffff]">${{t.test_id}}</span>
              ${{rerunBadge}}
            </div>
            <div class="flex items-center space-x-3">
              <span class="text-[#8b949e]">${{t.duration_ms}} ms</span>
              ${{resBadge}}
            </div>
          </div>
          ${{!isPass && t.error_type ? `
            <div class="mt-2 p-2.5 bg-[#0d1117] rounded border border-[#f85149]/30 text-[11px] font-mono text-[#f85149] space-y-1">
              <div class="font-bold">${{t.error_type}}: ${{t.error_message}}</div>
              ${{t.stack_trace ? `<pre class="text-[#8b949e] text-[10px] whitespace-pre-wrap overflow-x-auto mt-1">${{t.stack_trace}}</pre>` : ''}}
            </div>
          ` : ''}}
        `;
        stepsList.appendChild(step);
      }});

      document.getElementById('inspector-overlay').classList.remove('hidden');
      document.getElementById('inspector-drawer').classList.remove('drawer-closed');
      document.getElementById('inspector-drawer').classList.add('drawer-open');
    }}

    function closeInspector() {{
      document.getElementById('inspector-overlay').classList.add('hidden');
      document.getElementById('inspector-drawer').classList.remove('drawer-open');
      document.getElementById('inspector-drawer').classList.add('drawer-closed');
    }}

    function downloadCSV(type) {{
      const content = type === 'summary' ? FIM_DATA.csv_summary : FIM_DATA.csv_test;
      const filename = type === 'summary' ? 'comparison_summary.csv' : 'comparison_test_metrics.csv';
      const blob = new Blob([content], {{ type: 'text/csv;charset=utf-8;' }});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }}

    // Linear-style Keyboard Navigation
    document.addEventListener('keydown', (e) => {{
      if (['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement?.tagName)) {{
        if (e.key === 'Escape') {{
          document.activeElement.blur();
        }}
        return;
      }}
      if (e.key === 'Escape') {{
        closeInspector();
      }} else if (e.key === '1') {{
        switchTab('overview');
      }} else if (e.key === '2') {{
        switchTab('pipelines');
      }} else if (e.key === '3') {{
        switchTab('tests');
      }} else if (e.key === '4') {{
        switchTab('environments');
      }} else if (e.key === '5') {{
        switchTab('systemic');
      }} else if (e.key === '6') {{
        switchTab('comparative');
      }}
    }});

    // Initialize View
    document.addEventListener('DOMContentLoaded', () => {{
      renderTimelineRibbon();
      renderTestFailureBars();
      renderOverviewEnvGrid();
      renderTestMatrix();
      renderEnvironmentDetails();
      renderSystemicClusters();
      renderComparativeTable();
      filterPipelines();
    }});
  </script>
</body>
</html>
"""
    return html

def main():
    print("Loading baseline and comparison experiment data...")
    data = load_data()
    print("Generating self-contained production-grade HTML dashboard...")
    html_content = generate_html(data)

    with open(DASHBOARD_HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Saved dashboard template to: {DASHBOARD_HTML_PATH}")

    with open(ARTIFACT_HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Saved user-facing artifact to: {ARTIFACT_HTML_PATH}")

if __name__ == "__main__":
    main()
