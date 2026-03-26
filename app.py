from flask import Flask, jsonify, request
from flask_cors import CORS
import requests, zipfile, io, csv, os
from datetime import datetime, timedelta
import threading, time

app = Flask(__name__)
CORS(app)

GTFS_URL = "https://www.wroclaw.pl/open-data/87b09b32-f076-4475-8ec9-6020ed1f9ac0/OtwartyWroclaw_rozklad_jazdy_GTFS.zip"

STOPS = {
    "575":   "SĘPOLNO",
    "18002": "Przystanek pracy",
}

stop_data = {sid: [] for sid in STOPS}
API_TOKEN = os.environ.get("API_TOKEN", "")

# ── Защита токеном ──────────────────────────────
@app.before_request
def check_token():
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