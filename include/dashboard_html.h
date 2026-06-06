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
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0f172a; color: #e2e8f0; padding: 20px;
    min-height: 100vh;
  }
  .container { max-width: 1400px; margin: 0 auto; }
  h1 { margin-bottom: 20px; text-align: center; color: #38bdf8; font-weight: 700; letter-spacing: 0.5px; }
  .grid { display: grid; grid-template-columns: 2fr 1fr; gap: 20px; }
  @media (max-width: 768px) { .grid { grid-template-columns: 1fr; } }
  .card {
    background: #1e293b; border-radius: 12px; padding: 20px;
    box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    border: 1px solid #334155;
  }
  .card h2 {
    margin-bottom: 15px; color: #94a3b8; font-size: 0.85em;
    text-transform: uppercase; letter-spacing: 1.5px; font-weight: 600;
  }
  .stream-wrapper {
    position: relative; background: #000; border-radius: 8px;
    overflow: hidden; border: 2px solid #334155;
    aspect-ratio: 4/3; display: flex; align-items: center; justify-content: center;
  }
  #stream { width: 100%; height: 100%; object-fit: contain; transition: transform 0.3s ease; }
  #stream.rot-90 { transform: rotate(90deg); }
  #stream.rot-180 { transform: rotate(180deg); }
  #stream.rot-270 { transform: rotate(270deg); }
  .stream-badge {
    position: absolute; top: 10px; left: 10px;
    background: rgba(0,0,0,0.7); color: #38bdf8;
    padding: 4px 10px; border-radius: 6px;
    font-size: 11px; font-weight: 600; letter-spacing: 0.5px;
    backdrop-filter: blur(4px);
    border: 1px solid rgba(56,189,248,0.3);
  }
  .stream-badge .dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: #22c55e; margin-right: 6px; animation: pulse 2s infinite; }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
  .fullscreen-btn {
    position: absolute; top: 10px; right: 10px;
    background: rgba(0,0,0,0.6); color: #e2e8f0; border: 1px solid #475569;
    padding: 6px 10px; border-radius: 6px; cursor: pointer;
    font-size: 13px; transition: all 0.2s; backdrop-filter: blur(4px);
  }
  .fullscreen-btn:hover { background: #3b82f6; border-color: #3b82f6; }
  .btn {
    padding: 9px 18px; border: none; border-radius: 8px; cursor: pointer;
    font-size: 13px; font-weight: 600; transition: all 0.2s;
    display: inline-flex; align-items: center; gap: 6px;
  }
  .btn:hover { transform: translateY(-1px); filter: brightness(1.1); }
  .btn:active { transform: translateY(0); }
  .btn-primary { background: #3b82f6; color: white; }
  .btn-primary:hover { background: #2563eb; }
  .btn-success { background: #22c55e; color: white; }
  .btn-success:hover { background: #16a34a; }
  .btn-warning { background: #f59e0b; color: white; }
  .btn-warning:hover { background: #d97706; }
  .btn-danger { background: #ef4444; color: white; }
  .btn-danger:hover { background: #dc2626; }
  .btn-ghost { background: transparent; color: #94a3b8; border: 1px solid #334155; }
  .btn-ghost:hover { background: #1e293b; color: #e2e8f0; }
  .btn-sm { padding: 6px 12px; font-size: 12px; }
  select {
    padding: 9px 12px; border-radius: 8px; border: 1px solid #334155;
    background: #0f172a; color: #e2e8f0; font-size: 13px; font-weight: 500;
    cursor: pointer;
  }
  select:focus { outline: none; border-color: #3b82f6; }
  .btn-group { display: flex; gap: 4px; }
  .btn-group .btn { border-radius: 0; margin: 0; }
  .btn-group .btn:first-child { border-radius: 8px 0 0 8px; }
  .btn-group .btn:last-child { border-radius: 0 8px 8px 0; }
  #telemetry { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .metric {
    background: #0f172a; padding: 12px; border-radius: 8px; text-align: center;
    border: 1px solid #1e293b;
  }
  .metric .value { font-size: 1.4em; font-weight: 700; color: #38bdf8; font-variant-numeric: tabular-nums; }
  .metric .label { font-size: 0.75em; color: #64748b; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
  .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 15px; align-items: center; }
  .section { margin-bottom: 20px; }
  .section:last-child { margin-bottom: 0; }
  .toast {
    position: fixed; bottom: 20px; right: 20px; padding: 12px 24px;
    border-radius: 10px; color: white; font-weight: 600; display: none;
    z-index: 999; font-size: 14px; box-shadow: 0 8px 24px rgba(0,0,0,0.4);
  }
  .toast.success { background: #22c55e; }
  .toast.error { background: #ef4444; }
  .badge {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 12px; border-radius: 20px; font-size: 0.8em; font-weight: 600;
  }
  .badge-on { background: #22c55e; color: #052e16; }
  .badge-off { background: #64748b; color: #0f172a; }
  .badge-rotate { background: #3b82f6; color: #fff; }
  kbd {
    display: inline-block; padding: 2px 6px; font-size: 11px;
    background: #334155; border-radius: 4px; color: #cbd5e1;
    font-family: inherit; border: 1px solid #475569;
  }
</style>
</head>
<body>
<div class="container">
  <h1>&#x1F4F7; ESP32-S3 Camera Dashboard</h1>
  <div class="grid">
    <div class="card" style="padding: 0; overflow: hidden;">
      <div class="stream-wrapper">
        <img id="stream" src="/" alt="Live stream" draggable="false">
        <span class="stream-badge"><span class="dot"></span>LIVE</span>
        <button class="fullscreen-btn" onclick="toggleFullscreen()" title="Fullscreen (f)">&#x26F6;</button>
      </div>
      <div style="padding: 15px 20px;">
        <div class="actions">
          <button class="btn btn-primary" onclick="takeSnapshot()">&#x1F4F7; Snapshot</button>
          <div class="btn-group">
            <button class="btn btn-ghost btn-sm" onclick="rotateLeft()" title="Rotate left">&#x21B6;</button>
            <button class="btn btn-ghost btn-sm" onclick="rotateRight()" title="Rotate right">&#x21B7;</button>
            <button class="btn btn-ghost btn-sm" onclick="resetRotation()" title="Reset rotation">&#x21BA;</button>
          </div>
          <span id="rotBadge" class="badge badge-off">0&#176;</span>
          <select id="resSelect" onchange="changeResolution()">
            <option value="SVGA">SVGA (800x600)</option>
            <option value="UXGA" selected>UXGA (1600x1200)</option>
          </select>
        </div>
      </div>
    </div>
    <div>
      <div class="card section">
        <h2>&#x1F9F0; Telemetry</h2>
        <div id="telemetry">
          <div class="metric"><div class="value" id="heap">--</div><div class="label">Free Heap</div></div>
          <div class="metric"><div class="value" id="uptime">--</div><div class="label">Uptime (s)</div></div>
          <div class="metric"><div class="value" id="rssi">--</div><div class="label">WiFi RSSI</div></div>
          <div class="metric"><div class="value" id="resolution">--</div><div class="label">Resolution</div></div>
          <div class="metric"><div class="value" id="psram">--</div><div class="label">Free PSRAM</div></div>
          <div class="metric"><div class="value" id="total_psram">--</div><div class="label">Total PSRAM</div></div>
          <div class="metric"><div class="value" id="temp">--</div><div class="label">Temp (&deg;C)</div></div>
          <div class="metric"><div class="value" id="chip_id">--</div><div class="label">Chip ID</div></div>
        </div>
      </div>
      <div class="card section">
        <h2>&#x1F4A1; LED Control</h2>
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
          <span id="ledStatus" class="badge badge-off">OFF</span>
          <span style="font-size: 12px; color: #64748b;">Toggle or flash the onboard LED</span>
        </div>
        <div class="actions">
          <button class="btn btn-success" onclick="setLed('on')">&#x1F4A1; ON</button>
          <button class="btn btn-danger" onclick="setLed('off')">&#x1F4A1; OFF</button>
          <button class="btn btn-warning" onclick="flashLed()">&#x26A1; Flash (5x)</button>
        </div>
      </div>
      <div class="card section">
        <h2>&#x2328; Keyboard Shortcuts</h2>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px; font-size: 13px; color: #94a3b8;">
          <span><kbd>f</kbd> Fullscreen</span>
          <span><kbd>r</kbd> Rotate right</span>
          <span><kbd>R</kbd> Rotate left</span>
          <span><kbd>0</kbd> Reset rotation</span>
          <span><kbd>s</kbd> Snapshot</span>
          <span><kbd>Esc</kbd> Exit fullscreen</span>
        </div>
      </div>
    </div>
  </div>
</div>
<div id="toast" class="toast"></div>
<script>
  let rotation = 0;
  const classes = ['', 'rot-90', 'rot-180', 'rot-270'];

  function showToast(msg, type) {
    const t = document.getElementById('toast');
    t.textContent = msg; t.className = 'toast ' + type; t.style.display = 'block';
    setTimeout(() => t.style.display = 'none', 2500);
  }
  function applyRotation() {
    const img = document.getElementById('stream');
    img.className = classes[rotation];
    const badge = document.getElementById('rotBadge');
    const deg = rotation * 90;
    badge.textContent = deg + '\u00B0';
    badge.className = 'badge ' + (deg ? 'badge-rotate' : 'badge-off');
  }
  function rotateRight() { rotation = (rotation + 1) % 4; applyRotation(); showToast('Rotated ' + (rotation * 90) + '\u00B0', 'success'); }
  function rotateLeft() { rotation = (rotation + 3) % 4; applyRotation(); showToast('Rotated ' + (rotation * 90) + '\u00B0', 'success'); }
  function resetRotation() { rotation = 0; applyRotation(); showToast('Rotation reset', 'success'); }

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
  function toggleFullscreen() {
    const el = document.querySelector('.stream-wrapper');
    if (!document.fullscreenElement) {
      el.requestFullscreen().catch(() => {});
    } else {
      document.exitFullscreen();
    }
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
      document.getElementById('total_psram').textContent = data.total_psram || '--';
      document.getElementById('temp').textContent = data.temperature || '--';
      document.getElementById('chip_id').textContent = data.chip_id || '--';
    } catch(e) {}
  }
  document.addEventListener('keydown', (e) => {
    if (e.key === 'r' && !e.shiftKey) { e.preventDefault(); rotateRight(); }
    if (e.key === 'R') { e.preventDefault(); rotateLeft(); }
    if (e.key === '0') { e.preventDefault(); resetRotation(); }
    if (e.key === 'f' && !e.shiftKey) { e.preventDefault(); toggleFullscreen(); }
    if (e.key === 's' && !e.shiftKey) { e.preventDefault(); takeSnapshot(); }
    if (e.key === 'Escape' && document.fullscreenElement) { document.exitFullscreen(); }
  });
  setInterval(fetchTelemetry, 3000);
  fetchTelemetry();
</script>
</body>
</html>
)rawliteral";
