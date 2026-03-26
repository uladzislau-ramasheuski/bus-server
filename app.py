from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS
import requests, zipfile, io, csv, os
from datetime import datetime, timedelta
import threading, time

app = Flask(__name__)
CORS(app)

GTFS_URL = "https://www.wroclaw.pl/open-data/87b09b32-f076-4475-8ec9-6020ed1f9ac0/OtwartyWroclaw_rozklad_jazdy_GTFS.zip"

STOPS = {
    "575":   "SĘPOLNO",
    "18001": "Przystanek pracy",
}

stop_data = {sid: [] for sid in STOPS}
API_TOKEN = os.environ.get("API_TOKEN", "")

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
  .refresh { background: none; border: none; color: #0a84ff; font-size: 22px; cursor: pointer; padding: 4px 8px; }
</style>
</head>
<body>
<div class="header">
  <div class="stop-tabs">
    <button class="tab active" onclick="switchStop('575', this)">SĘPOLNO</button>
    <button class="tab" onclick="switchStop('18001', this)">Praca</button>
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
    const r = await fetch("/departures?stop_id=" + currentStop, {
      headers: { "X-Token": TOKEN }
    });
    const deps = await r.json();
    const list = document.getElementById("list");
    if (!deps.length) { list.innerHTML = "<div class='empty'>Brak odjazdow</div>"; return; }
    list.innerHTML = deps.map(d => {
      const cls = d.min <= 2 ? "now" : d.min <= 5 ? "soon" : "ok";
      const minTxt = d.min === 0 ? ">>>" : d.min + " min";
      return "<div class='row'><span class='line'>" + d.line + "</span><span class='dir'>" + d.dir + "</span><span class='min " + cls + "'>" + minTxt + "</span></div>";
    }).join("");
  } catch(e) {
    document.getElementById("list").innerHTML = "<div class='empty'>Blad polaczenia</div>";
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

# ── Защита токеном ──────────────────────────────
@app.before_request
def check_token():
    if request.path == "/" :
        return None
    if API_TOKEN and request.headers.get("X-Token") != API_TOKEN:
        return jsonify({"error": "unauthorized"}), 401

# ── GTFS ────────────────────────────────────────
def find_gtfs_url():
    try:
        api = ("https://www.wroclaw.pl/open-data/api/3/action/"
               "package_show?id=rozkladjazdytransportupublicznegoplik_data")
        r = requests.get(api, timeout=10)
        for res in r.json()["result"]["resources"]:
            url = res.get("url", "")
            if "GTFS" in url and url.endswith(".zip"):
                return url
    except:
        pass
    return GTFS_URL

def load_gtfs():
    print("Загружаю GTFS...")
    try:
        r = requests.get(find_gtfs_url(), timeout=60)
        r.raise_for_status()
        z = zipfile.ZipFile(io.BytesIO(r.content))
    except Exception as e:
        print(f"Ошибка: {e}"); return

    routes = {}
    with z.open("routes.txt") as f:
        for row in csv.DictReader(io.TextIOWrapper(f, "utf-8-sig")):
            routes[row["route_id"]] = row["route_short_name"]

    trips = {}
    with z.open("trips.txt") as f:
        for row in csv.DictReader(io.TextIOWrapper(f, "utf-8-sig")):
            trips[row["trip_id"]] = {
                "line": routes.get(row["route_id"], "?"),
                "dir":  row.get("trip_headsign", "")
            }

    new_data = {sid: [] for sid in STOPS}
    with z.open("stop_times.txt") as f:
        for row in csv.DictReader(io.TextIOWrapper(f, "utf-8-sig")):
            sid = row["stop_id"]
            if sid in STOPS:
                trip = trips.get(row["trip_id"], {})
                new_data[sid].append({
                    "time": row["departure_time"],
                    "line": trip.get("line", "?"),
                    "dir":  trip.get("dir", "?")
                })

    for sid in STOPS:
        stop_data[sid] = sorted(new_data[sid], key=lambda x: x["time"])
        print(f"✓ {STOPS[sid]}: {len(stop_data[sid])} отправлений")

def get_upcoming(stop_id, limit=8):
    now = datetime.now()
    upcoming, seen = [], set()
    for dep in stop_data.get(stop_id, []):
        h, m, s = map(int, dep["time"].split(":"))
        dep_dt = now.replace(hour=0, minute=0, second=0, microsecond=0) \
                 + timedelta(hours=h, minutes=m, seconds=s)
        diff = (dep_dt - now).total_seconds() / 60
        if 0 <= diff <= 90:
            key = (dep["line"], dep["time"])
            if key not in seen:
                seen.add(key)
                upcoming.append({
                    "line": dep["line"],
                    "dir":  dep["dir"][:20],
                    "min":  int(diff),
                    "time": f"{h % 24:02d}:{m:02d}"
                })
        if len(upcoming) >= limit:
            break
    return upcoming

def refresh_loop():
    while True:
        load_gtfs()
        time.sleep(86400)

# ── Эндпоинты ───────────────────────────────────
@app.route("/")
def index():
    return HTML

@app.route("/departures")
def departures():
    stop_id = request.args.get("stop_id", "575")
    if stop_id not in STOPS:
        return jsonify({"error": "unknown stop_id"}), 404
    return jsonify(get_upcoming(stop_id))

@app.route("/status")
def status():
    return jsonify({
        "stops": {sid: len(stop_data[sid]) for sid in STOPS},
        "time":  datetime.now().strftime("%H:%M:%S"),
    })

threading.Thread(target=refresh_loop, daemon=True).start()