#!/usr/bin/env python3
"""
Open Charge Map source adapter.

Endpoint
    GET https://api.openchargemap.io/v3/poi/
    ?countrycode=IN&maxresults=5000&compact=true&verbose=false[&key=...]

Unlike the e-AMRIT register (an Indian government host that blocks non-Indian
datacentre IPs), Open Charge Map is a globally hosted open-data service, so it is
reachable from CI runners anywhere. That makes it the dependable live source.

An API key is optional for light use. Set OCM_API_KEY in the environment to send
one - recommended, and it keeps you inside the fair-use policy.

Data quality note: Open Charge Map is community-contributed and sparse in India.
Treat its records as additive, not authoritative, and keep the `DataProvider`
attribution that comes with them.
"""
import json
import os
import urllib.parse
import urllib.request

ENDPOINT = "https://api.openchargemap.io/v3/poi/"
SOURCE_ID = "ocm"
SOURCE_LABEL = "Open Charge Map (IN)"

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
}


def fetch(maxresults=5000, timeout=45):
    """Live pull from Open Charge Map. Raises on failure."""
    params = {
        "output": "json",
        "countrycode": "IN",
        "maxresults": str(maxresults),
        "compact": "true",
        "verbose": "false",
        "client": "EVChargeIndia/1.0",
    }
    key = os.environ.get("OCM_API_KEY", "").strip()
    if key:
        params["key"] = key
    url = ENDPOINT + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": "EVChargeIndia/1.0 (pipeline)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data if isinstance(data, list) else []


def get_records():
    """Returns (records, mode). No snapshot fallback - a failure is reported."""
    return fetch(), "live"


def _speed_for(kw):
    if kw is None:
        return None
    if kw < 22:
        return "Normal"
    if kw < 100:
        return "Fast"
    return "Turbo"


def normalise(raw):
    """Map one Open Charge Map POI onto the canonical station dict."""
    addr = raw.get("AddressInfo") or {}
    op = raw.get("OperatorInfo") or {}
    conns = raw.get("Connections") or []

    lat, lng = addr.get("Latitude"), addr.get("Longitude")
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        lat = lng = None

    title = (addr.get("Title") or raw.get("AddressInfo", {}).get("AddressLine1") or "").strip()
    town = (addr.get("Town") or "").strip()
    state = (addr.get("StateOrProvince") or "").strip()

    # connectors
    out_conns = []
    max_kw = 0.0
    total_kw = 0.0
    for c in conns:
        ct = ((c.get("ConnectionType") or {}).get("Title") or "Unknown").strip()
        kw = c.get("PowerKW") or 0
        qty = c.get("Quantity") or 1
        current = "DC" if (c.get("CurrentType") or {}).get("ID") == 30 else "AC"
        out_conns.append(dict(type=ct, formal=ct, current=current, power_kw=kw,
                              speed=_speed_for(kw), qty=qty))
        max_kw = max(max_kw, kw or 0)
        total_kw += (kw or 0) * (qty or 1)

    status = ((raw.get("StatusType") or {}).get("Title") or "Unknown").strip()
    status = "Operational" if "operational" in status.lower() else status

    usage = (raw.get("UsageCost") or "").strip()

    return {
        "name": title or f"Charging point {raw.get('ID')}",
        "operator": (op.get("Title") or "Unknown operator").strip(),
        "ownership": "Public",
        "access": "Public access",
        "location_type": "Urban",
        "state_code": STATE_CODES.get(state.lower(), "DL"),
        "city": town or None,
        "district": None,
        "panchayat": None,
        "village": None,
        "address": ", ".join(x for x in [addr.get("AddressLine1"), town, state,
                                         addr.get("Postcode")] if x),
        "highway": None,
        "highway_direction": None,
        "latitude": lat,
        "longitude": lng,
        "contact_phone": (addr.get("ContactTelephone1")
                          or op.get("PhonePrimaryContact") or None),
        "contact_email": addr.get("ContactEmail") or None,
        "operating_hours": "Not reported",
        "is_24x7": 0,
        "status": status,
        "num_chargers": raw.get("NumberOfPoints") or len(out_conns) or None,
        "total_capacity_kw": round(total_kw, 1) or None,
        "max_power_kw": max_kw or None,
        "amenities": [],
        "connectors": out_conns,
        "usage_cost": usage or None,
        "data_source": f"Open Charge Map ({(raw.get('DataProvider') or {}).get('Title') or 'community'})",
        "source_id": SOURCE_ID,
        "source_ref": str(raw.get("ID") or ""),
        "is_validated": 0,
        "coord_precision": "exact" if lat is not None else None,
        "operator_website": op.get("WebsiteURL") or None,
    }


if __name__ == "__main__":
    recs, mode = get_records()
    print(f"mode={mode} records={len(recs)}")
    for r in recs[:3]:
        n = normalise(r)
        print(f"  [{n['source_ref']}] {n['name']} | {n['city']}, {n['state_code']} | "
              f"{len(n['connectors'])} connectors")
