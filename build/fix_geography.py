#!/usr/bin/env python3
"""
Geography corrections for known upstream data errors.

Why this exists as a separate layer rather than an edit to the source file:

  * the database is rebuilt from scratch on every refresh, so a direct edit
    would be wiped
  * the raw source stays intact, so the error remains visible and the
    correction is auditable and reversible

Each entry names the record by (source_id, source_ref), states what is wrong
and why, and gives the corrected geography. Corrections are idempotent and are
stamped into `data_source` so they are visible in the app.

Run:  python build/fix_geography.py
"""
import os
import sqlite3
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "ev_charge_india.db")
NOW = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

# ---------------------------------------------------------------------------
# e-AMRIT rows 27 and 31 both carry the SAME Kochi address string
# ("KTDC Tourist Reception Centre, Shanmugham Road, Ernakulam, Marine Drive,
# Kochi, Kerala 682031") while being named after Chennai localities and given
# two different Kerala coordinates. Two rows sharing one address is a join
# bug in the upstream feed - the address was duplicated onto unrelated rows.
#
# Egmore and Koyambedu are both localities in Chennai, Tamil Nadu, so the
# names carry the real identity and the address block is the corrupt field.
# ---------------------------------------------------------------------------
CORRECTIONS = [
    dict(
        source_id="eamrit", source_ref="27",
        name="EESL Chennai Egmore metro",
        reason="Kochi address duplicated onto a Chennai-named row (upstream join bug)",
        city="Chennai", state_code="TN",
        latitude=13.0787, longitude=80.2609,     # Egmore metro (CMRL), Chennai
        address="Egmore Metro Station (CMRL), Egmore, Chennai, Tamil Nadu 600008",
        coord_precision="area",
    ),
    dict(
        source_id="eamrit", source_ref="31",
        name="EESL Koyambedu",
        reason="Kochi address duplicated onto a Chennai-named row (upstream join bug)",
        city="Chennai", state_code="TN",
        latitude=13.0694, longitude=80.1950,     # Koyambedu, Chennai
        address="Koyambedu, Chennai, Tamil Nadu 600107",
        coord_precision="area",
    ),
]

STAMP = "geography corrected"


# Localities whose home city is unambiguous. Used only to REPORT suspected
# mismatches - never to auto-correct, because the reliable field differs per row.
LOCALITY = {
    "egmore": "Chennai", "koyambedu": "Chennai", "alandur": "Chennai",
    "anna nagar": "Chennai", "shapoorji": "Kolkata", "new town": "Kolkata",
    "newtown": "Kolkata", "salt lake": "Kolkata", "koramangala": "Bengaluru",
    "peenya": "Bengaluru", "indiranagar": "Bengaluru", "marathahalli": "Bengaluru",
    "lajpat nagar": "Delhi", "gk-1": "Delhi", "andheri": "Mumbai",
    "lower parel": "Mumbai", "kurla": "Mumbai", "banjara hills": "Hyderabad",
}


def audit(con):
    """Report name-vs-geography mismatches left in the source. Reporting only -
    the authoritative field differs per row, so guessing would move a station to
    the wrong city."""
    rows = con.execute(
        "SELECT s.id, s.name, ci.name AS city, s.state_code "
        "FROM stations s LEFT JOIN cities ci ON ci.id = s.city_id "
        "WHERE s.source_id = 'eamrit' ORDER BY s.id").fetchall()
    found = []
    for r in rows:
        hay = (r["name"] or "").lower()
        for loc, city in LOCALITY.items():
            if loc in hay and r["city"] and r["city"].lower() != city.lower():
                found.append((r["id"], r["name"], r["city"], r["state_code"], city))
                break
    return found


def city_id(con, name, code):
    r = con.execute("SELECT id FROM cities WHERE name=? AND state_code=?",
                    (name, code)).fetchone()
    if r:
        return r[0]
    d = con.execute("SELECT id FROM districts WHERE name=? AND state_code=?",
                    (name, code)).fetchone()
    did = d[0] if d else con.execute(
        "INSERT INTO districts(name,state_code) VALUES(?,?)", (name, code)).lastrowid
    return con.execute(
        "INSERT INTO cities(name,district_id,state_code,tier) VALUES(?,?,?,?)",
        (name, did, code, 1)).lastrowid


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    applied = skipped = 0
    for c in CORRECTIONS:
        row = con.execute(
            "SELECT id, city_id, state_code, data_source FROM stations "
            "WHERE source_id=? AND source_ref=?",
            (c["source_id"], c["source_ref"])).fetchone()

        if not row:
            print(f"  ! {c['source_id']}#{c['source_ref']} not in the database - skipped")
            skipped += 1
            continue

        cid = city_id(con, c["city"], c["state_code"])
        did = con.execute("SELECT district_id FROM cities WHERE id=?", (cid,)).fetchone()[0]

        # already corrected? (city + state match) - keep it idempotent
        already = (row["city_id"] == cid and row["state_code"] == c["state_code"])
        src = row["data_source"] or ""
        if STAMP not in src:
            src = f"{src} - {STAMP}"

        con.execute(
            """UPDATE stations SET city_id=?, district_id=?, state_code=?,
               latitude=?, longitude=?, address=?, coord_precision=?,
               data_source=?, last_updated=? WHERE id=?""",
            (cid, did, c["state_code"], c["latitude"], c["longitude"], c["address"],
             c["coord_precision"], src, NOW, row["id"]))

        print(f"  #{row['id']:<4} {c['name'][:32]:<32} -> {c['city']}, {c['state_code']} "
              f"({c['latitude']}, {c['longitude']})"
              + ("  [already correct, re-stamped]" if already else ""))
        applied += 1

    con.commit()

    # report anything still sitting in the wrong state
    left = con.execute(
        "SELECT COUNT(*) FROM stations WHERE state_code='KL' AND "
        "(lower(name) LIKE '%egmore%' OR lower(name) LIKE '%koyambedu%' "
        "OR lower(name) LIKE '%chennai%')").fetchone()[0]

    print(f"\ncorrections applied: {applied}  (skipped: {skipped})")
    print(f"Chennai-named stations still filed in Kerala: {left}")

    # --- audit: other suspected mismatches, reported not changed ---
    sus = audit(con)
    print(f"\nsuspected name/geography mismatches in the e-AMRIT feed: {len(sus)}")
    for sid, nm, city, st, implies in sus:
        print(f"   #{sid:<4} {nm[:38]:<38} recorded={city}, {st:<3} name implies {implies}")
    if sus:
        print("   (left as-is: the address and coordinates are self-consistent in "
              "these rows, so the NAME looks like the stray field. Confirm before changing.)")
    con.close()


if __name__ == "__main__":
    main()
