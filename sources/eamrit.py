#!/usr/bin/env python3
"""
e-AMRIT (NITI Aayog) source adapter.

Endpoint
    GET https://e-amrit.niti.gov.in/getChargingStation
    Returns a JSON array. No API key. No documented pagination - the whole
    list comes back in one response.

What the feed gives you (observed field set):
    stationid, name, address, city, state, pincode,
    lattitude (sic), longitude, availability, isValidated, pricing,
    contact, phones, issue, type, notes

Field notes worth knowing before you build on it:
  * `isValidated` is the verified flag - "1" means the station has been
    validated. Carry it through; it is the whole reason to use this source.
  * The coordinate key is misspelled `lattitude` in the source. Handle both.
  * `pricing` is free text ("free" or a rate string), not a number.
  * This endpoint carries NO connector data - no connector type, no power,
    no quantity. Connectors stay empty from this source; merge with the
    BEE charger-level dataset (charger_type / charger_rating / connector
    rating) to fill them.
  * Data quality is uneven: some records have pincode "0", and some have a
    name that does not match the address (see stationid 26/27/31 in the
    sample). Validate before publishing.

Live fetch needs outbound HTTPS. Where the network is unavailable the
adapter falls back to a checked-in snapshot so the pipeline still runs.
"""
import json
import os
import urllib.request

ENDPOINT = "https://e-amrit.niti.gov.in/getChargingStation"
SNAPSHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshot_eamrit.json")
SOURCE_ID = "eamrit"
SOURCE_LABEL = "e-AMRIT (NITI Aayog / BEE)"

# state name -> our state code
STATE_CODES = {
    "andhra pradesh": "AP", "arunachal pradesh": "AR", "assam": "AS", "bihar": "BR",
    "chhattisgarh": "CG", "goa": "GA", "gujarat": "GJ", "haryana": "HR",
    "himachal pradesh": "HP", "jharkhand": "JH", "karnataka": "KA", "kerala": "KL",
    "madhya pradesh": "MP", "maharashtra": "MH", "manipur": "MN", "meghalaya": "ML",
    "mizoram": "MZ", "nagaland": "NL", "odisha": "OD", "punjab": "PB",
    "rajasthan": "RJ", "sikkim": "SK", "tamil nadu": "TN", "telangana": "TS",
    "tripura": "TR", "uttar pradesh": "UP", "uttarakhand": "UK", "west bengal": "WB",
    "delhi": "DL", "jammu & kashmir": "JK", "jammu and kashmir": "JK",
    "ladakh": "LA", "puducherry": "PY", "chandigarh": "CH",
    "andaman & nicobar": "AN", "andaman and nicobar islands": "AN",
    "dadra and nagar haveli and daman and diu": "DN", "lakshadweep": "LD",
}

# operator detection from the station name prefix
OPERATOR_HINTS = [
    ("ANERT", "ANERT (Agency for Non-conventional Energy)"),
    ("HAREDA", "HAREDA (Haryana Renewable Energy)"),
    ("EESL", "EESL (Energy Efficiency Services Ltd)"),
    ("TATA", "Tata Power EZ Charge"),
    ("STATIQ", "Statiq"),
    ("CHARGEZONE", "ChargeZone"),
    ("JIO", "Jio-bp pulse"),
]


def fetch(timeout=30):
    """Live pull. Raises on network failure - caller decides on fallback."""
    req = urllib.request.Request(
        ENDPOINT,
        headers={"User-Agent": "EVChargeIndia/1.0 (pipeline)", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def load_snapshot():
    """Offline fallback: the checked-in real sample of the same feed."""
    with open(SNAPSHOT, encoding="utf-8") as f:
        return json.load(f)


def get_records(allow_snapshot=True):
    """Fetch live, or fall back to the snapshot when the network is unavailable.

    Returns (records, mode) where mode is 'live' or 'snapshot'.
    """
    try:
        return fetch(), "live"
    except Exception:
        if not allow_snapshot:
            raise
        return load_snapshot(), "snapshot"


def _detect_operator(name):
    up = (name or "").upper()
    for hint, label in OPERATOR_HINTS:
        if hint in up:
            return label
    return "EESL (Energy Efficiency Services Ltd)"


def _state_code(state_name):
    return STATE_CODES.get((state_name or "").strip().lower(), "DL")


def normalise(raw):
    """Map one e-AMRIT record to the canonical station dict the DB expects."""
    lat = raw.get("lattitude", raw.get("latitude"))
    lng = raw.get("longitude")
    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        lat = lng = None

    name = (raw.get("name") or "").strip()
    address = (raw.get("address") or "").strip()
    city = (raw.get("city") or "").strip()
    state = (raw.get("state") or "").strip()
    pincode = (raw.get("pincode") or "").strip()
    if pincode == "0":
        pincode = ""

    pricing = (raw.get("pricing") or "").strip().lower()
    free = pricing == "free"

    avail = raw.get("availability")
    status = "Operational" if str(avail) in ("1", "True", "true") else "Unknown"

    validated = 1 if str(raw.get("isValidated")) == "1" else 0

    full_address = address or name
    if city and city.lower() not in full_address.lower():
        full_address = f"{full_address}, {city}"
    if state and state.lower() not in full_address.lower():
        full_address = f"{full_address}, {state}"
    if pincode:
        full_address = f"{full_address} - {pincode}"

    gmaps = (f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"
             if lat is not None else None)
    amaps = (f"https://maps.apple.com/?ll={lat},{lng}&q={name.replace(' ', '+')}"
             if lat is not None else None)

    return {
        "name": name,
        "operator": _detect_operator(name),
        "ownership": "Public",                       # e-AMRIT is a government register
        "access": "Public access",
        "location_type": "Urban",                    # not provided; refine with the BEE dataset
        "state_code": _state_code(state),
        "city": city,
        "district": None,                            # not provided by this endpoint
        "panchayat": None,
        "village": None,
        "address": full_address,
        "highway": None,
        "highway_direction": None,
        "latitude": lat,
        "longitude": lng,
        "contact_phone": (raw.get("phones") or raw.get("contact") or "").strip() or None,
        "contact_email": None,
        "operating_hours": "Not reported",
        "is_24x7": 0,
        "status": status,
        "num_chargers": None,                        # not provided
        "total_capacity_kw": None,
        "max_power_kw": None,
        "amenities": [],
        "google_maps_url": gmaps,
        "apple_maps_url": amaps,
        "tariff_price_per_kwh": 0.0 if free else None,
        "data_source": SOURCE_LABEL,
        "source_id": SOURCE_ID,
        "source_ref": str(raw.get("stationid") or ""),
        "is_validated": validated,
    }


if __name__ == "__main__":
    recs, mode = get_records()
    print(f"mode={mode} records={len(recs)}")
    for r in recs[:3]:
        n = normalise(r)
        print(f"  [{n['source_ref']}] {n['name']} | {n['city']}, {n['state_code']} | "
              f"validated={n['is_validated']} | {n['latitude']},{n['longitude']}")
