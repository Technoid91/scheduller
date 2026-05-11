from flask import Flask, render_template, request, jsonify, send_file
import json
import os
import calendar
from datetime import date, timedelta
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from pdf_generator import generate_pdf
from telegram_sender import send_to_telegram

load_dotenv()

from flask import Blueprint

PORT   = int(os.getenv("PORT", 5000))
PREFIX = os.getenv("URL_PREFIX", "/scheduler").rstrip("/")

app = Flask(__name__)
app.config["APPLICATION_ROOT"] = PREFIX

bp = Blueprint("scheduler", __name__)
CONFIG_FILE = "config.json"

# Keys that belong to a snapshot (per-month config)
SNAPSHOT_KEYS = ["order", "active", "days_per_room", "anchor_date", "anchor_room"]

DEFAULT_FIRST_SNAPSHOT = {
    "order":         [1, 3, 2],
    "active":        [1, 2, 3],
    "days_per_room": 3,
    "anchor_date":   "2026-01-01",
    "anchor_room":   1,
}

DEFAULT_SNAPSHOT = DEFAULT_FIRST_SNAPSHOT

DEFAULT_GLOBAL = {
    "rooms":     [1, 2, 3],
    "autosend":  False,
    "snapshots": {},
}


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            cfg = json.load(f)
    else:
        # First run — create config.json with defaults
        cfg = {**DEFAULT_GLOBAL, "snapshots": {}}
        save_config(cfg)
        print(f"[init] Created default {CONFIG_FILE}")
    # Merge missing global keys
    for k, v in DEFAULT_GLOBAL.items():
        if k not in cfg:
            cfg[k] = v
    return cfg


def save_config(cfg: dict):
    # Sort snapshots chronologically before writing
    if "snapshots" in cfg:
        cfg["snapshots"] = dict(sorted(cfg["snapshots"].items()))
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def get_snapshot_for_month(cfg: dict, year: int, month: int) -> dict:
    """
    Return the effective snapshot for the given month.
    Finds the latest snapshot whose key <= 'YYYY-MM'.
    Falls back to DEFAULT_SNAPSHOT if none found.
    Returns (snapshot_dict, snapshot_key_or_None)
    """
    key = f"{year}-{month:02d}"
    snapshots = cfg.get("snapshots", {})
    # All keys <= requested month, sorted
    candidates = sorted(k for k in snapshots if k <= key)
    if candidates:
        src_key = candidates[-1]
        snap = {**DEFAULT_SNAPSHOT, **snapshots[src_key]}
        return snap, src_key
    return DEFAULT_SNAPSHOT.copy(), None


def build_schedule(year: int, month: int, snap: dict) -> dict:
    active_order = [r for r in snap["order"] if r in snap["active"]]
    if not active_order:
        return {}
    days_per_room = snap["days_per_room"]
    anchor_date   = date.fromisoformat(snap["anchor_date"])
    anchor_room   = snap["anchor_room"]
    anchor_idx    = active_order.index(anchor_room) if anchor_room in active_order else 0
    num_days      = calendar.monthrange(year, month)[1]
    cycle_len     = len(active_order) * days_per_room
    schedule      = {}
    for day in range(1, num_days + 1):
        delta         = (date(year, month, day) - anchor_date).days
        pos           = (delta % cycle_len + cycle_len) % cycle_len
        schedule[day] = active_order[(anchor_idx + pos // days_per_room) % len(active_order)]
    return schedule


def get_autosend_monday(year: int, month: int) -> date:
    num_days    = calendar.monthrange(year, month)[1]
    last_day    = date(year, month, num_days)
    last_monday = last_day - timedelta(days=last_day.weekday())
    if last_monday.day == num_days:
        last_monday -= timedelta(days=7)
    return last_monday


def do_autosend():
    cfg = load_config()
    if not cfg.get("autosend"):
        return
    token    = os.getenv("TELEGRAM_TOKEN", "")
    chat_ids = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_ids:
        print("[autosend] TELEGRAM_TOKEN or TELEGRAM_CHAT_ID not set in .env")
        return
    today    = date.today()
    if today != get_autosend_monday(today.year, today.month):
        return
    ny, nm   = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    snap, _  = get_snapshot_for_month(cfg, ny, nm)
    pdf_path = generate_pdf(ny, nm, build_schedule(ny, nm, snap))
    result   = send_to_telegram(pdf_path, token, chat_ids, ny, nm)
    print(f"[autosend] {result['message']}")


scheduler = BackgroundScheduler()
scheduler.add_job(do_autosend, "cron", hour=10, minute=30)
scheduler.start()


# ── Routes ───────────────────────────────────────────────────────

@bp.route("/")
def index():
    return render_template("index.html", prefix=PREFIX)


@bp.route("/api/config", methods=["GET"])
def get_config_route():
    cfg = load_config()
    return jsonify({
        "rooms":     cfg["rooms"],
        "autosend":  cfg["autosend"],
        "snapshots": cfg.get("snapshots", {}),
    })


@bp.route("/api/config", methods=["POST"])
def update_global_config():
    """Save global settings (autosend). Snapshots managed separately."""
    cfg  = load_config()
    data = request.json
    if "autosend" in data:
        cfg["autosend"] = data["autosend"]
    save_config(cfg)
    return jsonify({"status": "ok"})


@bp.route("/api/snapshot/<int:year>/<int:month>", methods=["GET"])
def get_snapshot(year, month):
    cfg          = load_config()
    snap, src    = get_snapshot_for_month(cfg, year, month)
    month_key    = f"{year}-{month:02d}"
    own_snapshot = month_key in cfg.get("snapshots", {})
    return jsonify({
        "snapshot":     snap,
        "source_key":   src,
        "own_snapshot": own_snapshot,
    })


@bp.route("/api/snapshot/<int:year>/<int:month>", methods=["POST"])
def save_snapshot(year, month):
    cfg  = load_config()
    data = request.json
    snap = {k: data[k] for k in SNAPSHOT_KEYS if k in data}
    if not cfg.get("snapshots"):
        cfg["snapshots"] = {}
    cfg["snapshots"][f"{year}-{month:02d}"] = snap
    save_config(cfg)
    return jsonify({"status": "ok"})


@bp.route("/api/snapshot/<int:year>/<int:month>", methods=["DELETE"])
def delete_snapshot(year, month):
    cfg = load_config()
    key = f"{year}-{month:02d}"
    cfg.get("snapshots", {}).pop(key, None)
    save_config(cfg)
    return jsonify({"status": "ok"})


@bp.route("/api/preview")
def preview():
    year  = int(request.args.get("year",  date.today().year))
    month = int(request.args.get("month", date.today().month))
    cfg   = load_config()
    snap, src = get_snapshot_for_month(cfg, year, month)
    return jsonify({
        "schedule":   build_schedule(year, month, snap),
        "year":       year,
        "month":      month,
        "source_key": src,
    })


@bp.route("/api/generate_pdf")
def generate_pdf_route():
    year  = int(request.args.get("year",  date.today().year))
    month = int(request.args.get("month", date.today().month))
    cfg   = load_config()
    snap, _ = get_snapshot_for_month(cfg, year, month)
    pdf_path = generate_pdf(year, month, build_schedule(year, month, snap))
    return send_file(pdf_path, as_attachment=True,
                     download_name=f"duty_{year}_{month:02d}.pdf",
                     mimetype="application/pdf")


@bp.route("/api/send_telegram", methods=["POST"])
def send_telegram_route():
    token    = os.getenv("TELEGRAM_TOKEN", "")
    chat_ids = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_ids:
        return jsonify({"status": "error",
                        "message": "Заполните TELEGRAM_TOKEN и TELEGRAM_CHAT_ID в .env"}), 400
    data     = request.json
    year     = data.get("year",  date.today().year)
    month    = data.get("month", date.today().month)
    cfg      = load_config()
    snap, _  = get_snapshot_for_month(cfg, year, month)
    pdf_path = generate_pdf(year, month, build_schedule(year, month, snap))
    return jsonify(send_to_telegram(pdf_path, token, chat_ids, year, month))



@bp.route("/api/preview_live")
def preview_live():
    """Preview schedule from URL params without touching saved config."""
    year          = int(request.args.get("year",  date.today().year))
    month         = int(request.args.get("month", date.today().month))
    order_str     = request.args.get("order",  "")
    active_str    = request.args.get("active", "")
    days_per_room = int(request.args.get("days_per_room", 2))
    anchor_date   = request.args.get("anchor_date", str(date.today().replace(day=1)))
    anchor_room   = int(request.args.get("anchor_room", 1))

    order  = [int(x) for x in order_str.split(",")  if x.strip().isdigit()]
    active = [int(x) for x in active_str.split(",") if x.strip().isdigit()]

    snap = {
        "order":         order  or DEFAULT_SNAPSHOT["order"],
        "active":        active or DEFAULT_SNAPSHOT["active"],
        "days_per_room": days_per_room,
        "anchor_date":   anchor_date,
        "anchor_room":   anchor_room,
    }
    return jsonify({"schedule": build_schedule(year, month, snap)})

app.register_blueprint(bp, url_prefix=PREFIX)

if __name__ == "__main__":
    print(f"Running on http://localhost:{PORT}{PREFIX}")
    app.run(host='0.0.0.0', port=PORT)
