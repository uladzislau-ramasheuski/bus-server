from flask import render_template_string

HTML = '''<!DOCTYPE html>
<html lang="pl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Autobus">
<title>Autobus</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #0a0a0a; color: #fff; font-family: -apple-system, sans-serif; }
  .header { padding: 16px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #222; }
  .stop-tabs { display: flex; gap: 8px; }
  .tab { padding: 6px 14px; border-radius: 20px; font-size: 14px; font-weight: 600; cursor: pointer; border: none; background: #222; color: #888; }
  .tab.active { background: #0a84ff; color: #fff; }
  .time { font-size: 13px; color: #666; }
  .list { padding: 8px 0; }
  .row { display: flex; align-items: center; gap: 10px; padding: 11px 16px; border-bottom: 1px solid #111; }
  .line { background: #0a84ff; color: #fff; font-weight: 700; font-size: 14px; border-radius: 6px; min-width: 40px; text-align: center; padding: 3px 6px; }
  .dir { flex: 1; font-size: 14px; color: #ccc; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .min { font-size: 15px; font-weight: 600; }
  .min.now { color: #ff3b30; }
  .min.soon { color: #ff9500; }
  .min.ok { color: #30d158; }
  .empty { text-align: center; padding: 40px; color: #555; }
  .refresh { background: none; border: none; color: #0a84ff; font-size: 14px; cursor: pointer; padding: 4px 8px; }
</style>
</head>
<body>
<div class="header">
  <div class="stop-tabs">
    <button class="tab active" onclick="switchStop('575', this)">SĘPOLNO</button>
    <button class="tab" onclick="switchStop('18002', this)">Praca</button>
  </div>
  <div style="display:flex;align-items:center;gap:8px">
    <span class="time" id="clock"></span>
    <button class="refresh" onclick="load()">↻</button>
  </div>
</div>
<div class="list" id="list"><div class="empty">Ładowanie...</div></div>

<script>
const TOKEN = "moj-autobus-2024";
let currentStop = "575";

function switchStop(id, el) {
  currentStop = id;
  document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
  el.classList.add("active");
  load();
}

async function load() {
  try {
    const r = await fetch(`/departures?stop_id=${currentStop}`, {
      headers: { "X-Token": TOKEN }
    });
    const deps = await r.json();
    const list = document.getElementById("list");
    if (!deps.length) { list.innerHTML = "<div class=\'empty\'>Brak odjazdów</div>"; return; }
    list.innerHTML = deps.map(d => {
      const cls = d.min <= 2 ? "now" : d.min <= 5 ? "soon" : "ok";
      const minTxt = d.min === 0 ? ">>>" : d.min + " min";
      return `<div class="row">
        <span class="line">${d.line}</span>
        <span class="dir">${d.dir}</span>
        <span class="min ${cls}">${minTxt}</span>
      </div>`;
    }).join("");
  } catch(e) {
    document.getElementById("list").innerHTML = "<div class=\'empty\'>Błąd połączenia</div>";
  }
}

function updateClock() {
  const now = new Date();
  document.getElementById("clock").textContent =
    now.getHours().toString().padStart(2,"0") + ":" +
    now.getMinutes().toString().padStart(2,"0");
}

load();
setInterval(load, 30000);
setInterval(updateClock, 1000);
updateClock();
</script>
</body>
</html>'''

@app.route("/")
def index():
    return HTML