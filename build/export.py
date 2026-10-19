#!/usr/bin/env python3
"""Export the database to app/data.js for the PWA."""
import json
import os
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "ev_charge_india.db")
OUT = os.path.join(ROOT, "app", "data.js")

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

stations = []
for r in con.execute("""
    SELECT s.*, o.name AS operator, o.kind AS operator_kind, o.phone AS operator_phone,
           o.website AS operator_website, st.name AS state, d.name AS district, c.name AS city,
           h.number AS highway
    FROM stations s
    LEFT JOIN operators o ON o.id = s.operator_id
    LEFT JOIN states st ON st.code = s.state_code
    LEFT JOIN districts d ON d.id = s.district_id
    LEFT JOIN cities c ON c.id = s.city_id
    LEFT JOIN highways h ON h.id = s.highway_id
    ORDER BY s.id
"""):
    sid = r["id"]
    conns = [dict(x) for x in con.execute(
        "SELECT connector_type AS type, formal_name AS formal, current_type AS current,"
        " power_kw, charging_speed AS speed, quantity FROM connectors WHERE station_id=?", (sid,))]
    tariffs = [dict(x) for x in con.execute(
        "SELECT connector_type, price_per_kwh, session_fee, idle_fee_per_min FROM tariffs "
        "WHERE station_id=?", (sid,))]
    pays = [x[0] for x in con.execute(
        "SELECT method FROM station_payments WHERE station_id=? ORDER BY method", (sid,))]
    stations.append({
        "id": sid, "name": r["name"], "operator": r["operator"],
        "operator_kind": r["operator_kind"], "ownership": r["ownership"], "access": r["access"],
        "location_type": r["location_type"], "state": r["state"], "state_code": r["state_code"],
        "district": r["district"], "city": r["city"], "panchayat": r["panchayat"],
        "village": r["village"], "address": r["address"], "highway": r["highway"],
        "highway_direction": r["highway_direction"], "latitude": r["latitude"],
        "longitude": r["longitude"], "contact_phone": r["contact_phone"],
        "contact_email": r["contact_email"], "operating_hours": r["operating_hours"],
        "is_24x7": bool(r["is_24x7"]), "status": r["status"], "num_chargers": r["num_chargers"],
        "total_capacity_kw": r["total_capacity_kw"], "max_power_kw": r["max_power_kw"],
        "connectors": conns, "tariffs": tariffs, "payments": pays,
        "amenities": json.loads(r["amenities"] or "[]"),
        "google_maps_url": r["google_maps_url"], "apple_maps_url": r["apple_maps_url"],
        "operator_phone": r["operator_phone"], "operator_website": r["operator_website"],
        "last_updated": r["last_updated"], "source_id": r["source_id"],
        "source_ref": r["source_ref"], "is_validated": bool(r["is_validated"]),
        "data_source": r["data_source"], "coord_precision": r["coord_precision"],
        "venue_type": r["venue_type"],
    })

brands = [dict(x) for x in con.execute(
    "SELECT name,aliases,segment,operates_network,network_name,network_scale,"
    "connector_standard,partnership,app,website,notes,source,verified FROM brands ORDER BY "
    "operates_network DESC, segment, name")]

meta = {
    "states": [dict(x) for x in con.execute("SELECT code,name FROM states ORDER BY name")],
    "cities": [dict(x) for x in con.execute(
        "SELECT name, state_code, latitude, longitude FROM cities ORDER BY name")],
    "operators": [dict(x) for x in con.execute(
        "SELECT name,kind,website,phone FROM operators ORDER BY name")],
    "highways": [dict(x) for x in con.execute("SELECT number,name FROM highways ORDER BY number")],
    "payments": [x[0] for x in con.execute(
        "SELECT DISTINCT method FROM station_payments ORDER BY method")],
    "connectors": [x[0] for x in con.execute(
        "SELECT DISTINCT connector_type FROM connectors ORDER BY connector_type")],
    "speeds": ["Normal", "Fast", "Turbo"],
    "verified_count": con.execute("SELECT COUNT(*) FROM stations WHERE is_validated=1").fetchone()[0],
    "oem_count": con.execute("SELECT COUNT(*) FROM stations WHERE source_id='oem'").fetchone()[0],
    "venues": [x[0] for x in con.execute(
        "SELECT venue_type FROM stations WHERE venue_type IS NOT NULL "
        "GROUP BY venue_type ORDER BY COUNT(*) DESC")],
    "brands": brands,
    "brand_network_count": con.execute(
        "SELECT COUNT(*) FROM brands WHERE operates_network=1").fetchone()[0],
}
con.close()

with open(OUT, "w", encoding="utf-8") as f:
    f.write("// Auto-generated from ev_charge_india.db by build/export.py - do not edit by hand.\n")
    f.write("window.EV_META = " + json.dumps(meta, ensure_ascii=False) + ";\n")
    f.write("window.EV_DATA = " + json.dumps(stations, ensure_ascii=False) + ";\n")

print(f"exported {len(stations)} stations ({meta['verified_count']} govt-verified) -> {OUT}")
