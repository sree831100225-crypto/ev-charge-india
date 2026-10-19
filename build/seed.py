#!/usr/bin/env python3
"""
EV Charge India - database schema + realistic seed dataset generator.

Builds:
  - ev_charge_india.db   (SQLite, full relational schema)
  - stations.json        (flattened export consumed by the PWA prototype)

NOTE: The station records are SYNTHETIC seed data, generated to be
realistic in structure, geography, operator mix, connector mix, tariffs
and payment methods. They are labelled as sample data and are NOT a
verified live registry. The schema and pipeline are built to ingest real
sources (Open Charge Map, DISCOM registers, operator feeds) unchanged.
"""
import json
import math
import os
import random
import sqlite3
from datetime import datetime, timedelta, timezone

random.seed(20261019)

# Repo root = the parent of this script's directory. Keeps the pipeline portable
# between the sandbox and CI (GitHub Actions).
OUT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(OUT_DIR, "ev_charge_india.db")
JSON_PATH = os.path.join(OUT_DIR, "stations.json")

# ---------------------------------------------------------------------------
# REFERENCE DATA
# ---------------------------------------------------------------------------

STATES = {
    "DL": "Delhi", "MH": "Maharashtra", "KA": "Karnataka", "TS": "Telangana",
    "TN": "Tamil Nadu", "WB": "West Bengal", "GJ": "Gujarat", "RJ": "Rajasthan",
    "UP": "Uttar Pradesh", "MP": "Madhya Pradesh", "BR": "Bihar", "HR": "Haryana",
    "PB": "Punjab", "KL": "Kerala", "OD": "Odisha", "AP": "Andhra Pradesh",
    "JH": "Jharkhand", "CG": "Chhattisgarh", "UK": "Uttarakhand", "HP": "Himachal Pradesh",
    "GA": "Goa", "AS": "Assam", "JK": "Jammu & Kashmir", "CH": "Chandigarh",
}

# city -> (state_code, district, lat, lng, tier)
CITIES = [
    ("New Delhi", "DL", "New Delhi", 28.6139, 77.2090, 1),
    ("Mumbai", "MH", "Mumbai Suburban", 19.0760, 72.8777, 1),
    ("Bengaluru", "KA", "Bengaluru Urban", 12.9716, 77.5946, 1),
    ("Hyderabad", "TS", "Hyderabad", 17.3850, 78.4867, 1),
    ("Chennai", "TN", "Chennai", 13.0827, 80.2707, 1),
    ("Kolkata", "WB", "Kolkata", 22.5726, 88.3639, 1),
    ("Pune", "MH", "Pune", 18.5204, 73.8567, 1),
    ("Ahmedabad", "GJ", "Ahmedabad", 23.0225, 72.5714, 1),
    ("Jaipur", "RJ", "Jaipur", 26.9124, 75.7873, 1),
    ("Surat", "GJ", "Surat", 21.1702, 72.8311, 2),
    ("Lucknow", "UP", "Lucknow", 26.8467, 80.9462, 1),
    ("Kanpur", "UP", "Kanpur Nagar", 26.4499, 80.3319, 2),
    ("Nagpur", "MH", "Nagpur", 21.1458, 79.0882, 2),
    ("Indore", "MP", "Indore", 22.7196, 75.8577, 2),
    ("Bhopal", "MP", "Bhopal", 23.2599, 77.4126, 2),
    ("Patna", "BR", "Patna", 25.5941, 85.1376, 2),
    ("Vadodara", "GJ", "Vadodara", 22.3072, 73.1812, 2),
    ("Ludhiana", "PB", "Ludhiana", 30.9010, 75.8573, 2),
    ("Agra", "UP", "Agra", 27.1767, 78.0081, 2),
    ("Nashik", "MH", "Nashik", 19.9975, 73.7898, 2),
    ("Varanasi", "UP", "Varanasi", 25.3176, 82.9739, 2),
    ("Amritsar", "PB", "Amritsar", 31.6340, 74.8723, 2),
    ("Prayagraj", "UP", "Prayagraj", 25.4358, 81.8463, 2),
    ("Ranchi", "JH", "Ranchi", 23.3441, 85.3096, 2),
    ("Coimbatore", "TN", "Coimbatore", 11.0168, 76.9558, 2),
    ("Jabalpur", "MP", "Jabalpur", 23.1815, 79.9864, 2),
    ("Gwalior", "MP", "Gwalior", 26.2183, 78.1828, 2),
    ("Vijayawada", "AP", "Krishna", 16.5062, 80.6480, 2),
    ("Jodhpur", "RJ", "Jodhpur", 26.2389, 73.0243, 2),
    ("Madurai", "TN", "Madurai", 9.9252, 78.1198, 2),
    ("Raipur", "CG", "Raipur", 21.2514, 81.6296, 2),
    ("Kota", "RJ", "Kota", 25.2138, 75.8648, 3),
    ("Guwahati", "AS", "Kamrup Metropolitan", 26.1445, 91.7362, 2),
    ("Chandigarh", "CH", "Chandigarh", 30.7333, 76.7794, 2),
    ("Mysuru", "KA", "Mysuru", 12.2958, 76.6394, 3),
    ("Bareilly", "UP", "Bareilly", 28.3670, 79.4304, 3),
    ("Tiruchirappalli", "TN", "Tiruchirappalli", 10.7905, 78.7047, 3),
    ("Kochi", "KL", "Ernakulam", 9.9312, 76.2673, 2),
    ("Thiruvananthapuram", "KL", "Thiruvananthapuram", 8.5241, 76.9366, 2),
    ("Bhubaneswar", "OD", "Khordha", 20.2961, 85.8245, 2),
    ("Dehradun", "UK", "Dehradun", 30.3165, 78.0322, 3),
    ("Shimla", "HP", "Shimla", 31.1048, 77.1734, 3),
    ("Panaji", "GA", "North Goa", 15.4909, 73.8278, 3),
    ("Visakhapatnam", "AP", "Visakhapatnam", 17.6868, 83.2185, 2),
    ("Aurangabad", "MH", "Aurangabad", 19.8762, 75.3433, 3),
    ("Meerut", "UP", "Meerut", 28.9845, 77.7064, 3),
    ("Rajkot", "GJ", "Rajkot", 22.3039, 70.8022, 3),
    ("Srinagar", "JK", "Srinagar", 34.0837, 74.7973, 3),
    ("Jalandhar", "PB", "Jalandhar", 31.3260, 75.5762, 3),
    ("Gorakhpur", "UP", "Gorakhpur", 26.7606, 83.3732, 3),
    ("Noida", "UP", "Gautam Buddha Nagar", 28.5355, 77.3910, 2),
    ("Gurugram", "HR", "Gurugram", 28.4595, 77.0266, 1),
]

# highway corridors: (number, name, from_city, to_city)
HIGHWAYS = [
    ("NH-48", "Delhi - Mumbai Expressway corridor", "New Delhi", "Mumbai"),
    ("NH-44", "North-South Corridor (Srinagar - Kanyakumari)", "New Delhi", "Bengaluru"),
    ("NH-19", "Delhi - Kolkata (Grand Trunk Road)", "New Delhi", "Kolkata"),
    ("NH-16", "Kolkata - Chennai (East Coast Road)", "Kolkata", "Chennai"),
    ("NH-66", "Panvel - Kanyakumari (West Coast)", "Mumbai", "Kochi"),
    ("NH-27", "Porbandar - Silchar (East-West Corridor)", "Ahmedabad", "Guwahati"),
    ("NH-30", "Chennai - Bengaluru", "Chennai", "Bengaluru"),
    ("NH-52", "Jaipur - Agra", "Jaipur", "Agra"),
    ("NH-75", "Bengaluru - Mangaluru", "Bengaluru", "Mysuru"),
    ("NH-34", "Delhi - Lucknow", "New Delhi", "Lucknow"),
]

# operators: (name, kind, website, phone, email, dc_price, ac_price, dc_share)
OPERATORS = [
    ("Tata Power EZ Charge", "Charging network", "https://www.tatapower.com/ezcharge", "1800-209-5161", "ezcharge@tatapower.com", 18.0, 12.0, 0.85),
    ("Statiq", "Charging network", "https://statiq.in", "1800-419-0133", "support@statiq.in", 18.0, 15.0, 0.80),
    ("ChargeZone", "Charging network", "https://www.chargezone.in", "1800-572-7827", "care@chargezone.in", 22.0, 16.0, 0.95),
    ("Jio-bp pulse", "Charging network", "https://www.jiobp.com/pulse", "1800-890-9393", "pulse@jiobp.com", 20.0, 15.0, 0.90),
    ("Zeon Charging", "Charging network", "https://www.zeoncharging.com", "1800-121-9090", "support@zeoncharging.com", 19.0, 14.0, 0.88),
    ("GLIDA (Fortum)", "Charging network", "https://glida.in", "1800-102-6262", "care@glida.in", 20.0, 15.0, 0.85),
    ("Relux Electric", "Charging network", "https://reluxelectric.com", "1800-570-0909", "hello@reluxelectric.com", 19.5, 14.5, 0.82),
    ("Shell Recharge", "Charging network", "https://www.shell.in/recharge", "1800-209-4499", "recharge@shell.com", 23.0, 17.0, 0.90),
    ("BPCL", "Oil company", "https://www.bharatpetroleum.in", "1800-222-434", "charge@bpcl.in", 17.0, 14.0, 0.70),
    ("IndianOil", "Oil company", "https://www.iocl.com", "1800-233-3555", "evcare@indianoil.in", 16.5, 13.5, 0.60),
    ("HP eCharge", "Oil company", "https://www.hindustanpetroleum.com/pages/ev-charging", "1800-233-3522", "evcharge@hpcl.in", 17.5, 14.0, 0.65),
    ("EESL", "Public sector", "https://eeslindia.org", "1800-11-9103", "ev@eeslindia.org", 15.0, 12.0, 0.55),
    ("NTPC", "Public sector", "https://www.ntpc.co.in", "1800-180-6080", "ev@ntpc.co.in", 16.0, 13.0, 0.60),
    ("BESCOM EV Mitra", "Electricity board", "https://bescom.karnataka.gov.in", "1912", "evmitra@bescom.co.in", 15.5, 11.0, 0.50),
    ("KSEB", "Electricity board", "https://kseb.in", "1912", "ev@kseb.in", 15.0, 11.5, 0.45),
    ("MSEDCL PowerUp", "Electricity board", "https://www.mahadiscom.in", "1912", "ev@mahadiscom.in", 15.5, 12.0, 0.50),
    ("GMR", "Charging network", "https://www.gmrgroup.in", "1800-102-9090", "care@gmrgroup.in", 16.5, 15.0, 0.80),
    ("GoEgo", "Charging network", "https://goego.network", "1800-120-6688", "support@goego.network", 20.0, 17.0, 0.75),
    ("Kazam", "Two-wheeler network", "https://kazam.in", "1800-102-1777", "support@kazam.in", 18.0, 13.0, 0.30),
    ("Ather Grid", "Two-wheeler network", "https://www.atherenergy.com", "1800-103-0303", "grid@atherenergy.com", 0.0, 16.0, 0.05),
    ("Ola Hypercharger", "Two-wheeler network", "https://www.olaelectric.com", "1800-103-0456", "hypercharger@olaelectric.com", 0.0, 17.0, 0.10),
    ("Fortum Charge & Drive", "Charging network", "https://www.fortum.in", "1800-102-6262", "charge@fortum.in", 19.5, 15.0, 0.88),
    ("chargeMOD", "Charging network", "https://chargemod.com", "1800-889-0200", "support@chargemod.com", 21.0, 18.0, 0.85),
    ("ePlug", "Charging network", "https://eplug.in", "1800-121-1111", "care@eplug.in", 20.0, 16.0, 0.80),
]

# connector type -> (formal, current, typical_kw_list)
CONNECTOR_TYPES = {
    "CCS2": ("IEC 62196-3 CCS Combo 2", "DC", [50, 60, 120, 150, 180, 240]),
    "CHAdeMO": ("CHAdeMO (IEC 62196-3)", "DC", [50, 62.5]),
    "Type 2 AC": ("IEC 62196-2 Type 2 (Mennekes)", "AC", [7.4, 11, 22]),
    "Type 1 AC": ("SAE J1772 Type 1", "AC", [3.3, 7.4]),
    "Bharat DC-001": ("Bharat DC-001 (GB/T based)", "DC", [15]),
    "Bharat AC-001": ("Bharat AC-001 (3 x 3.3 kW)", "AC", [10]),
    "GB/T": ("GB/T 20234", "DC", [15, 60]),
}

PAYMENTS = ["UPI", "Credit/Debit Card", "Net Banking", "In-app Wallet", "RFID Card", "QR Code"]
AMENITIES = ["Restroom", "Cafe / Food Court", "Parking", "Shopping", "ATM", "WiFi",
             "Rest Area", "Convenience Store", "CCTV", "Wheelchair Accessible",
             "24x7 Security", "Kids Play Area"]

# named sample villages for panchayat-level entries
VILLAGES = [
    ("Bilaspur", "Gurugram"), ("Manesar", "Gurugram"), ("Kherki Daula", "Gurugram"),
    ("Shahpura", "Jaipur"), ("Bassi", "Jaipur"), ("Dudu", "Jaipur"),
    ("Khed Shivapur", "Pune"), ("Talegaon", "Pune"), ("Urse", "Pune"),
    ("Hoskote", "Bengaluru Urban"), ("Nelamangala", "Bengaluru Rural"),
    ("Bidadi", "Ramanagara"), ("Chikkaballapur", "Chikkaballapur"),
    ("Vadape", "Thane"), ("Khalapur", "Raigad"), ("Panvel", "Raigad"),
    ("Sanand", "Ahmedabad"), ("Bavla", "Ahmedabad"), ("Bagodara", "Ahmedabad"),
    ("Choryasi", "Surat"), ("Kamrej", "Surat"), ("Palsana", "Surat"),
    ("Jewar", "Gautam Buddha Nagar"), ("Dankaur", "Gautam Buddha Nagar"),
    ("Bharthana", "Etawah"), ("Phagwara", "Kapurthala"), ("Bilga", "Jalandhar"),
    ("Kotputli", "Jaipur"), ("Behror", "Alwar"), ("Shahjahanpur", "Alwar"),
]

LOCATION_TYPES = ["Urban", "Highway", "Village / Rural"]
OWNERSHIP = ["Public", "Private"]

SPEED_BUCKETS = [
    (22, "Normal"),      # < 22 kW
    (100, "Fast"),       # 22 - 99 kW
    (10_000, "Turbo"),   # >= 100 kW
]


def speed_for(kw):
    for ceiling, label in SPEED_BUCKETS:
        if kw < ceiling:
            return label
    return "Turbo"


def jitter(lat, lng, km=6.0):
    """Random offset within ~km kilometres."""
    dlat = (random.random() - 0.5) * (km / 111.0) * 2
    dlng = (random.random() - 0.5) * (km / (111.0 * max(0.3, math.cos(math.radians(lat))))) * 2
    return round(lat + dlat, 6), round(lng + dlng, 6)


def interp(a, b, t):
    return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t


CITY_COORD = {c[0]: (c[3], c[4]) for c in CITIES}
CITY_STATE = {c[0]: c[1] for c in CITIES}
CITY_DISTRICT = {c[0]: c[2] for c in CITIES}
CITY_TIER = {c[0]: c[5] for c in CITIES}

now = datetime.now(timezone.utc)


def iso(dt):
    return dt.replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# SCHEMA
# ---------------------------------------------------------------------------

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE states (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE districts (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    state_code TEXT NOT NULL REFERENCES states(code)
);

CREATE TABLE cities (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    district_id INTEGER REFERENCES districts(id),
    state_code TEXT NOT NULL REFERENCES states(code),
    tier INTEGER,
    latitude REAL,
    longitude REAL
);

CREATE TABLE highways (
    id INTEGER PRIMARY KEY,
    number TEXT NOT NULL,
    name TEXT
);

CREATE TABLE operators (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    kind TEXT,
    website TEXT,
    phone TEXT,
    email TEXT,
    dc_price_per_kwh REAL,
    ac_price_per_kwh REAL
);

CREATE TABLE stations (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    operator_id INTEGER REFERENCES operators(id),
    ownership TEXT NOT NULL,              -- Public | Private
    access TEXT,                          -- Public access | Restricted (fleet/hotel)
    location_type TEXT NOT NULL,          -- Urban | Highway | Village / Rural
    state_code TEXT REFERENCES states(code),
    district_id INTEGER REFERENCES districts(id),
    city_id INTEGER REFERENCES cities(id),
    panchayat TEXT,
    village TEXT,
    address TEXT,
    highway_id INTEGER REFERENCES highways(id),
    highway_direction TEXT,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    contact_phone TEXT,
    contact_email TEXT,
    operating_hours TEXT,
    is_24x7 INTEGER DEFAULT 0,
    status TEXT,                          -- Operational | Under maintenance | Coming soon
    num_chargers INTEGER,
    total_capacity_kw REAL,
    max_power_kw REAL,
    amenities TEXT,                       -- json array
    google_maps_url TEXT,
    apple_maps_url TEXT,
    data_source TEXT,
    source_id TEXT DEFAULT 'seed',        -- 'seed' | 'eamrit' | ...
    source_ref TEXT,                       -- the source's own id for this record
    is_validated INTEGER DEFAULT 0,        -- 1 = confirmed by a government register
    coord_precision TEXT,                  -- exact | area | town  (how tight the lat/lng is)
    last_updated TEXT,
    created_at TEXT
);

CREATE TABLE connectors (
    id INTEGER PRIMARY KEY,
    station_id INTEGER NOT NULL REFERENCES stations(id),
    connector_type TEXT NOT NULL,
    formal_name TEXT,
    current_type TEXT,                    -- AC | DC
    power_kw REAL,
    charging_speed TEXT,                  -- Normal | Fast | Turbo
    quantity INTEGER,
    status TEXT
);

CREATE TABLE tariffs (
    id INTEGER PRIMARY KEY,
    station_id INTEGER NOT NULL REFERENCES stations(id),
    connector_type TEXT,
    price_per_kwh REAL,
    session_fee REAL DEFAULT 0,
    idle_fee_per_min REAL DEFAULT 0,
    currency TEXT DEFAULT 'INR',
    notes TEXT
);

CREATE TABLE brands (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    aliases TEXT,                          -- other names the brand appears under
    segment TEXT,                          -- Two-wheeler | Car | Luxury car
    operates_network INTEGER DEFAULT 0,    -- 1 = runs its own public charging network
    network_name TEXT,
    network_scale TEXT,                    -- verified size, as published
    connector_standard TEXT,
    partnership TEXT,                      -- charging partner, when it has no network of its own
    app TEXT,
    website TEXT,
    notes TEXT,
    source TEXT,
    verified INTEGER DEFAULT 0
);

CREATE TABLE station_payments (
    station_id INTEGER NOT NULL REFERENCES stations(id),
    method TEXT NOT NULL
);

CREATE TABLE refresh_log (
    id INTEGER PRIMARY KEY,
    started_at TEXT,
    finished_at TEXT,
    source TEXT,
    records_seen INTEGER,
    records_created INTEGER,
    records_updated INTEGER,
    status TEXT,
    notes TEXT
);

CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    mobile TEXT UNIQUE NOT NULL,
    name TEXT,
    email TEXT,
    vehicle TEXT,
    created_at TEXT,
    last_login TEXT
);

CREATE TABLE sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    created_at TEXT,
    expires_at TEXT
);

CREATE INDEX idx_stations_state ON stations(state_code);
CREATE INDEX idx_stations_city ON stations(city_id);
CREATE INDEX idx_stations_type ON stations(location_type);
CREATE INDEX idx_stations_operator ON stations(operator_id);
CREATE INDEX idx_connectors_station ON connectors(station_id);
CREATE INDEX idx_tariffs_station ON tariffs(station_id);
CREATE INDEX idx_payments_station ON station_payments(station_id);
"""


def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    cur = con.cursor()

    # --- states
    for code, name in STATES.items():
        cur.execute("INSERT INTO states(code,name) VALUES(?,?)", (code, name))

    # --- districts + cities
    dist_id = {}
    for city, st, dist, lat, lng, tier in CITIES:
        key = (dist, st)
        if key not in dist_id:
            cur.execute("INSERT INTO districts(name,state_code) VALUES(?,?)", (dist, st))
            dist_id[key] = cur.lastrowid
    city_id = {}
    for city, st, dist, lat, lng, tier in CITIES:
        cur.execute(
            "INSERT INTO cities(name,district_id,state_code,tier,latitude,longitude) VALUES(?,?,?,?,?,?)",
            (city, dist_id[(dist, st)], st, tier, lat, lng),
        )
        city_id[city] = cur.lastrowid

    # --- highways
    hw_id = {}
    for num, name, a, b in HIGHWAYS:
        cur.execute("INSERT INTO highways(number,name) VALUES(?,?)", (num, name))
        hw_id[num] = cur.lastrowid

    # --- operators
    op_id = {}
    op_meta = {}
    for name, kind, web, phone, email, dcp, acp, dcs in OPERATORS:
        cur.execute(
            "INSERT INTO operators(name,kind,website,phone,email,dc_price_per_kwh,ac_price_per_kwh) VALUES(?,?,?,?,?,?,?)",
            (name, kind, web, phone, email, dcp, acp),
        )
        op_id[name] = cur.lastrowid
        op_meta[name] = dict(kind=kind, web=web, phone=phone, email=email, dcp=dcp, acp=acp, dcs=dcs)

    stations_out = []
    station_seq = 0

    def add_station(*, name, operator, ownership, location_type, city, lat, lng,
                    highway=None, direction=None, village=None, panchayat=None,
                    address=None, access=None):
        nonlocal station_seq
        station_seq += 1
        sid = station_seq
        st = CITY_STATE.get(city, "DL")
        dist = CITY_DISTRICT.get(city, "New Delhi")
        cid = city_id.get(city)
        did = dist_id.get((dist, st))
        hwid = hw_id.get(highway) if highway else None
        m = op_meta[operator]

        # connectors
        n_conn = random.randint(1, 4)
        conns = []
        has_dc = random.random() < m["dcs"]
        if location_type == "Highway":
            has_dc = random.random() < 0.95
        # pick connector types
        pool = []
        if has_dc:
            pool += ["CCS2", "CCS2", "CHAdeMO", "Bharat DC-001", "GB/T"]
        else:
            pool += ["Type 2 AC", "Bharat AC-001", "Type 1 AC"]
        chosen = random.sample(pool, k=min(n_conn, len(pool)))
        max_kw = 0
        total_kw = 0
        for ct in chosen:
            formal, current, kws = CONNECTOR_TYPES[ct]
            kw = random.choice(kws)
            # turbo only on highways / big city hubs
            if kw >= 100 and location_type != "Highway" and random.random() < 0.6:
                kw = random.choice([50, 60])
            qty = random.choice([1, 1, 1, 2, 3])
            conns.append(dict(ct=ct, formal=formal, current=current, kw=kw,
                              speed=speed_for(kw), qty=qty))
            max_kw = max(max_kw, kw)
            total_kw += kw * qty
        # ensure at least one connector
        if not conns:
            formal, current, kws = CONNECTOR_TYPES["Type 2 AC"]
            kw = random.choice(kws)
            conns.append(dict(ct="Type 2 AC", formal=formal, current=current,
                              kw=kw, speed=speed_for(kw), qty=1))
            max_kw = kw
            total_kw = kw

        # tariffs
        dcp, acp = m["dcp"], m["acp"]
        tariffs = []
        for c in conns:
            if c["current"] == "DC":
                base = dcp if dcp else 18.0
            else:
                base = acp if acp else 14.0
            price = round(base + random.choice([-1.5, -1.0, -0.5, 0, 0, 0.5, 1.0, 1.5]), 2)
            price = max(9.0, price)
            tariffs.append(dict(ct=c["ct"], price=price,
                                session_fee=random.choice([0, 0, 0, 20, 50]),
                                idle_fee=random.choice([0, 0, 2, 4])))
        # one tariff per connector type (dedupe)
        seen = set()
        uniq_tariffs = []
        for t in tariffs:
            if t["ct"] in seen:
                continue
            seen.add(t["ct"])
            uniq_tariffs.append(t)
        tariffs = uniq_tariffs

        # payments
        pays = set(random.sample(PAYMENTS, k=random.randint(3, 5)))
        pays.add("UPI")  # UPI is near-universal
        pays = sorted(pays)

        # amenities
        amen = sorted(random.sample(AMENITIES, k=random.randint(2, 6)))
        if location_type == "Highway":
            amen = sorted(set(amen) | {"Restroom", "Parking"})

        hours = "Open 24 hours" if (random.random() < 0.7 or location_type == "Highway") else random.choice(
            ["06:00 - 23:00", "07:00 - 22:00", "09:00 - 21:00", "08:00 - 20:00"])
        is24 = 1 if hours == "Open 24 hours" else 0
        status = "Operational" if random.random() < 0.9 else random.choice(
            ["Under maintenance", "Coming soon"])
        age_h = random.random() * 6
        last_upd = iso(now - timedelta(hours=age_h))

        phone = f"+91 {random.choice(['80','98','99','97','70','90'])}{random.randint(10000000,99999999)}"
        email = None if random.random() < 0.5 else f"{operator.split()[0].lower()}.{station_seq}@{operator.split()[0].lower()}.in"

        if not address:
            if location_type == "Highway":
                address = f"{name}, {highway} {direction or ''}, near {city}".strip()
            else:
                address = f"{name}, {city}"

        # map links
        gmaps = f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"
        amaps = f"https://maps.apple.com/?ll={lat},{lng}&q={name.replace(' ', '+')}"

        cur.execute(
            """INSERT INTO stations(name,operator_id,ownership,access,location_type,state_code,district_id,
               city_id,panchayat,village,address,highway_id,highway_direction,latitude,longitude,
               contact_phone,contact_email,operating_hours,is_24x7,status,num_chargers,total_capacity_kw,
               max_power_kw,amenities,google_maps_url,apple_maps_url,data_source,last_updated,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (name, op_id[operator], ownership, access or ("Public access" if ownership == "Public" else "Restricted (fleet / hotel)"),
             location_type, st, did, cid, panchayat, village, address, hwid, direction, lat, lng,
             phone, email, hours, is24, status, len(conns), round(total_kw, 1), max_kw,
             json.dumps(amen), gmaps, amaps, "Seed dataset (synthetic) — pending live source",
             last_upd, iso(now)),
        )
        sid = cur.lastrowid

        for c in conns:
            cur.execute(
                """INSERT INTO connectors(station_id,connector_type,formal_name,current_type,power_kw,
                   charging_speed,quantity,status) VALUES(?,?,?,?,?,?,?,?)""",
                (sid, c["ct"], c["formal"], c["current"], c["kw"], c["speed"], c["qty"],
                 "Operational" if status == "Operational" else status),
            )
        for t in tariffs:
            cur.execute(
                """INSERT INTO tariffs(station_id,connector_type,price_per_kwh,session_fee,idle_fee_per_min,
                   currency,notes) VALUES(?,?,?,?,?,?,?)""",
                (sid, t["ct"], t["price"], t["session_fee"], t["idle_fee"], "INR",
                 "Indicative; confirm in operator app"),
            )
        for p in pays:
            cur.execute("INSERT INTO station_payments(station_id,method) VALUES(?,?)", (sid, p))

        stations_out.append(dict(
            id=sid, name=name, operator=operator, operator_kind=m["kind"],
            ownership=ownership, access=access or ("Public access" if ownership == "Public" else "Restricted (fleet / hotel)"),
            location_type=location_type, state=STATES[st], state_code=st,
            district=dist, city=city, panchayat=panchayat, village=village,
            address=address, highway=highway, highway_direction=direction,
            latitude=lat, longitude=lng, contact_phone=phone, contact_email=email,
            operating_hours=hours, is_24x7=bool(is24), status=status,
            num_chargers=len(conns), total_capacity_kw=round(total_kw, 1), max_power_kw=max_kw,
            connectors=[dict(type=c["ct"], formal=c["formal"], current=c["current"],
                             power_kw=c["kw"], speed=c["speed"], quantity=c["qty"]) for c in conns],
            tariffs=[dict(connector_type=t["ct"], price_per_kwh=t["price"],
                          session_fee=t["session_fee"], idle_fee_per_min=t["idle_fee"]) for t in tariffs],
            payments=pays, amenities=amen,
            google_maps_url=gmaps, apple_maps_url=amaps,
            operator_phone=m["phone"], operator_website=m["web"],
            last_updated=last_upd,
        ))

    # --- generate urban stations per city
    for city, st, dist, lat, lng, tier in CITIES:
        if tier == 1:
            n = random.randint(5, 8)
        elif tier == 2:
            n = random.randint(3, 5)
        else:
            n = random.randint(1, 3)
        for i in range(n):
            op = random.choice(OPERATORS)[0]
            # 2W-only networks -> private/urban small
            ownership = "Public" if random.random() < 0.78 else "Private"
            lat2, lng2 = jitter(lat, lng, km=9 if tier == 1 else 6)
            add_station(
                name=f"{op} {city} - {random.choice(['Mall','Metro','Tech Park','Market','Hub','Fuel Station','Hotel','Hospital','Airport Road','Ring Road'])} {i+1}",
                operator=op, ownership=ownership, location_type="Urban",
                city=city, lat=lat2, lng=lng2,
            )

    # --- highway stations
    for num, hname, a, b in HIGHWAYS:
        A = CITY_COORD[a]
        B = CITY_COORD[b]
        n = random.randint(3, 6)
        for i in range(n):
            t = (i + 1) / (n + 1)
            lat, lng = interp(A, B, t)
            lat, lng = jitter(lat, lng, km=5)
            # nearest named city for admin fields
            city = min(CITIES, key=lambda c: (c[3]-lat)**2 + (c[4]-lng)**2)[0]
            op = random.choice(OPERATORS)[0]
            direction = random.choice([
                f"{a} to {b} bound", f"{b} to {a} bound", "Both directions",
                f"Northbound / {b} side", f"Southbound / {a} side"])
            add_station(
                name=f"{op} {num} {random.choice(['Highway Plaza','Food Court','Rest Stop','Fuel Station','Toll Plaza'])} {i+1}",
                operator=op, ownership="Public", location_type="Highway",
                city=city, lat=lat, lng=lng, highway=num, direction=direction,
            )

    # --- village / panchayat stations
    for vname, vdist in VILLAGES:
        city = min(CITIES, key=lambda c: c[2] == vdist and 0 or 1)[0]
        # find a city in same district if possible
        same = [c for c in CITIES if c[2] == vdist]
        if same:
            city = same[0][0]
        base = CITY_COORD.get(city, (23.0, 78.0))
        lat, lng = jitter(base[0], base[1], km=25)
        op = random.choice(OPERATORS)[0]
        add_station(
            name=f"{op} Gram Panchayat Charging Point, {vname}",
            operator=op, ownership=random.choice(["Public", "Public", "Private"]),
            location_type="Village / Rural", city=city, lat=lat, lng=lng,
            village=vname, panchayat=f"{vname} Gram Panchayat",
        )

    # --- refresh log seed (last few runs)
    for k in range(4):
        start = now - timedelta(hours=6 * (k + 1))
        cur.execute(
            """INSERT INTO refresh_log(started_at,finished_at,source,records_seen,records_created,
               records_updated,status,notes) VALUES(?,?,?,?,?,?,?,?)""",
            (iso(start), iso(start + timedelta(minutes=4)), "Open Charge Map (IN) + operator feeds",
             len(stations_out), 0, random.randint(5, 40), "success",
             "6-hourly scheduled refresh"),
        )

    con.commit()
    con.close()

    # --- JSON export for the PWA
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(dict(
            generated_at=iso(now),
            notice="Synthetic seed dataset for prototype. Structure matches the production schema.",
            count=len(stations_out),
            stations=stations_out,
        ), f, ensure_ascii=False)

    # stats
    print(f"stations: {len(stations_out)}")
    print(f"db: {DB_PATH}")
    print(f"json: {JSON_PATH}")
    con = sqlite3.connect(DB_PATH)
    for q, label in [
        ("SELECT COUNT(*) FROM connectors", "connectors"),
        ("SELECT COUNT(*) FROM tariffs", "tariffs"),
        ("SELECT COUNT(*) FROM station_payments", "payment rows"),
        ("SELECT COUNT(*) FROM operators", "operators"),
        ("SELECT COUNT(*) FROM cities", "cities"),
        ("SELECT COUNT(*) FROM districts", "districts"),
    ]:
        print(label, con.execute(q).fetchone()[0])
    print("by location_type:", con.execute(
        "SELECT location_type, COUNT(*) FROM stations GROUP BY location_type").fetchall())
    print("by ownership:", con.execute(
        "SELECT ownership, COUNT(*) FROM stations GROUP BY ownership").fetchall())
    print("by speed:", con.execute(
        "SELECT charging_speed, COUNT(*) FROM connectors GROUP BY charging_speed").fetchall())
    con.close()


if __name__ == "__main__":
    main()
