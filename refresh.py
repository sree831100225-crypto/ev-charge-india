#!/usr/bin/env python3
"""
EV Charge India - refresh pipeline.

Runs on a 6-hour schedule and performs, per source:

  1. Fetch     - pull the latest records (live HTTP, or a snapshot when offline)
  2. Normalise - map each record onto the canonical station shape
  3. Diff      - match against the DB on (source_id, source_ref)
  4. Upsert    - insert new, update changed, touch last_updated
  5. Log       - one row in refresh_log with counts and per-source notes

Registered sources
  eamrit  - e-AMRIT (NITI Aayog) public charging register. Live, no key.
            Carries a government `isValidated` flag. No connector data.

Run:  python refresh.py                 (live, snapshot fallback)
      EV_REFRESH_SIMULATE=1 python refresh.py   (exercise updates on seed data)
"""
import json
import os
import sqlite3
from datetime import datetime, timezone

from sources import eamrit

SOURCES = [
    {"id": "eamrit", "adapter": eamrit, "label": eamrit.SOURCE_LABEL},
]

UPSERT_FIELDS = [
    "name", "operator_name", "ownership", "access", "location_type", "state_code",
    "city_name", "address", "highway", "highway_direction", "latitude", "longitude",
    "contact_phone", "contact_email", "operating_hours", "is_24x7", "status",
    "num_chargers", "total_capacity_kw", "max_power_kw", "amenities",
    "google_maps_url", "apple_maps_url", "data_source", "is_validated",
]


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ensure_operator(con, name):
    if not name:
        return None
    row = con.execute("SELECT id FROM operators WHERE name=?", (name,)).fetchone()
    if row:
        return row[0]
    cur = con.execute("INSERT INTO operators(name,kind) VALUES(?,?)", (name, "Charging network"))
    return cur.lastrowid


def _ensure_city(con, city_name, state_code):
    if not city_name:
        return None, None
    row = con.execute("SELECT id,district_id FROM cities WHERE name=? AND state_code=?",
                      (city_name, state_code)).fetchone()
    if row:
        return row[0], row[1]
    d = con.execute("SELECT id FROM districts WHERE name=? AND state_code=?",
                    (city_name, state_code)).fetchone()
    if d:
        did = d[0]
    else:
        did = con.execute("INSERT INTO districts(name,state_code) VALUES(?,?)",
                          (city_name, state_code)).lastrowid
    cid = con.execute(
        "INSERT INTO cities(name,district_id,state_code,tier) VALUES(?,?,?,?)",
        (city_name, did, state_code, 2)).lastrowid
    return cid, did


def _upsert_station(con, rec):
    """Insert or update one normalised record. Returns 'created' or 'updated'."""
    sid = rec.get("source_id")
    ref = rec.get("source_ref")
    ts = now_iso()

    existing = con.execute(
        "SELECT id FROM stations WHERE source_id=? AND source_ref=?", (sid, ref)
    ).fetchone()

    state_code = rec.get("state_code") or "DL"
    if not con.execute("SELECT 1 FROM states WHERE code=?", (state_code,)).fetchone():
        con.execute("INSERT INTO states(code,name) VALUES(?,?)", (state_code, state_code))

    op_id = _ensure_operator(con, rec.get("operator"))
    cid, did = _ensure_city(con, rec.get("city"), state_code)

    amenities = json.dumps(rec.get("amenities") or [])

    if existing:
        con.execute(
            """UPDATE stations SET name=?, operator_id=?, ownership=?, access=?, location_type=?,
               state_code=?, district_id=?, city_id=?, address=?, highway_direction=?,
               latitude=?, longitude=?, contact_phone=?, contact_email=?, operating_hours=?,
               is_24x7=?, status=?, num_chargers=?, total_capacity_kw=?, max_power_kw=?,
               amenities=?, google_maps_url=?, apple_maps_url=?, data_source=?, is_validated=?,
               last_updated=? WHERE id=?""",
            (rec.get("name"), op_id, rec.get("ownership"), rec.get("access"),
             rec.get("location_type"), state_code, did, cid, rec.get("address"),
             rec.get("highway_direction"), rec.get("latitude"), rec.get("longitude"),
             rec.get("contact_phone"), rec.get("contact_email"), rec.get("operating_hours"),
             rec.get("is_24x7", 0), rec.get("status"), rec.get("num_chargers"),
             rec.get("total_capacity_kw"), rec.get("max_power_kw"), amenities,
             rec.get("google_maps_url"), rec.get("apple_maps_url"), rec.get("data_source"),
             rec.get("is_validated", 0), ts, existing["id"]),
        )
        return "updated", existing["id"]

    cur = con.execute(
        """INSERT INTO stations(name,operator_id,ownership,access,location_type,state_code,
           district_id,city_id,address,highway_direction,latitude,longitude,contact_phone,
           contact_email,operating_hours,is_24x7,status,num_chargers,total_capacity_kw,
           max_power_kw,amenities,google_maps_url,apple_maps_url,data_source,source_id,
           source_ref,is_validated,last_updated,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (rec.get("name"), op_id, rec.get("ownership"), rec.get("access"),
         rec.get("location_type"), state_code, did, cid, rec.get("address"),
         rec.get("highway_direction"), rec.get("latitude"), rec.get("longitude"),
         rec.get("contact_phone"), rec.get("contact_email"), rec.get("operating_hours"),
         rec.get("is_24x7", 0), rec.get("status"), rec.get("num_chargers"),
         rec.get("total_capacity_kw"), rec.get("max_power_kw"), amenities,
         rec.get("google_maps_url"), rec.get("apple_maps_url"), rec.get("data_source"),
         sid, ref, rec.get("is_validated", 0), ts, ts),
    )
    new_id = cur.lastrowid

    # e-AMRIT gives a free/paid hint but no connector data
    price = rec.get("tariff_price_per_kwh")
    if price is not None:
        con.execute(
            "INSERT INTO tariffs(station_id,connector_type,price_per_kwh,currency,notes) "
            "VALUES(?,?,?,?,?)",
            (new_id, None, price, "INR",
             "Free of charge (as reported by e-AMRIT)" if price == 0 else "Reported by e-AMRIT"),
        )
    return "created", new_id


def _simulate(con):
    """Exercise the update path against existing rows (no network needed)."""
    import random
    rows = con.execute("SELECT id FROM stations").fetchall()
    ts = now_iso()
    n = 0
    for r in random.sample(rows, k=min(len(rows), random.randint(8, 35))):
        if random.random() < 0.06:
            con.execute("UPDATE stations SET status=?, last_updated=? WHERE id=?",
                        (random.choice(["Operational", "Under maintenance"]), ts, r[0]))
        else:
            con.execute("UPDATE stations SET last_updated=? WHERE id=?", (ts, r[0]))
        n += 1
    return n


def run_refresh(db_path, simulate=None):
    if simulate is None:
        simulate = os.environ.get("EV_REFRESH_SIMULATE") == "1"
    started = now_iso()
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    seen = created = updated = 0
    notes = []

    if simulate:
        updated = _simulate(con)
        seen = len(con.execute("SELECT id FROM stations").fetchall())
        notes.append(f"simulated: {updated} rows refreshed")
    else:
        for src in SOURCES:
            try:
                records, mode = src["adapter"].get_records()
            except Exception as e:  # noqa: BLE001
                notes.append(f"{src['label']}: fetch failed ({e})")
                continue
            good = 0
            for raw in records:
                rec = src["adapter"].normalise(raw)
                if rec.get("latitude") is None or not rec.get("name"):
                    continue
                seen += 1
                result, _ = _upsert_station(con, rec)
                if result == "created":
                    created += 1
                else:
                    updated += 1
                good += 1
            notes.append(f"{src['label']}: {good} records ({mode})")

    con.commit()
    finished = now_iso()
    con.execute(
        """INSERT INTO refresh_log(started_at,finished_at,source,records_seen,records_created,
           records_updated,status,notes) VALUES(?,?,?,?,?,?,?,?)""",
        (started, finished, " + ".join(s["label"] for s in SOURCES), seen, created, updated,
         "success", "; ".join(notes)),
    )
    con.commit()
    con.close()
    return {"status": "success", "started_at": started, "finished_at": finished,
            "records_seen": seen, "records_created": created, "records_updated": updated,
            "notes": notes}


if __name__ == "__main__":
    db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ev_charge_india.db")
    print(json.dumps(run_refresh(db), indent=2, ensure_ascii=False))
