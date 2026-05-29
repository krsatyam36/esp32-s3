#pragma once

const char DASHBOARD_HTML[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ESP32-S3 Camera Dashboard</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; padding: 20px; }
  .container { max-width: 1200px; margin: 0 auto; }
  h1 { margin-bottom: 20px; text-align: center; color: #38bdf8; }
  .grid { display: grid; grid-template-columns: 2fr 1fr; gap: 20px; }
  @media (max-width: 768px) { .grid { grid-template-columns: 1fr; } }
  .card { background: #1e293b; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
  .card h2 { margin-bottom: 15px; color: #94a3b8; font-size: 1.1em; text-transform: uppercase; letter-spacing: 1px; }
  #stream { width: 100%; border-radius: 8px; border: 2px solid #334155; }
  .btn { padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600; margin: 5px; transition: all 0.2s; }
  .btn:hover { transform: translateY(-1px); }
  .btn-primary { background: #3b82f6; color: white; }
  .btn-primary:hover { background: #2563eb; }
  .btn-success { background: #22c55e; color: white; }
  .btn-success:hover { background: #16a34a; }
  .btn-warning { background: #f59e0b; color: white; }
  .btn-warning:hover { background: #d97706; }
  .btn-danger { background: #ef4444; color: white; }
  .btn-danger:hover { background: #dc2626; }
  select { padding: 10px; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: #e2e8f0; font-size: 14px; margin: 5px; }
  #telemetry { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .metric { background: #0f172a; padding: 12px; border-radius: 8px; text-align: center; }
  .metric .value { font-size: 1.5em; font-weight: bold; color: #38bdf8; }
  .metric .label { font-size: 0.8em; color: #64748b; margin-top: 4px; }
  .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 15px; }
  .toast { position: fixed; bottom: 20px; right: 20px; padding: 12px 24px; border-radius: 8px; color: white; font-weight: 600; display: none; z-index: 999; }
  .toast.success { background: #22c55e; }
  .toast.error { background: #ef4444; }
  .badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 0.8em; font-weight: 600; }
  .badge-on { background: #22c55e; color: #052e16; }
  .badge-off { background: #64748b; color: #0f172a; }
</style>
</head>
<body>
<div class="container">
  <h1>&#x1F4F7; ESP32-S3 Camera Dashboard</h1>
  <div class="grid">
    <div class="card">
      <h2>&#x1F4E1; Live Stream</h2>
      <img id="stream" src="/" alt="Live stream">
      <div class="actions">
        <button class="btn btn-primary" onclick="takeSnapshot()">&#x1F4F7; Snapshot</button>
        <select id="resSelect" onchange="changeResolution()">
          <option value="SVGA">SVGA (800x600)</option>
          <option value="UXGA" selected>UXGA (1600x1200)</option>
        </select>
      </div>
    </div>
    <div>
      <div class="card" style="margin-bottom: 20px;">
        <h2>&#x1F9F0; Telemetry</h2>
        <div id="telemetry">
          <div class="metric"><div class="value" id="heap">--</div><div class="label">Free Heap</div></div>
          <div class="metric"><div class="value" id="uptime">--</div><div class="label">Uptime (s)</div></div>
          <div class="metric"><div class="value" id="rssi">--</div><div class="label">WiFi RSSI</div></div>
          <div class="metric"><div class="value" id="resolution">--</div><div class="label">Resolution</div></div>
          <div class="metric"><div class="value" id="psram">--</div><div class="label">Free PSRAM</div></div>
          <div class="metric"><div class="value" id="temp">--</div><div class="label">Temp (°C)</div></div>
        </div>
      </div>
      <div class="card">
        <h2>&#x1F4A1; LED Control</h2>
        <span id="ledStatus" class="badge badge-off">OFF</span>
        <div class="actions">
          <button class="btn btn-success" onclick="setLed('on')">&#x1F4A1; ON</button>
          <button class="btn btn-danger" onclick="setLed('off')">&#x1F4A1; OFF</button>
          <button class="btn btn-warning" onclick="flashLed()">&#x26A1; Flash</button>
        </div>
      </div>
    </div>
  </div>
</div>
<div id="toast" class="toast"></div>
<script>
  function showToast(msg, type) {
    const t = document.getElementById('toast');
    t.textContent = msg; t.className = 'toast ' + type; t.style.display = 'block';
    setTimeout(() => t.style.display = 'none', 2500);
  }
  async function takeSnapshot() {
    const a = document.createElement('a');
    a.href = '/snapshot'; a.download = 'snapshot_' + Date.now() + '.jpg';
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    showToast('Snapshot saved', 'success');
  }
  async function changeResolution() {
    const val = document.getElementById('resSelect').value;
    try {
      const r = await fetch('/res?val=' + val);
      const data = await r.json();
      if (data.success) showToast('Resolution: ' + val, 'success');
      else showToast('Failed to change resolution', 'error');
    } catch(e) { showToast('Error: ' + e, 'error'); }
  }
  async function setLed(state) {
    try {
      const r = await fetch('/led?state=' + state);
      const data = await r.json();
      if (data.success) {
        const badge = document.getElementById('ledStatus');
        badge.textContent = state.toUpperCase();
        badge.className = 'badge badge-' + state;
        showToast('LED ' + state, 'success');
      }
    } catch(e) { showToast('Error: ' + e, 'error'); }
  }
  async function flashLed() {
    try {
      const r = await fetch('/flash?count=5');
      const data = await r.json();
      if (data.success) showToast('Flashing 5 times', 'success');
    } catch(e) { showToast('Error: ' + e, 'error'); }
  }
  async function fetchTelemetry() {
    try {
      const r = await fetch('/telemetry');
      const data = await r.json();
      document.getElementById('heap').textContent = data.heap || '--';
      document.getElementById('uptime').textContent = data.uptime || '--';
      document.getElementById('rssi').textContent = data.rssi || '--';
      document.getElementById('resolution').textContent = data.resolution || '--';
      document.getElementById('psram').textContent = data.free_psram || '--';
      document.getElementById('temp').textContent = data.temperature || '--';
    } catch(e) {}
  }
  setInterval(fetchTelemetry, 3000);
  fetchTelemetry();
</script>
</body>
</html>
)rawliteral";
