#!/usr/bin/env python3
"""
EV Charge India - in-app agent.

Turns a natural-language question into a structured query against the
database and returns a spoken-style answer plus the matching stations.

This is a deterministic intent engine (no external LLM, no API key), so the
agent works offline and inside the prototype. The `answer()` function is the
single seam to swap in an LLM: keep the retrieval below, hand the ranked
stations to the model as grounding context, and return its prose.

Supported intents
  find / count stations by: city, state, district, village, highway, operator,
  connector type, charging speed (normal/fast/turbo), payment method,
  ownership (public/private), location type (urban/highway/rural),
  24x7, cheapest, and nearest (given a lat/lng).
"""
import re

SPEED_WORDS = {
    "turbo": "Turbo", "ultra": "Turbo", "hyper": "Turbo", "superfast": "Turbo",
    "rapid": "Fast", "fast": "Fast", "dc": "Fast",
    "normal": "Normal", "slow": "Normal", "ac": "Normal", "regular": "Normal",
}
CONNECTOR_WORDS = {
    "ccs2": "CCS2", "ccs": "CCS2", "combo": "CCS2",
    "chademo": "CHAdeMO",
    "type 2": "Type 2 AC", "type2": "Type 2 AC", "mennekes": "Type 2 AC",
    "type 1": "Type 1 AC", "type1": "Type 1 AC",
    "bharat dc": "Bharat DC-001", "dc-001": "Bharat DC-001", "dc001": "Bharat DC-001",
    "bharat ac": "Bharat AC-001", "ac-001": "Bharat AC-001", "ac001": "Bharat AC-001",
    "gb/t": "GB/T", "gbt": "GB/T",
}
PAY_WORDS = {
    "upi": "UPI", "card": "Credit/Debit Card", "credit card": "Credit/Debit Card",
    "debit card": "Credit/Debit Card", "wallet": "In-app Wallet", "rfid": "RFID Card",
    "net banking": "Net Banking", "qr": "QR Code",
}


def _haversine(a, b, c, d):
    import math
    R = 6371.0
    p1, p2 = math.radians(a), math.radians(c)
    dp = math.radians(c - a)
    dl = math.radians(d - b)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def _rows(con, sql, args=()):
    con.row_factory = __import__("sqlite3").Row
    return con.execute(sql, args).fetchall()


def resolve_place(con, text):
    """Turn a typed place into (lat, lng, label), or None.

    Mirrors the resolver in the web app so the API, the MCP server and the
    browser all understand the same inputs. Tried in order:
        6-digit PIN -> city name -> area/landmark -> state centroid
    """
    import re as _re
    raw = (text or "").strip()
    if not raw:
        return None
    ql = raw.lower()

    pin = _re.search(r"\b\d{6}\b", raw)
    if pin:
        r = _rows(con, "SELECT latitude,longitude FROM stations "
                       "WHERE address LIKE ? AND latitude IS NOT NULL LIMIT 1",
                  (f"%{pin.group(0)}%",))
        if r:
            return (r[0]["latitude"], r[0]["longitude"], f"PIN {pin.group(0)}")

    r = _rows(con, "SELECT name,latitude,longitude FROM cities "
                   "WHERE lower(name)=? AND latitude IS NOT NULL LIMIT 1", (ql,))
    if not r:
        r = _rows(con, "SELECT name,latitude,longitude FROM cities "
                       "WHERE lower(name) LIKE ? AND latitude IS NOT NULL "
                       "ORDER BY length(name) LIMIT 1", (f"{ql}%",))
    if not r:
        r = _rows(con, "SELECT name,latitude,longitude FROM cities "
                       "WHERE lower(name) LIKE ? AND latitude IS NOT NULL "
                       "ORDER BY length(name) LIMIT 1", (f"%{ql}%",))
    if r:
        return (r[0]["latitude"], r[0]["longitude"], r[0]["name"])

    r = _rows(con, "SELECT code,name FROM states "
                   "WHERE lower(name)=? OR lower(code)=? LIMIT 1", (ql, ql))
    if r:
        c = _rows(con, "SELECT AVG(latitude) a, AVG(longitude) b FROM stations "
                       "WHERE state_code=? AND latitude IS NOT NULL", (r[0]["code"],))
        if c and c[0]["a"] is not None:
            return (c[0]["a"], c[0]["b"], r[0]["name"])
    r = _rows(con, "SELECT s.name, c.name AS city_name, s.latitude, s.longitude "
                   "FROM stations s LEFT JOIN cities c ON c.id = s.city_id "
                   "WHERE (lower(s.name) LIKE ? OR lower(s.address) LIKE ? "
                   "       OR lower(c.name) LIKE ?) "
                   "AND s.latitude IS NOT NULL LIMIT 1",
              (f"%{ql}%", f"%{ql}%", f"%{ql}%"))
    if r:
        return (r[0]["latitude"], r[0]["longitude"], r[0]["city_name"] or r[0]["name"])

    return None


def answer(con, query, lat=None, lng=None, place=None):
    q = (query or "").strip()
    ql = q.lower()
    intent = {"type": "unknown", "filters": {}}

    # A caller may hand us a place name instead of coordinates.
    place_label = None
    if (lat is None or lng is None) and place:
        hit = resolve_place(con, place)
        if hit:
            lat, lng, place_label = hit
    filters = {}

    if not q:
        return _help()

    if re.search(r"\b(hi|hello|hey|namaste|help|what can you do)\b", ql) and len(ql.split()) <= 4:
        return _help()

    # --- speed
    for w, s in SPEED_WORDS.items():
        if re.search(rf"\b{re.escape(w)}\b", ql):
            filters["speed"] = s
            break
    # --- connector
    for w, c in CONNECTOR_WORDS.items():
        if w in ql:
            filters["connector"] = c
            break
    # --- payment
    for w, p in PAY_WORDS.items():
        if w in ql:
            filters["payment"] = p
            break
    # --- ownership / location type
    if "private" in ql:
        filters["ownership"] = "Private"
    elif "public" in ql:
        filters["ownership"] = "Public"
    if re.search(r"\b(rural|village|gram panchayat)\b", ql):
        filters["location_type"] = "Village / Rural"
    elif "highway" in ql:
        filters["location_type"] = "Highway"
    elif re.search(r"\b(urban|city|town)\b", ql):
        filters["location_type"] = "Urban"
    if re.search(r"\b24\s*x?\s*7\b|\b24\s*hours?\b|\bopen now\b|\ball night\b", ql):
        filters["is_24x7"] = True

    # --- highway number
    m = re.search(r"\b(nh[\s-]?\d{1,3})\b", ql)
    if m:
        filters["highway"] = "NH-" + re.sub(r"\D", "", m.group(1))

    # --- venue type: where the charger physically is
    for _re_v, _venue in [
        (r"\b(cinemas?|multiplexs?|movies?|inoxs?|pvrs?)\b", "Cinema"),
        (r"\b(malls?|shoppings?|retails?)\b", "Mall / retail"),
        (r"\b(hotels?|resorts?|hospitalitys?|tajs?|marriotts?|itcs?)\b", "Hotel / resort"),
        (r"\b(petrols?|fuels?|pumps?|gas stations?|bpcls?|iocls?|hpcls?|indianoils?)\b", "Petrol station"),
        (r"\b(metros?|airports?|railways?|transits?)\b", "Transit hub"),
        (r"\b(hospitals?)\b", "Hospital"),
        (r"\b(offices?|tech parks?|workplaces?|campuss?)\b", "Office / campus"),
        (r"\b(societys?|residentials?|apartments?|housings?)\b", "Residential / society"),
        (r"\b(restaurants?|cafes?|food courts?)\b", "Restaurant / cafe"),
        (r"\b(parkings?)\b", "Public parking"),
    ]:
        if re.search(_re_v, ql):
            filters["venue"] = _venue
            break

    # --- cheapest
    if re.search(r"\b(cheap|cheapest|lowest price|affordable|budget)\b", ql):
        filters["cheapest"] = True

    # --- nearest / near me
    if re.search(r"\b(nearest|near me|nearby|close to me|around me)\b", ql):
        filters["nearest"] = True

    # --- operator match (full name, or leading tokens like 'tata power')
    ops = [r[0] for r in _rows(con, "SELECT name FROM operators")]
    for o in sorted(ops, key=len, reverse=True):
        ol = o.lower()
        head = " ".join(ol.split()[:2])
        first = ol.split()[0]
        if (ol in ql or (len(head) > 3 and head in ql)
                or (len(first) >= 3 and re.search(rf"\b{re.escape(first)}\b", ql))):
            filters["operator"] = o
            break

    # --- state match
    st = _rows(con, "SELECT code,name FROM states")
    for code, name in st:
        if re.search(rf"\b{re.escape(name.lower())}\b", ql):
            filters["state"] = code
            filters["state_name"] = name
            break

    # --- city match
    cities = [r[0] for r in _rows(con, "SELECT name FROM cities")]
    for c in sorted(cities, key=len, reverse=True):
        if re.search(rf"\b{re.escape(c.lower())}\b", ql):
            filters["city"] = c
            break

    # --- village match
    vils = [r[0] for r in _rows(con, "SELECT DISTINCT village FROM stations WHERE village IS NOT NULL")]
    for v in vils:
        if v.lower() in ql:
            filters["village"] = v
            break

    if not filters:
        # free-text fallback -> name search
        filters["q"] = q
        intent["type"] = "search"
    else:
        intent["type"] = "find"
    intent["filters"] = filters

    # ---- build SQL
    where, args = [], []
    if filters.get("state"):
        where.append("s.state_code = ?"); args.append(filters["state"])
    if filters.get("venue"):
        where.append("s.venue_type = ?"); args.append(filters["venue"])
    if filters.get("city"):
        where.append("c.name = ?"); args.append(filters["city"])
    if filters.get("village"):
        where.append("s.village = ?"); args.append(filters["village"])
    if filters.get("operator"):
        where.append("o.name = ?"); args.append(filters["operator"])
    if filters.get("ownership"):
        where.append("s.ownership = ?"); args.append(filters["ownership"])
    if filters.get("location_type"):
        where.append("s.location_type = ?"); args.append(filters["location_type"])
    if filters.get("is_24x7"):
        where.append("s.is_24x7 = 1")
    if filters.get("highway"):
        where.append("h.number = ?"); args.append(filters["highway"])
    if filters.get("connector"):
        where.append("s.id IN (SELECT station_id FROM connectors WHERE connector_type = ?)")
        args.append(filters["connector"])
    if filters.get("speed"):
        where.append("s.id IN (SELECT station_id FROM connectors WHERE charging_speed = ?)")
        args.append(filters["speed"])
    if filters.get("payment"):
        where.append("s.id IN (SELECT station_id FROM station_payments WHERE method = ?)")
        args.append(filters["payment"])
    if filters.get("q"):
        like = f"%{filters['q']}%"
        where.append("(s.name LIKE ? OR s.address LIKE ? OR o.name LIKE ?)")
        args += [like, like, like]

    sql = """
    SELECT s.id, s.name, s.location_type, s.ownership, s.status, s.latitude, s.longitude,
           s.max_power_kw, s.contact_phone, s.highway_direction, s.village,
           o.name AS operator, c.name AS city, st.name AS state, h.number AS highway,
           (SELECT MIN(price_per_kwh) FROM tariffs t WHERE t.station_id = s.id) AS min_price,
           (SELECT GROUP_CONCAT(DISTINCT connector_type) FROM connectors cn WHERE cn.station_id = s.id) AS connectors
    FROM stations s
    LEFT JOIN operators o ON o.id = s.operator_id
    LEFT JOIN cities c ON c.id = s.city_id
    LEFT JOIN states st ON st.code = s.state_code
    LEFT JOIN highways h ON h.id = s.highway_id
    """
    if where:
        sql += " WHERE " + " AND ".join(where)

    if filters.get("nearest") and lat is not None and lng is not None:
        rows = _rows(con, sql, args)
        scored = []
        for r in rows:
            d = _haversine(lat, lng, r["latitude"], r["longitude"])
            scored.append((d, r))
        scored.sort(key=lambda x: x[0])
        top = scored[:5]
        out = []
        for d, r in top:
            out.append({**_slim(r), "distance_km": round(d, 1)})
        where = f" near {place_label}" if place_label else " to you"
        tail = f" Closest is {out[0]['name']}, {out[0]['distance_km']} km away." if out else ""
        return _respond(intent, out, f"Here are the nearest charging stations{where}.{tail}")

    # "near me" but no coordinates and no resolvable place: ask, don't guess.
    if filters.get("nearest") and lat is None and lng is None:
        return _respond(intent, [],
                        "Tell me where you are and I'll find the closest chargers - "
                        "share your location in the app, or send a city, area or "
                        "6-digit PIN code.")

    if filters.get("cheapest"):
        sql += " ORDER BY min_price ASC NULLS LAST"
    else:
        sql += " ORDER BY s.max_power_kw DESC"
    rows = _rows(con, sql, args)

    # ---- compose answer
    n = len(rows)
    top = [_slim(r) for r in rows[:8]]
    where_txt = _describe(filters)
    if n == 0:
        if where_txt:
            text = f"I couldn't find any stations {where_txt}. Try a nearby city or a broader filter."
        else:
            text = "I couldn't find any stations for that. Try a nearby city or a broader filter."
    else:
        lead = "Here is 1 station" if n == 1 else f"Here are {n} stations"
        text = f"{lead} {where_txt}."
        if len(top) < n:
            text += f" Showing the top {len(top)}."
        if filters.get("cheapest") and rows[0]["min_price"]:
            text += f" Cheapest is {rows[0]['name']} at ₹{rows[0]['min_price']}/kWh."
    return _respond(intent, top, text)


def _slim(r):
    return {
        "id": r["id"], "name": r["name"], "operator": r["operator"], "city": r["city"],
        "state": r["state"], "location_type": r["location_type"], "ownership": r["ownership"],
        "status": r["status"], "max_power_kw": r["max_power_kw"], "min_price": r["min_price"],
        "connectors": (r["connectors"] or "").split(","), "highway": r["highway"],
        "highway_direction": r["highway_direction"], "village": r["village"],
        "contact_phone": r["contact_phone"], "latitude": r["latitude"], "longitude": r["longitude"],
    }


VENUE_PHRASE = {
    "Mall / retail": "at malls and retail sites",
    "Hotel / resort": "at hotels and resorts",
    "Cinema": "at cinemas",
    "Petrol station": "at petrol stations",
    "Transit hub": "at transit hubs",
    "Hospital": "at hospitals",
    "Office / campus": "at offices and campuses",
    "Residential / society": "at residential societies",
    "Restaurant / cafe": "at restaurants and cafes",
    "Public parking": "at public parking",
}


def _describe(f):
    parts = []
    if f.get("speed"):
        parts.append(f"{f['speed'].lower()}-charging")
    if f.get("connector"):
        parts.append(f"{f['connector']} connector")
    if f.get("city"):
        parts.append(f"in {f['city']}")
    if f.get("state") and not f.get("city"):
        parts.append(f"in {f.get('state_name', f['state'])}")
    if f.get("village"):
        parts.append(f"in {f['village']}")
    if f.get("highway"):
        parts.append(f"on {f['highway']}")
    if f.get("operator"):
        parts.append(f"operated by {f['operator']}")
    if f.get("ownership"):
        parts.append(f"{f['ownership'].lower()} stations")
    if f.get("location_type"):
        parts.append(f"{f['location_type'].lower()} locations")
    if f.get("payment"):
        parts.append(f"accepting {f['payment']}")
    if f.get("is_24x7"):
        parts.append("open 24x7")
    if f.get("venue"):
        parts.append(VENUE_PHRASE.get(f["venue"], "at " + f["venue"].lower()))
    if f.get("nearest"):
        parts.append("near you")
    if f.get("q"):
        parts.append(f"matching '{f['q']}'")
    return " ".join(parts) if parts else "your query"


def _respond(intent, stations, text):
    return {"intent": intent, "answer": text, "stations": stations, "count": len(stations)}


def _help():
    return {
        "intent": {"type": "help", "filters": {}},
        "answer": ("I can find EV charging stations by city, state, village, highway, operator, "
                   "connector type (CCS2, CHAdeMO, Type 2, Bharat AC/DC), charging speed "
                   "(normal, fast, turbo), payment method, public/private, and 24x7. "
                   "Try: 'turbo chargers on NH-48', 'cheapest charging in Jaipur', "
                   "'CCS2 stations in Pune that accept UPI', or 'nearest station'."),
        "stations": [], "count": 0,
    }
