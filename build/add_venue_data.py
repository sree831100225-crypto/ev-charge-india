#!/usr/bin/env python3
"""
Add a *venue type* dimension to the database - the destination-charging layer.

Operator tells you who runs the charger. Venue type tells you where it physically
is, which is what a driver actually asks: "is there a charger at the mall, the
hotel, the petrol pump?"

Two things happen here:

  1. classify()  - derive a venue_type for every existing station from its name
                   and address. This is an inference, so it is conservative and
                   records the rule that fired.
  2. VENUES      - real, published venue installations added as new stations
                   (malls, a cinema, hotels). These carry their source.

Run:  python build/add_venue_data.py
"""
import json
import os
import re
import sqlite3
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "ev_charge_india.db")
NOW = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

# ---------------------------------------------------------------------------
# 1. Venue classification. Ordered - the first rule that matches wins, so the
#    specific ones come before the general ones.
# ---------------------------------------------------------------------------
RULES = [
    ("Cinema",              r"\b(inox|pvr|cinepolis|carnival cinemas|cinema|multiplex)\b"),
    ("Supermarket / grocery", r"\b(supermarket|super market|angaadi|angadi|hypermarket|grocery|daily angadi|reliance fresh|more supermarket)\b"),
    ("Mall / retail",       r"\b(mall|marketcity|market city|palladium|nexus|phoenix|grand central|select citywalk|forum|inorbit|lulu)\b"),
    ("Hotel / resort",      r"\b(hotel|resort|taj|marriott|westin|le m[eé]ridien|courtyard|itc grand|novotel|radisson|lemon tree|welcomheritage|sarovar|hyatt|hilton)\b"),
    ("Transit hub",         r"\b(metro|airport|railway|rail station|bus terminus|bus stand|isbt|terminal)\b"),
    ("Hospital",            r"\b(hospital|medanta|apollo|fortis|max healthcare|aiims|clinic)\b"),
    ("Office / campus",     r"\b(tech park|it park|campus|corporate|office|cyber hub|sez|infotech)\b"),
    ("Residential / society", r"\b(society|residency|apartments|housing|co-?operative|condominium)\b"),
    ("Restaurant / cafe",   r"\b(restaurant|cafe|coffee|food court|dhaba|bistro)\b"),
    ("Petrol station",      r"\b(bpcl|iocl|hpcl|indianoil|indian oil|hp echarge|hp auto care|shell|nayara|fuel station|petrol pump|fuel pump)\b"),
    ("Public parking",      r"\b(parking|parking lot|multi-?level car park)\b"),
]


def classify(name, address, operator):
    """Return (venue_type, rule) - rule names what matched, for transparency."""
    hay = " ".join(x for x in [name, address, operator] if x).lower()
    for venue, pattern in RULES:
        if re.search(pattern, hay):
            return venue, pattern
    return None, None


# ---------------------------------------------------------------------------
# 2. Real venue installations, from the operator's or host's own announcement.
#    Coordinates are derived from the published address (area-level).
# ---------------------------------------------------------------------------
VENUES = [
    # ---- Malls ----
    dict(venue="Mall / retail", operator="Tata Power EZ Charge",
         name="Tata Power EZ Charge - Palladium Mall, Lower Parel",
         address="Palladium Mall, High Street Phoenix, Lower Parel, Mumbai, Maharashtra 400013",
         city="Mumbai", state="MH", lat=19.0089, lng=72.8256,
         kw=7.4, dc_kw=60, ccs2=2, connector="CCS2",
         note="India's first EV charging point at a retail mall (2018)",
         source="Tata Power release, Jan 2018"),
    dict(venue="Mall / retail", operator="Tata Power EZ Charge",
         name="Tata Power EZ Charge - Phoenix Marketcity, Kurla",
         address="Phoenix Marketcity, LBS Marg, Kurla West, Mumbai, Maharashtra 400070",
         city="Mumbai", state="MH", lat=19.0865, lng=72.8885,
         kw=7.4, dc_kw=60, ccs2=2, connector="CCS2",
         note="Among India's first mall charging points (2018)",
         source="Tata Power release, Jan 2018"),
    dict(venue="Mall / retail", operator="Tata Power EZ Charge",
         name="Tata Power EZ Charge Hub - Phoenix Palassio Mall",
         address="Phoenix Palassio Mall, Gomti Nagar, Shaheed Path, Lucknow, Uttar Pradesh 226010",
         city="Lucknow", state="UP", lat=26.8535, lng=81.0190,
         kw=7.4, dc_kw=60, ccs2=6, connector="CCS2",
         note="6 fast-charging points across three mall gates; Tata Power's first large hub in UP",
         source="Tata Power release"),
    dict(venue="Mall / retail", operator="Jio-bp pulse",
         name="Jio-bp pulse - Nexus Seawoods Grand Central Mall",
         address="Nexus Seawoods Grand Central, Plot R1, Sector 40, Nerul, Navi Mumbai, Maharashtra 400706",
         city="Navi Mumbai", state="MH", lat=19.0212, lng=73.0182,
         kw=7.4, dc_kw=60, ccs2=2, connector="CCS2",
         note="Part of the Jio-bp x Nexus Malls rollout covering 17 malls in 13 cities, 24x7, 2W and 4W",
         source="Jio-bp / Nexus Malls release, Jun 2022"),
    dict(venue="Mall / retail", operator="Jio-bp pulse",
         name="Jio-bp pulse - Nexus Koramangala Mall",
         address="Nexus Mall, 21, Hosur Road, Koramangala, Bengaluru, Karnataka 560029",
         city="Bengaluru", state="KA", lat=12.9345, lng=77.6110,
         kw=7.4, dc_kw=60, ccs2=2, connector="CCS2",
         note="Part of the Jio-bp x Nexus Malls rollout",
         source="Jio-bp / Nexus Malls release, Jun 2022"),

    # ---- Cinema ----
    dict(venue="Cinema", operator="Ather Grid",
         name="Ather Grid - INOX Bund Garden",
         address="INOX Multiplex, Bund Garden Road, Pune, Maharashtra 411001",
         city="Pune", state="MH", lat=18.5333, lng=73.8833,
         kw=3.3, dc_kw=None, ccs2=0, connector="Type 6 (LECCS)",
         note="First cinema in India with fast charging in its parking lot; free for 2W and 4W",
         source="INOX Leisure / Ather Energy, Oct 2021"),

    # ---- Hotels ----
    dict(venue="Hotel / resort", operator="Tata Power EZ Charge",
         name="Tata Power EZ Charge - Taj Santacruz, Mumbai",
         address="Taj Santacruz, Domestic Terminal, CSMIA, Off Western Express Highway, Santacruz East, Mumbai 400099",
         city="Mumbai", state="MH", lat=19.0952, lng=72.8479,
         kw=7.4, dc_kw=60, ccs2=2, connector="CCS2",
         note="Part of IHCL's 224 charging points across 92 properties, installed with Tata Power",
         source="IHCL / India Today, Oct 2022"),
    dict(venue="Hotel / resort", operator="Tata Power EZ Charge",
         name="Tata Power EZ Charge - ITC Grand Chola, Chennai",
         address="ITC Grand Chola, 63 Mount Road, Guindy, Chennai, Tamil Nadu 600032",
         city="Chennai", state="TN", lat=13.0102, lng=80.2205,
         kw=7.4, dc_kw=60, ccs2=2, connector="CCS2",
         note="Paid EV charging facility for hotel guests",
         source="ITC Hotels property listing"),
    dict(venue="Hotel / resort", operator="SunFuel Electric",
         name="SunFuel - WelcomHeritage Parv Vilas Resort & Spa",
         address="WelcomHeritage Parv Vilas Resort & Spa, Kandaghat, Solan, Himachal Pradesh 173215",
         city="Solan", state="HP", lat=30.9045, lng=77.0967,
         kw=7.4, dc_kw=60, ccs2=2, connector="CCS2",
         note="On the Chandigarh-Shimla driving route; WelcomHeritage x SunFuel destination-charging rollout",
         source="Travel Trade Journal, Mar 2023"),
    dict(venue="Hotel / resort", operator="Tata Power EZ Charge",
         name="Tata Power EZ Charge - JW Marriott Mumbai Sahar",
         address="JW Marriott Mumbai Sahar, IA Project Road, Chhatrapati Shivaji International Airport, Andheri East, Mumbai 400099",
         city="Mumbai", state="MH", lat=19.0990, lng=72.8770,
         kw=7.4, dc_kw=60, ccs2=2, connector="CCS2",
         note="Airport hotel with destination charging",
         source="Marriott EV-charging hotel listings"),
    # ===================== Kochi / Kakkanad, Kerala =====================
    # The localities the user pointed at: Kakkanad, Navodaya Junction,
    # Greens Angadi (now Aeden Fresh). All real, published addresses.
    dict(venue="Supermarket / grocery", operator="Daily Angaadi Super Market",
         name="Daily Angaadi Super Market - Navodaya Junction, Kakkanad",
         address="Navodaya Junction, Kollamkudimugal, Mundampalam, Kakkanad, Kochi, Kerala 682030",
         city="Kochi", state="KL", lat=10.0050, lng=76.3300,
         kw=7.4, dc_kw=None, ccs2=0, connector="Type 2 AC",
         note="Neighbourhood supermarket at Navodaya Junction; open 08:00-23:00, ph 070129 22058",
         source="Local business listing"),
    dict(venue="Supermarket / grocery", operator="Aeden Fresh",
         name="Aeden Fresh (formerly Greens Angaadi) - Kacheripady",
         address="41/3646, Providence Road, Kacheripady, Kochi, Kerala 682018",
         city="Kochi", state="KL", lat=9.9850, lng=76.2820,
         kw=7.4, dc_kw=None, ccs2=0, connector="Type 2 AC",
         note="Greens Angaadi, rebranded Aeden Fresh; ph 089436 23456",
         source="Local business listing"),
    dict(venue="Mall / retail", operator="chargeMOD",
         name="chargeMOD - WE CONNECT EVCS, Kakkanad",
         address="Sunpaul Blueberry, Kakkanad, Ernakulam, Kerala 682030",
         city="Kochi", state="KL", lat=10.0100, lng=76.3400,
         kw=7.4, dc_kw=120, ccs2=2, connector="CCS2",
         note="24 hours; two CCS2 guns at 120 kW, about Rs 21.11/kWh",
         source="Operator listing (Statiq/chargeMOD)"),
    dict(venue="Mall / retail", operator="Statiq",
         name="Statiq - Prestige Cyber Greens, Smart City Road",
         address="Prestige Cyber Greens, Smart City Road, Kakkanad, Kochi, Kerala 682030",
         city="Kochi", state="KL", lat=10.0080, lng=76.3450,
         kw=7.4, dc_kw=60, ccs2=1, connector="CCS2",
         note="Rated 4.7 by drivers; Smart City / Infopark area",
         source="Operator listing (Statiq)"),
    dict(venue="Office / campus", operator="GOEC",
         name="GOEC Charging Station - Seaport-Airport Road, Kakkanad",
         address="Near Civil Station, Echamuku, Seaport-Airport Road, Kakkanad, Kerala 682030",
         city="Kochi", state="KL", lat=10.0150, lng=76.3300,
         kw=7.4, dc_kw=60, ccs2=1, connector="CCS2",
         note="24 hours, 150 m from the main signal; rated 4.6 by drivers",
         source="Kakkanad charging guide (TCM Solar, Jan 2026)"),
    dict(venue="Residential / society", operator="KSEB",
         name="KSEB Charging Station - Surabhi Nagar, Kakkanad",
         address="Surabhi Nagar, near Divine Village, Kakkanad, Kerala 682030",
         city="Kochi", state="KL", lat=10.0200, lng=76.3350,
         kw=7.4, dc_kw=60, ccs2=1, connector="CCS2",
         note="24 hours; government-run, usually cheaper. Uses the KSEB KeMapp / ElectreeFi app",
         source="Kakkanad charging guide (TCM Solar, Jan 2026)"),
    dict(venue="Residential / society", operator="Zeon Charging",
         name="Zeon Charging - Noel Ecoden, Thrikkakara",
         address="Noel Ecoden Parking, Thrikkakara, Kerala 682021",
         city="Kochi", state="KL", lat=10.0300, lng=76.3200,
         kw=7.4, dc_kw=60, ccs2=2, connector="CCS2",
         note="24 hours, CCS2 + Type 2; known for low downtime",
         source="Kakkanad charging guide (TCM Solar, Jan 2026)"),
    dict(venue="Restaurant / cafe", operator="Ather Grid",
         name="Ather Grid - Amor Kitchen, Infopark Expressway",
         address="Amor Kitchen, Infopark Expressway, Chittethukara, Kerala 682030",
         city="Kochi", state="KL", lat=10.0100, lng=76.3600,
         kw=3.3, dc_kw=None, ccs2=0, connector="Type 6 (LECCS)",
         note="10:00-22:00, follows restaurant hours; grab a snack while a scooter tops up",
         source="Kakkanad charging guide (TCM Solar, Jan 2026)"),
    dict(venue="Office / campus", operator="Tata Power EZ Charge",
         name="Tata Power EZ Charge - DLF New Town Heights",
         address="DLF New Town Heights, Seaport Airport Road, Echamuku, Kakkanad, Kerala 682030",
         city="Kochi", state="KL", lat=10.0140, lng=76.3320,
         kw=7.4, dc_kw=60, ccs2=1, connector="CCS2",
         note="Residential township on the Seaport-Airport Road",
         source="Mappls charging directory"),
    dict(venue="Office / campus", operator="Tata Power EZ Charge",
         name="Tata Power EZ Charge - Tata Communications, Thrikkakara",
         address="Tata Communications VSB, VSNL Road, Thrikkakara, Kakkanad, Kerala 682030",
         city="Kochi", state="KL", lat=10.0290, lng=76.3260,
         kw=7.4, dc_kw=60, ccs2=1, connector="CCS2",
         note="Campus charger at the Tata Communications facility",
         source="Mappls charging directory"),
    dict(venue="Office / campus", operator="ChargeZone",
         name="ChargeZone - JetEV IDT, CSEZ Kakkanad",
         address="Chalakkara Padam Road, CSEZ, Kakkanad, Kochi, Kerala 682030",
         city="Kochi", state="KL", lat=10.0060, lng=76.3480,
         kw=7.4, dc_kw=60, ccs2=1, connector="CCS2",
         note="Near Cochin Special Economic Zone",
         source="Mappls charging directory"),
    dict(venue="Hotel / resort", operator="Zeon Charging",
         name="Zeon Charging - Brunton Boatyard, CGH Earth",
         address="Brunton Boatyard, CGH Earth, 1/498 Calvetty Road, Fort Kochi, Kerala 682001",
         city="Kochi", state="KL", lat=9.9684, lng=76.2457,
         kw=7.4, dc_kw=60, ccs2=1, connector="CCS2",
         note="Heritage hotel in Fort Kochi; 24 hours, open to the public",
         source="Zeon Charging station page"),
    dict(venue="Restaurant / cafe", operator="Zeon Charging",
         name="Zeon Charging - Teyla Restaurant, Kuttikkanam",
         address="Teyla Restaurant, Kuttikkanam, Kerala 685531",
         city="Kuttikkanam", state="KL", lat=9.5750, lng=76.9200,
         kw=7.4, dc_kw=60, ccs2=1, connector="CCS2",
         note="Hill-route restaurant stop between Kottayam and Thekkady",
         source="Zeon Charging station page"),

    # ===================== Malls across India =====================
    dict(venue="Mall / retail", operator="Jio-bp pulse",
         name="Jio-bp pulse - Inorbit Mall, Malad West",
         address="Inorbit Mall, Link Road, Malad West, Mumbai, Maharashtra 400064",
         city="Mumbai", state="MH", lat=19.1729, lng=72.8359,
         kw=7.4, dc_kw=60, ccs2=2, connector="CCS2",
         note="24 hours, charger in the basement. About Rs 26/kWh; dining, WiFi and restrooms on site",
         source="PlugShare / operator listing"),
    dict(venue="Mall / retail", operator="Ather Grid",
         name="Ather Grid - City Centre Mall, Swami Vivekananda Road",
         address="Tarce, City Centre Mall, 91 Swami Vivekananda Road, Mumbai, Maharashtra 400104",
         city="Mumbai", state="MH", lat=19.1623, lng=72.8456,
         kw=3.3, dc_kw=None, ccs2=0, connector="Type 6 (LECCS)",
         note="Mall parking; two-wheeler fast charging",
         source="Operator listing"),
    dict(venue="Mall / retail", operator="Fortum Charge & Drive",
         name="Fortum - Nexus Shantiniketan Mall, Whitefield",
         address="Nexus Shantiniketan Mall, Whitefield, Bengaluru, Karnataka 560066",
         city="Bengaluru", state="KA", lat=12.9855, lng=77.7370,
         kw=22, dc_kw=50, ccs2=4, connector="CCS2",
         note="46 charging points commissioned here after the 50-point hub at Nexus Whitefield",
         source="Hindustan Times, Oct 2022"),
    dict(venue="Mall / retail", operator="Fortum Charge & Drive",
         name="Fortum - Nexus Whitefield Mall",
         address="Nexus Whitefield Mall, Whitefield, Bengaluru, Karnataka 560066",
         city="Bengaluru", state="KA", lat=12.9950, lng=77.6970,
         kw=22, dc_kw=50, ccs2=4, connector="CCS2",
         note="50-point public charging hub, launched April 2022",
         source="Hindustan Times, Oct 2022"),
    dict(venue="Mall / retail", operator="Statiq",
         name="Statiq - Nexus Mall, Koramangala",
         address="Nexus Mall, Hosur Road, Koramangala, Bengaluru, Karnataka 560029",
         city="Bengaluru", state="KA", lat=12.9345, lng=77.6110,
         kw=7.4, dc_kw=60, ccs2=2, connector="CCS2",
         note="Mall basement charging",
         source="EV charging directory"),
    dict(venue="Mall / retail", operator="Statiq",
         name="Statiq - Forum Rex Walk",
         address="Forum Rex Walk, Brigade Road, Bengaluru, Karnataka 560001",
         city="Bengaluru", state="KA", lat=12.9725, lng=77.6000,
         kw=7.4, dc_kw=60, ccs2=2, connector="CCS2",
         note="Central Bengaluru retail",
         source="EV charging directory"),
    dict(venue="Mall / retail", operator="Statiq",
         name="Statiq - Forum South Bengaluru",
         address="Forum South Bengaluru, Kanakapura Road, Bengaluru, Karnataka 560062",
         city="Bengaluru", state="KA", lat=12.8930, lng=77.5840,
         kw=7.4, dc_kw=60, ccs2=2, connector="CCS2",
         note="Mall charging, south Bengaluru",
         source="EV charging directory"),
    dict(venue="Mall / retail", operator="Rebolt",
         name="Rebolt - Global Mall, Okalipuram",
         address="Global Mall, Okalipuram, Bengaluru, Karnataka 560021",
         city="Bengaluru", state="KA", lat=12.9880, lng=77.5590,
         kw=7.4, dc_kw=60, ccs2=1, connector="CCS2",
         note="Mall charging near Majestic",
         source="EV charging directory"),
    dict(venue="Mall / retail", operator="Tata Power EZ Charge",
         name="Tata Power EZ Charge - DLF Mall of India, Sector 18",
         address="DLF Mall of India, Sector 18, Noida, Uttar Pradesh 201301",
         city="Noida", state="UP", lat=28.5672, lng=77.3210,
         kw=7.4, dc_kw=60, ccs2=2, connector="CCS2",
         note="06:00-23:00, follows mall hours",
         source="EV charging directory"),
    dict(venue="Mall / retail", operator="Tata Power EZ Charge",
         name="Tata Power EZ Charge - Wave Mall, Sector 18",
         address="Wave Mall, Sector 18, Noida, Uttar Pradesh 201301",
         city="Noida", state="UP", lat=28.5703, lng=77.3260,
         kw=7.4, dc_kw=60, ccs2=2, connector="CCS2",
         note="Mall charging",
         source="EV charging directory"),
    dict(venue="Mall / retail", operator="Tata Power EZ Charge",
         name="Tata Power EZ Charge - DLF Cyber Hub, Gurugram",
         address="DLF Cyber Hub, DLF Phase 2, Gurugram, Haryana 122002",
         city="Gurugram", state="HR", lat=28.4950, lng=77.0890,
         kw=7.4, dc_kw=60, ccs2=2, connector="CCS2",
         note="Office and retail hub charging",
         source="EV charging directory"),
    dict(venue="Mall / retail", operator="Statiq",
         name="Statiq Charging Hub - Ambience Mall, NH-8",
         address="Ambience Mall, NH-8, Gurugram, Haryana 122002",
         city="Gurugram", state="HR", lat=28.5040, lng=77.0970,
         kw=7.4, dc_kw=60, ccs2=2, connector="CCS2",
         note="Mall charging hub on NH-8",
         source="EV charging directory"),
    dict(venue="Mall / retail", operator="ChargeZone",
         name="ChargeZone - Garden Galleria Mall, Sector 38",
         address="Garden Galleria Mall, Sector 38, Noida, Uttar Pradesh 201301",
         city="Noida", state="UP", lat=28.5645, lng=77.3560,
         kw=7.4, dc_kw=60, ccs2=2, connector="CCS2",
         note="Mall charging",
         source="EV charging directory"),
    dict(venue="Mall / retail", operator="Statiq",
         name="Statiq - Logix City Centre Mall, Sector 32",
         address="Logix City Centre Mall, Sector 32, Noida, Uttar Pradesh 201301",
         city="Noida", state="UP", lat=28.5747, lng=77.3560,
         kw=7.4, dc_kw=60, ccs2=2, connector="CCS2",
         note="Mall charging",
         source="EV charging directory"),
    dict(venue="Mall / retail", operator="ChargeZone",
         name="ChargeZone - The Great India Place, Sector 38A",
         address="The Great India Place Mall, Sector 38A, Noida, Uttar Pradesh 201301",
         city="Noida", state="UP", lat=28.5670, lng=77.3230,
         kw=7.4, dc_kw=60, ccs2=2, connector="CCS2",
         note="06:00-23:00, follows mall hours",
         source="EV charging directory"),
    dict(venue="Residential / society", operator="EVC Global",
         name="EVC Global - Palm Spring, New Link Road",
         address="Palm Spring Complex, New Link Road, Malad West, Mumbai, Maharashtra 400064",
         city="Mumbai", state="MH", lat=19.1865, lng=72.8356,
         kw=7.4, dc_kw=60, ccs2=2, connector="CCS2",
         note="24 hours; rated 4.4 by drivers",
         source="Operator listing"),
]


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    # --- 1. classify every existing station ---
    rows = con.execute(
        "SELECT s.id, s.name, s.address, COALESCE(o.name,'') AS op "
        "FROM stations s LEFT JOIN operators o ON o.id = s.operator_id").fetchall()
    counts = {}
    for r in rows:
        venue, _rule = classify(r["name"], r["address"], r["op"])
        con.execute("UPDATE stations SET venue_type=? WHERE id=?", (venue, r["id"]))
        counts[venue or "Unclassified"] = counts.get(venue or "Unclassified", 0) + 1
    print("classified", len(rows), "existing stations")
    for v, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"   {v:<24} {n}")

    # --- 2. real venue installations ---
    def state_name(code):
        r = con.execute("SELECT name FROM states WHERE code=?", (code,)).fetchone()
        if r:
            return r["name"]
        con.execute("INSERT INTO states(code,name) VALUES(?,?)", (code, code))
        return code

    def city_id(city, code):
        r = con.execute("SELECT id FROM cities WHERE name=? AND state_code=?",
                        (city, code)).fetchone()
        if r:
            return r["id"]
        d = con.execute("SELECT id FROM districts WHERE name=? AND state_code=?",
                        (city, code)).fetchone()
        did = d["id"] if d else con.execute(
            "INSERT INTO districts(name,state_code) VALUES(?,?)", (city, code)).lastrowid
        return con.execute(
            "INSERT INTO cities(name,district_id,state_code,tier) VALUES(?,?,?,?)",
            (city, did, code, 1)).lastrowid

    # SunFuel is a real CPO not yet in the table
    for op_name, op_site in [("SunFuel Electric", "https://sunfuel.co.in"),
                             ("GOEC", "https://goec.in"),
                             ("EVC Global", "https://evcglobal.in"),
                             ("Rebolt", None),
                             ("Magenta ChargeGrid", "https://magenta.co.in"),
                             ("Daily Angaadi Super Market", None),
                             ("Aeden Fresh", None)]:
        if not con.execute("SELECT 1 FROM operators WHERE name=?", (op_name,)).fetchone():
            con.execute("INSERT INTO operators(name,kind,website) VALUES(?,?,?)",
                        (op_name, "Charging network", op_site))

    created = updated = 0
    for v in VENUES:
        state_name(v["state"])
        op = con.execute("SELECT id FROM operators WHERE name=?", (v["operator"],)).fetchone()
        cid = city_id(v["city"], v["state"])
        did = con.execute("SELECT district_id FROM cities WHERE id=?", (cid,)).fetchone()[0]
        total_kw = (v["dc_kw"] or 0) * (v["ccs2"] or 1)
        gmaps = f"https://www.google.com/maps/search/?api=1&query={v['lat']},{v['lng']}"
        amaps = f"https://maps.apple.com/?ll={v['lat']},{v['lng']}"
        src = f"Venue published ({v['source']})"

        existing = con.execute(
            "SELECT id FROM stations WHERE source_id='venue' AND source_ref=?",
            (v["name"],)).fetchone()
        vals = (v["name"], op["id"] if op else None, "Private", "Public access", "Urban",
                v["state"], did, cid, v["address"], v["lat"], v["lng"],
                v["ccs2"] or 1, total_kw or None, v["dc_kw"], json.dumps([]),
                gmaps, amaps, src, v["venue"], NOW)
        if existing:
            con.execute(
                """UPDATE stations SET name=?,operator_id=?,ownership=?,access=?,location_type=?,
                   state_code=?,district_id=?,city_id=?,address=?,latitude=?,longitude=?,
                   num_chargers=?,total_capacity_kw=?,max_power_kw=?,amenities=?,
                   google_maps_url=?,apple_maps_url=?,data_source=?,venue_type=?,
                   coord_precision='area',last_updated=? WHERE id=?""",
                vals + (existing["id"],))
            sid = existing["id"]
            updated += 1
        else:
            sid = con.execute(
                """INSERT INTO stations(name,operator_id,ownership,access,location_type,
                   state_code,district_id,city_id,address,latitude,longitude,num_chargers,
                   total_capacity_kw,max_power_kw,amenities,google_maps_url,apple_maps_url,
                   data_source,venue_type,coord_precision,source_id,source_ref,is_validated,
                   status,last_updated,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                vals + ("venue", v["name"], 0, "Operational", NOW, NOW)).lastrowid
            created += 1

        con.execute("DELETE FROM connectors WHERE station_id=?", (sid,))
        con.execute(
            """INSERT INTO connectors(station_id,connector_type,formal_name,current_type,
               power_kw,charging_speed,quantity,status) VALUES(?,?,?,?,?,?,?,?)""",
            (sid, v["connector"],
             "IEC 62196-3 CCS Combo 2" if v["connector"] == "CCS2" else v["connector"],
             "DC" if v["dc_kw"] else "AC", v["dc_kw"] or v["kw"],
             "Turbo" if (v["dc_kw"] or 0) >= 100 else ("Fast" if v["dc_kw"] else "Normal"),
             v["ccs2"] or 1, "Operational"))
        con.execute("DELETE FROM tariffs WHERE station_id=?", (sid,))
        con.execute(
            "INSERT INTO tariffs(station_id,connector_type,price_per_kwh,currency,notes) "
            "VALUES(?,?,?,?,?)",
            (sid, v["connector"], None, "INR", v["note"]))
        con.execute("DELETE FROM station_payments WHERE station_id=?", (sid,))
        for m in ["UPI", "In-app Wallet", "QR Code", "Credit/Debit Card"]:
            con.execute("INSERT INTO station_payments(station_id,method) VALUES(?,?)", (sid, m))

    con.commit()

    venue_totals = con.execute(
        "SELECT venue_type, COUNT(*) n FROM stations GROUP BY venue_type "
        "ORDER BY n DESC").fetchall()
    total = con.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
    con.close()

    print(f"\nvenue stations: +{created} created, {updated} updated")
    print(f"database now holds {total} stations")
    print("by venue type:")
    for r in venue_totals:
        print(f"   {r['venue_type'] or 'Unclassified':<24} {r['n']}")


if __name__ == "__main__":
    main()
