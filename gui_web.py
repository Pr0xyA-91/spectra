#!/usr/bin/env python3
"""
W.R.A.T. — WhiteRat Asynchronous Telemetry — Web & Cross-Platform Dashboard
A zero-dependency browser-based diagnostic dashboard for Windows, Linux, and macOS.
Provides identical functionality to the GTK interface using Python's built-in standard library.
"""

import os
import sys
import time
import json
import socket
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Optional

import serial_io
import stats_collector as sc
from wrat_engine import WRATSession
from drivers import list_drivers, DRIVER_DISPLAY_NAMES

__version__ = "0.1"

# Global state for background polling
_poll_lock = threading.Lock()
_poll_active = False
_poll_thread: Optional[threading.Thread] = None
_latest_telemetry: Dict[str, Any] = {}
_active_session: Optional[WRATSession] = None
_current_port: str = ""
_current_mfr: str = "auto"

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>W.R.A.T. — WhiteRat Asynchronous Telemetry</title>
  <style>
    :root {
      --bg: #1e1e2e;
      --card-bg: #282a36;
      --card-border: #44475a;
      --text: #f8f8f2;
      --text-muted: #6272a4;
      --accent: #8be9fd;
      --green: #50fa7b;
      --orange: #ffb86c;
      --red: #ff5555;
      --yellow: #f1fa8c;
      --purple: #bd93f9;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
    body { background-color: var(--bg); color: var(--text); padding: 16px; min-height: 100vh; }
    header { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; padding-bottom: 12px; border-bottom: 1px solid var(--card-border); margin-bottom: 16px; gap: 12px; }
    .brand-title { display: flex; align-items: center; gap: 10px; }
    .brand-title h1 { font-size: 22px; color: var(--accent); }
    .brand-title .badge-ver { background: var(--purple); color: #000; font-size: 11px; font-weight: bold; padding: 2px 6px; border-radius: 4px; }
    .controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    select, button { background: var(--card-bg); color: var(--text); border: 1px solid var(--card-border); padding: 6px 12px; border-radius: 6px; font-size: 13px; cursor: pointer; outline: none; }
    select:focus, button:focus { border-color: var(--accent); }
    button.btn-primary { background: #6272a4; color: #fff; font-weight: bold; border-color: #6272a4; }
    button.btn-primary:hover { background: #7082b6; }
    button.btn-success { background: #2e7d32; color: #fff; font-weight: bold; border-color: #2e7d32; }
    button.btn-success:hover { background: #388e3c; }
    button.btn-danger { background: #c62828; color: #fff; font-weight: bold; }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    
    /* Sensor KPI Cards Grid */
    .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin-bottom: 16px; }
    .kpi-card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 8px; padding: 10px; display: flex; flex-direction: column; justify-content: space-between; min-height: 85px; }
    .kpi-title { font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; font-weight: bold; }
    .kpi-val { font-size: 16px; font-weight: bold; margin: 4px 0; color: var(--green); }
    .kpi-sub { font-size: 11px; color: var(--text-muted); }

    /* Tabs & Content */
    .tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--card-border); margin-bottom: 16px; }
    .tab-btn { background: transparent; border: none; border-bottom: 2px solid transparent; border-radius: 0; padding: 8px 16px; color: var(--text-muted); font-size: 14px; font-weight: 500; }
    .tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); }
    .tab-content { display: none; }
    .tab-content.active { display: block; }

    /* Tables */
    table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 13px; }
    th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--card-border); }
    th { color: var(--text-muted); text-transform: uppercase; font-size: 11px; background: rgba(0,0,0,0.1); }
    tr:hover { background: rgba(255,255,255,0.02); }
    .badge { display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: bold; }
    .badge-ok { background: rgba(80, 250, 123, 0.2); color: var(--green); border: 1px solid var(--green); }
    .badge-warn { background: rgba(255, 184, 108, 0.2); color: var(--orange); border: 1px solid var(--orange); }
    .badge-err { background: rgba(255, 85, 85, 0.2); color: var(--red); border: 1px solid var(--red); }
    .badge-info { background: rgba(139, 233, 253, 0.2); color: var(--accent); border: 1px solid var(--accent); }

    /* Progress bar */
    .progress-wrap { height: 14px; background: rgba(0,0,0,0.3); border-radius: 7px; overflow: hidden; width: 100%; }
    .progress-bar { height: 100%; background: var(--purple); border-radius: 7px; transition: width 0.3s; }

    .status-bar { font-size: 12px; color: var(--text-muted); padding: 8px 0; border-top: 1px solid var(--card-border); margin-top: 20px; display: flex; justify-content: space-between; }
  </style>
</head>
<body>
  <header>
    <div class="brand-title">
      <h1>W.R.A.T.</h1>
      <span class="badge-ver">v__VERSION__ (WIN/WEB)</span>
      <span style="font-size: 12px; color: var(--text-muted);">Multi-Manufacturer Telemetry Engine</span>
    </div>
    <div class="controls">
      <label style="font-size: 12px; color: var(--text-muted);">Brand:</label>
      <select id="mfrSelect">
        <option value="auto">⚡ Auto-Detect</option>
        <option value="jura">☕ Jura</option>
        <option value="nivona">☕ Nivona</option>
        <option value="lamanti-kl">🏢 Lamanti-KL (Kalerm)</option>
        <option value="lamanti-jn">🥤 Lamanti-JN (Jetinno)</option>
      </select>

      <label style="font-size: 12px; color: var(--text-muted);">Port:</label>
      <select id="portSelect" style="min-width: 220px;"></select>
      <button id="btnRefreshPorts" title="Refresh Port List">🔄</button>

      <button id="btnManualRefresh" class="btn-primary">⚡ Refresh Sensors</button>
      <button id="btnAutoPoll" class="btn-success">▶ Start Auto-Poll (1.5s)</button>
      <button id="btnReadStats" class="btn-primary">📊 Read Full Statistics</button>
    </div>
  </header>

  <!-- 7 KPI Badges -->
  <div class="kpi-grid">
    <div class="kpi-card">
      <span class="kpi-title">💧 Water Tank</span>
      <span id="kpiTankVal" class="kpi-val">UNKNOWN</span>
      <span id="kpiTankSub" class="kpi-sub">Level Sensor</span>
    </div>
    <div class="kpi-card">
      <span class="kpi-title">📥 Drip Tray</span>
      <span id="kpiTrayVal" class="kpi-val">UNKNOWN</span>
      <span id="kpiTraySub" class="kpi-sub">Microswitch</span>
    </div>
    <div class="kpi-card">
      <span class="kpi-title">⚡ Machine State</span>
      <span id="kpiStateVal" class="kpi-val">UNKNOWN</span>
      <span id="kpiStateSub" class="kpi-sub">Operating Status</span>
    </div>
    <div class="kpi-card">
      <span class="kpi-title">☕ Coffee TB1</span>
      <span id="kpiCoffeeVal" class="kpi-val">UNKNOWN</span>
      <span id="kpiCoffeeSub" class="kpi-sub">Thermoblock 1</span>
    </div>
    <div class="kpi-card">
      <span class="kpi-title">💨 Steam TB2</span>
      <span id="kpiSteamVal" class="kpi-val">UNKNOWN</span>
      <span id="kpiSteamSub" class="kpi-sub">Thermoblock 2</span>
    </div>
    <div class="kpi-card">
      <span class="kpi-title">🌊 Water Flow</span>
      <span id="kpiFlowVal" class="kpi-val" style="color: var(--accent);">0.0 ml/s</span>
      <span id="kpiFlowSub" class="kpi-sub">Flowmeter Rate</span>
    </div>
    <div class="kpi-card">
      <span class="kpi-title">🛡️ Water Filter</span>
      <span id="kpiFilterVal" class="kpi-val">UNKNOWN</span>
      <span id="kpiFilterSub" class="kpi-sub">Hardness</span>
    </div>
  </div>

  <!-- Navigation Tabs -->
  <div class="tabs">
    <button class="tab-btn active" onclick="switchTab('tabSensors')">Physical Sensors & Contacts</button>
    <button class="tab-btn" onclick="switchTab('tabDiagnostics')">Hardware Diagnostics & Safety</button>
    <button class="tab-btn" onclick="switchTab('tabBeverages')">Beverages & Dispensings</button>
    <button class="tab-btn" onclick="switchTab('tabMaintenance')">Maintenance & Hygiene</button>
    <button class="tab-btn" onclick="switchTab('tabRaw')">Raw Telemetry & System Info</button>
  </div>

  <!-- Tab 1: Live Sensors -->
  <div id="tabSensors" class="tab-content active">
    <table>
      <thead>
        <tr><th>ID</th><th>Component / Sensor Name</th><th>Current Operational State</th><th>Status</th></tr>
      </thead>
      <tbody id="tblSwitches">
        <tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No telemetry received. Select a port and click 'Refresh Sensors'.</td></tr>
      </tbody>
    </table>
  </div>

  <!-- Tab 2: Hardware Diagnostics Tree -->
  <div id="tabDiagnostics" class="tab-content">
    <table>
      <thead>
        <tr><th>Health</th><th>Diagnostic Channel / Sensor</th><th>Details & Verification Notes</th><th>Verification</th></tr>
      </thead>
      <tbody id="tblSensors">
        <tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No diagnostic records. Click 'Refresh Sensors'.</td></tr>
      </tbody>
    </table>
  </div>

  <!-- Tab 3: Beverages -->
  <div id="tabBeverages" class="tab-content">
    <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
      <span id="bevSummaryText" style="font-size:14px; color:var(--accent); font-weight:bold;">Total Preparations: ---</span>
      <div>
        <button onclick="exportData('json')">💾 Export JSON</button>
        <button onclick="exportData('csv')">📄 Export CSV</button>
      </div>
    </div>
    <table>
      <thead>
        <tr><th>Index</th><th>Beverage / Product Name</th><th>Dispensed Preparations</th><th>Proportion</th></tr>
      </thead>
      <tbody id="tblBeverages">
        <tr><td colspan="4" style="text-align: center; color: var(--text-muted);">Perform 'Read Full Statistics' to extract beverage counters.</td></tr>
      </tbody>
    </table>
  </div>

  <!-- Tab 4: Maintenance -->
  <div id="tabMaintenance" class="tab-content">
    <table>
      <thead>
        <tr><th>Hygiene Category</th><th>Execution Count</th><th>Remaining Life Bar</th><th>Percentage</th></tr>
      </thead>
      <tbody id="tblMaintenance">
        <tr><td colspan="4" style="text-align: center; color: var(--text-muted);">Perform 'Read Full Statistics' to inspect hygiene counters.</td></tr>
      </tbody>
    </table>
  </div>

  <!-- Tab 5: Raw Telemetry -->
  <div id="tabRaw" class="tab-content">
    <div style="background:rgba(0,0,0,0.3); padding:12px; border-radius:6px; font-family:monospace; font-size:12px; white-space:pre-wrap; max-height:400px; overflow-y:auto;" id="rawJson">No raw data.</div>
  </div>

  <div class="status-bar">
    <span id="lblStatus">Ready (Windows Web Edition). Select a port to connect.</span>
    <span id="lblTimestamp">---</span>
  </div>

  <script>
    let isAutoPolling = false;
    let pollInterval = null;
    let fullStatsCache = null;

    function switchTab(tabId) {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      event.target.classList.add('active');
      document.getElementById(tabId).classList.add('active');
    }

    async function fetchPorts() {
      try {
        const res = await fetch('/api/ports');
        const ports = await res.json();
        const select = document.getElementById('portSelect');
        select.innerHTML = '';
        let activeIdx = 0;
        ports.forEach((p, idx) => {
          const opt = document.createElement('option');
          opt.value = p;
          opt.textContent = p;
          select.appendChild(opt);
          if (p.startsWith('COM') || p.startsWith('/dev/ttyUSB')) activeIdx = idx;
        });
        if (ports.length > 0) select.selectedIndex = activeIdx;
      } catch (e) {
        document.getElementById('lblStatus').textContent = 'Error querying ports: ' + e;
      }
    }

    async function queryLiveSensors(fast = false) {
      const port = document.getElementById('portSelect').value;
      const mfr = document.getElementById('mfrSelect').value;
      if (!port) return;

      document.getElementById('lblStatus').textContent = (fast ? 'Auto-polling' : 'Querying') + ' live sensors on ' + port + '...';
      try {
        const res = await fetch(`/api/sensors?port=${encodeURIComponent(port)}&mfr=${encodeURIComponent(mfr)}&fast=${fast ? 1 : 0}`);
        const data = await res.json();
        updateUI(data, fast);
      } catch (e) {
        document.getElementById('lblStatus').textContent = 'Polling error: ' + e;
      }
    }

    function updateUI(data, isFast) {
      document.getElementById('lblTimestamp').textContent = data.timestamp || new Date().toLocaleTimeString();
      document.getElementById('lblStatus').textContent = `Telemetry updated via ${data.protocol || 'UART'} (${isFast ? 'auto' : 'manual'})`;

      const telem = data.telemetry || {};
      const switches = {};
      (data.switches || []).forEach(s => { switches[s.id] = s; });

      // Water Tank
      if (switches.water_tank) {
        document.getElementById('kpiTankVal').textContent = switches.water_tank.ok ? 'WATER OK' : 'LOW / EMPTY';
        document.getElementById('kpiTankVal').style.color = switches.water_tank.ok ? 'var(--green)' : 'var(--orange)';
        document.getElementById('kpiTankSub').textContent = switches.water_tank.ok ? 'Float Sensor Nominal' : 'Refill Water Tank';
      }

      // Drip Tray
      if (switches.drip_tray) {
        document.getElementById('kpiTrayVal').textContent = switches.drip_tray.ok ? 'INSERTED' : 'MISSING';
        document.getElementById('kpiTrayVal').style.color = switches.drip_tray.ok ? 'var(--green)' : 'var(--orange)';
        document.getElementById('kpiTraySub').textContent = switches.drip_tray.ok ? 'Drawer Inserted' : 'Tray Removed';
      }

      // Machine State
      if (switches.machine_ready) {
        const s = switches.machine_ready;
        document.getElementById('kpiStateVal').textContent = s.ok ? 'READY TO BREW' : s.badge;
        document.getElementById('kpiStateVal').style.color = s.ok ? 'var(--green)' : (s.badge === 'HEATING' ? 'var(--yellow)' : 'var(--orange)');
        document.getElementById('kpiStateSub').textContent = s.status;
      }

      // Heaters
      if (telem.heater_coffee_str) {
        document.getElementById('kpiCoffeeVal').textContent = telem.heater_coffee_str;
        document.getElementById('kpiCoffeeSub').textContent = telem.heater_coffee_status || 'Ready';
      }
      if (telem.heater_steam_str) {
        document.getElementById('kpiSteamVal').textContent = telem.heater_steam_str;
        document.getElementById('kpiSteamSub').textContent = telem.heater_steam_status || 'Installed';
      }

      // Live Water Flow
      const flowRate = telem.flow_rate_ml_s || 0.0;
      const flowPulses = telem.flow_pulses || 0;
      const flowVol = telem.flow_volume_ml || 0.0;
      document.getElementById('kpiFlowVal').textContent = flowRate > 0 ? `${flowRate.toFixed(1)} ml/s` : '0.0 ml/s';
      document.getElementById('kpiFlowSub').textContent = flowRate > 0 ? `Flowing (${flowVol.toFixed(1)} ml / ${flowPulses} P)` : `Idle (${flowPulses} pulses)`;

      // Filter & Water Hardness (Manual refresh only)
      if (telem.water_hardness_dh !== undefined) {
        document.getElementById('kpiFilterVal').textContent = `${telem.water_hardness_dh} °dH`;
        document.getElementById('kpiFilterSub').textContent = telem.filter_claris_active ? 'CLARIS Active' : (telem.filter_ext_active ? 'External Filter' : 'Bypass Mode');
      }

      // Populate Switches Table
      const tblSw = document.getElementById('tblSwitches');
      tblSw.innerHTML = '';
      (data.switches || []).forEach(sw => {
        const tr = document.createElement('tr');
        const badgeClass = sw.ok ? 'badge-ok' : (sw.badge === 'HEATING' ? 'badge-info' : 'badge-warn');
        tr.innerHTML = `
          <td><code>${sw.id}</code></td>
          <td><b>${sw.name}</b></td>
          <td>${sw.status}</td>
          <td><span class="badge ${badgeClass}">${sw.badge}</span></td>
        `;
        tblSw.appendChild(tr);
      });

      // Populate Diagnostics Table
      const tblSensors = document.getElementById('tblSensors');
      tblSensors.innerHTML = '';
      (data.sensors || []).forEach(sn => {
        const tr = document.createElement('tr');
        const badgeClass = sn.ok ? 'badge-ok' : 'badge-err';
        tr.innerHTML = `
          <td><span class="badge ${badgeClass}">${sn.ok ? '🟢 NOMINAL' : '🔴 FAULT'}</span></td>
          <td><b>${sn.name}</b></td>
          <td>${sn.details || sn.status}</td>
          <td><code>${sn.badge || 'OK'}</code></td>
        `;
        tblSensors.appendChild(tr);
      });

      document.getElementById('rawJson').textContent = JSON.stringify(data, null, 2);
    }

    async function readFullStatistics() {
      const port = document.getElementById('portSelect').value;
      const mfr = document.getElementById('mfrSelect').value;
      if (!port) return;

      document.getElementById('lblStatus').textContent = `Interrogating full statistics on ${port}...`;
      const btn = document.getElementById('btnReadStats');
      btn.disabled = true;
      btn.textContent = '⏳ Reading...';

      try {
        const res = await fetch(`/api/stats?port=${encodeURIComponent(port)}&mfr=${encodeURIComponent(mfr)}`);
        const data = await res.json();
        fullStatsCache = data;
        renderFullStats(data);
        document.getElementById('lblStatus').textContent = `Full interrogation successful: ${data.total_cups || 0} cups read!`;
      } catch (e) {
        document.getElementById('lblStatus').textContent = 'Statistics error: ' + e;
      } finally {
        btn.disabled = false;
        btn.textContent = '📊 Read Full Statistics';
      }
    }

    function renderFullStats(data) {
      document.getElementById('bevSummaryText').textContent = `Total Cups: ${data.total_cups || 0} | Brew Cycles: ${data.total_preparations || 0}`;

      // Beverages
      const tblBev = document.getElementById('tblBeverages');
      tblBev.innerHTML = '';
      (data.beverages || []).forEach(b => {
        const tr = document.createElement('tr');
        const pct = data.total_cups > 0 ? ((b.count / data.total_cups) * 100).toFixed(1) : 0;
        tr.innerHTML = `
          <td><code>${b.code || b.index}</code></td>
          <td><b>${b.name}</b></td>
          <td>${b.count} cups</td>
          <td>${pct}%</td>
        `;
        tblBev.appendChild(tr);
      });

      // Maintenance
      const tblMaint = document.getElementById('tblMaintenance');
      tblMaint.innerHTML = '';
      (data.maintenance || []).forEach(m => {
        const tr = document.createElement('tr');
        const pct = m.percentage !== null && m.percentage !== undefined ? m.percentage : 100;
        tr.innerHTML = `
          <td><b>${m.label || m.name}</b></td>
          <td>${m.count} cycles</td>
          <td><div class="progress-wrap"><div class="progress-bar" style="width: ${pct}%"></div></div></td>
          <td><b>${pct}%</b></td>
        `;
        tblMaint.appendChild(tr);
      });
    }

    function toggleAutoPoll() {
      const btn = document.getElementById('btnAutoPoll');
      isAutoPolling = !isAutoPolling;
      if (isAutoPolling) {
        btn.textContent = '⏹ Stop Auto-Poll';
        btn.classList.remove('btn-success');
        btn.classList.add('btn-danger');
        queryLiveSensors(true);
        pollInterval = setInterval(() => queryLiveSensors(true), 1500);
      } else {
        btn.textContent = '▶ Start Auto-Poll (1.5s)';
        btn.classList.remove('btn-danger');
        btn.classList.add('btn-success');
        clearInterval(pollInterval);
        document.getElementById('lblStatus').textContent = 'Auto-poll stopped.';
      }
    }

    function exportData(format) {
      if (!fullStatsCache) {
        alert('Please run "Read Full Statistics" first before exporting.');
        return;
      }
      let content = '', mime = 'text/plain', ext = 'txt';
      if (format === 'json') {
        content = JSON.stringify(fullStatsCache, null, 2);
        mime = 'application/json';
        ext = 'json';
      } else if (format === 'csv') {
        const lines = ['Category,Item,Value'];
        lines.push(`Identity,Model,${fullStatsCache.machine_model || 'Unknown'}`);
        lines.push(`Summary,Total Cups,${fullStatsCache.total_cups || 0}`);
        (fullStatsCache.beverages || []).forEach(b => lines.push(`Beverage,"${b.name}",${b.count}`));
        (fullStatsCache.maintenance || []).forEach(m => lines.push(`Maintenance,"${m.label || m.name}",${m.count}`));
        content = lines.join('\n');
        mime = 'text/csv';
        ext = 'csv';
      }
      const blob = new Blob([content], { type: mime });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `wrat_export_${new Date().toISOString().slice(0,10)}.${ext}`;
      a.click();
    }

    document.getElementById('btnRefreshPorts').onclick = fetchPorts;
    document.getElementById('btnManualRefresh').onclick = () => queryLiveSensors(false);
    document.getElementById('btnAutoPoll').onclick = toggleAutoPoll;
    document.getElementById('btnReadStats').onclick = readFullStatistics;

    window.onload = () => {
      fetchPorts();
    };
  </script>
</body>
</html>
"""


class WRATWebHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence routine HTTP access logging in terminal
        pass

    def do_GET(self):
        url = urlparse(self.path)
        params = parse_qs(url.query)

        if url.path == "/" or url.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html = HTML_TEMPLATE.replace("__VERSION__", __version__)
            self.wfile.write(html.encode("utf-8"))

        elif url.path == "/api/ports":
            ports = serial_io.list_serial_ports()
            self._send_json(ports)

        elif url.path == "/api/sensors":
            port = params.get("port", [""])[0]
            mfr = params.get("mfr", ["auto"])[0]
            fast_poll = (params.get("fast", ["0"])[0] == "1")

            global _active_session, _current_port, _current_mfr
            with _poll_lock:
                if not _active_session or _current_port != port or _current_mfr != mfr:
                    _current_port = port
                    _current_mfr = mfr
                    _active_session = WRATSession(port_name=port, manufacturer=mfr)

                try:
                    data = _active_session.query_live_sensors(fast_poll=fast_poll)
                except Exception as e:
                    data = {"error": str(e), "timestamp": time.strftime("%H:%M:%S"), "switches": [], "sensors": []}

            self._send_json(data)

        elif url.path == "/api/stats":
            port = params.get("port", [""])[0]
            mfr = params.get("mfr", ["auto"])[0]

            with _poll_lock:
                session = WRATSession(port_name=port, manufacturer=mfr)
                try:
                    session.run_interrogation()
                    data = session.get_structured_summary()
                except Exception as e:
                    data = {"error": str(e)}

            self._send_json(data)

        else:
            self.send_error(404, "Not Found")

    def _send_json(self, data: Any):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def find_free_port(start_port: int = 8080) -> int:
    for port in range(start_port, start_port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start_port


def main():
    port = find_free_port(8080)
    server_address = ("127.0.0.1", port)
    httpd = HTTPServer(server_address, WRATWebHandler)

    url = f"http://127.0.0.1:{port}"
    print("=" * 78)
    print(f"  W.R.A.T. (v{__version__}) Universal Diagnostics — Web Dashboard")
    print("=" * 78)
    print(f"[*] Server listening on: {url}")
    print("[*] Opening default web browser automatically...")
    print("[*] Press Ctrl+C in this terminal window to stop the server.")
    print("=" * 78)

    # Launch browser automatically
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Shutting down W.R.A.T. Web Server...")
        httpd.server_close()


if __name__ == "__main__":
    main()
