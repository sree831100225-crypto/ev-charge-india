#!/usr/bin/env python3
"""
Add OEM (vehicle-manufacturer) charging data to the database.

Two distinct things get recorded, because conflating them would be misleading:

  1. `brands` - one row per manufacturer, saying whether it runs a public
     charging network, what that network is called, its verified size, the
     connector standard, and its charging partner if it has no network of its own.

  2. `stations` - only where the manufacturer publishes actual locations.
     Two do: Mahindra (CHARGE_iN, 6 published sites) and Ola Electric
     (Hypercharger, 5 published Bengaluru sites). Everything else is recorded
     at network level in `brands`, not invented as stations.

Provenance is explicit: source_id='oem', data_source names the publisher, and
coord_precision records how tight the coordinates are ('town'/'area' - these are
derived from the published address, not from a survey).

Run:  python build/add_oem_data.py
"""
import json
import os
import sqlite3
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "ev_charge_india.db")

NOW = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

# ---------------------------------------------------------------------------
# 1. Brands
#    operates_network: 1 = runs its own public charging network
#    Everything below is from the manufacturer's own releases or trade press.
# ---------------------------------------------------------------------------
BRANDS = [
    dict(name="Tata Motors", aliases="TATA.ev, Tata EV", segment="Car", operates_network=1,
         network_name="TATA.ev dealer charging + Mega Charger",
         network_scale="700+ DC/AC fast chargers at dealer outlets across 250+ cities; open-collaboration partnership with 8 CPOs covering 10,000+ public chargers; 'Mega Charger' network planned across 500 locations",
         connector_standard="CCS2, Type 2 AC", partnership=None, app="Tata.ev / iRA.ev",
         website="https://ev.tatamotors.com",
         notes="Largest EV car seller in India; charging run through Tata Power and partner CPOs rather than a wholly owned network",
         source="Times of India (Jan 2025); Reuters factbox (Feb 2025)", verified=1),

    dict(name="Hyundai Motor India", aliases="Hyundai, HMIL", segment="Car", operates_network=1,
         network_name="HMIL fast-charging network (myHyundai app)",
         network_scale="183 DC fast-charging stations operational across 105 cities, scaling to 600 by 2030; 30,000+ charging points aggregated in the myHyundai app via CPO partnerships",
         connector_standard="CCS2, 60 kW to 240 kW", partnership=None, app="myHyundai",
         website="https://www.hyundai.com/in/en",
         notes="Own network plus an aggregator app open to all brands; charging within an average 25 km radius nationally",
         source="Hyundai Motor India press release (Jul 2026)", verified=1),

    dict(name="Kia India", aliases="Kia", segment="Car", operates_network=1,
         network_name="Kia dealer charging network",
         network_scale="150 kW DC fast chargers at dealerships; a 210 kW unit, at the time the fastest public charger in India",
         connector_standard="CCS2", partnership="Partner-led network plus dealer charging",
         app="Kia Connect", website="https://www.kia.com/in/",
         notes="Partner-led ecosystem; charging accessibility grows with the EV portfolio (EV6, Syros EV)",
         source="Overdrive (OEM charging networks)", verified=1),

    dict(name="JSW MG Motor India", aliases="MG Motor, MG, JSW MG", segment="Car",
         operates_network=1, network_name="MG Charge (community) + eHUB aggregator app",
         network_scale="1,000 community chargers across 470+ sites - first OEM to reach that scale; eHUB app lists 22,500-25,000+ charging points across 40 CPOs",
         connector_standard="15 A / AC community sockets; CCS2 on the aggregated network",
         partnership=None, app="eHUB by MG",
         website="https://www.mgmotor.co.in",
         notes="Community charging in housing societies, hospitals, hotels and campuses. eHUB is an aggregator app, open to all brands",
         source="JSW MG Motor India press releases (Jun 2026, Mar 2026)", verified=1),

    dict(name="Mahindra & Mahindra", aliases="Mahindra, M&M", segment="Car", operates_network=1,
         network_name="CHARGE_iN by Mahindra",
         network_scale="50 live locations / 200 charging points (Sep 2026); targeting 250 stations and ~1,000 points by Dec 2027",
         connector_standard="180 kW DC dual-gun, CCS2", partnership=None,
         app="CHARGE_iN by Mahindra, Me4U",
         website="https://www.mahindraelectricsuv.com/technology/Charge_IN.html",
         notes="Pure CCS2 network, open to all brands, on highway corridors. First HPCL collaboration site live on the Mumbai-Pune Expressway",
         source="Mahindra press releases (Nov 2025, Sep 2026)", verified=1),

    dict(name="Mercedes-Benz India", aliases="Mercedes, Mercedes-Benz, MBI", segment="Luxury car",
         operates_network=1, network_name="Mercedes-Benz India charging network",
         network_scale="140 charging points - 100+ 22 kW AC, 20+ 60 kW DC and 20+ 180 kW DC; largest network among luxury car makers in India",
         connector_standard="CCS2, Type 2 AC", partnership=None,
         app="Mercedes me Charge / MBRDI charging app",
         website="https://www.mercedes-benz.co.in",
         notes="Opened to owners of other brands in 2023; sited along popular drive routes (Mumbai-Pune, Delhi-Chandigarh-Shimla, Chennai-Kochi)",
         source="Overdrive; Inc42 (Sep 2023)", verified=1),

    dict(name="BMW India", aliases="BMW", segment="Luxury car", operates_network=1,
         network_name="BMW India charging network",
         network_scale="50 chargers across 34 locations, largely 50 kW DC units",
         connector_standard="CCS2, 50 kW", partnership=None, app="My BMW",
         website="https://www.bmw.in",
         notes="Announced as the largest DC fast-charging network to be set up by an automaker in India at the time",
         source="Overdrive (OEM charging networks)", verified=1),

    dict(name="BYD India", aliases="BYD", segment="Car", operates_network=0,
         network_name=None,
         network_scale="Access to 950+ partner charging stations",
         connector_standard="CCS2, Type 2", partnership="ChargeZone, Volttic, IndiPro",
         app="BYD app", website="https://bydindia.in",
         notes="No network of its own; e6 customers get partner network access including ChargeZone's highway coverage",
         source="Economic Times / Financial Express (May 2022)", verified=1),

    dict(name="Citroën India", aliases="Citroen", segment="Car", operates_network=0,
         network_name=None,
         network_scale="DC fast chargers at key dealerships and workshops (phased rollout)",
         connector_standard="CCS2", partnership="Jio-bp pulse", app="My Citroën Connect",
         website="https://www.citroen.in",
         notes="Strategic charging partnership with Jio-bp; chargers at dealerships are open to all EV cars",
         source="Jio-bp press release (Jan 2023)", verified=1),

    dict(name="Ather Energy", aliases="Ather", segment="Two-wheeler", operates_network=1,
         network_name="Ather Grid",
         network_scale="3,675+ fast chargers operated directly; 5,000+ accessible including partner networks; 395+ cities. Bengaluru alone has 240+",
         connector_standard="LECCS (Type 7, IS 17017) - interoperable",
         partnership=None, app="Ather app",
         website="https://www.atherenergy.com/grid",
         notes="India's oldest and widest 2W fast-charging network (live since 2018). Ather opened the LECCS connector IP, so Hero Vida, Matter, Bolt.Earth and Kazam interoperate. Tariff about Rs 1.2/min + GST",
         source="Ather Energy press release (Jan 2026)", verified=1),

    dict(name="Ola Electric", aliases="Ola", segment="Two-wheeler", operates_network=1,
         network_name="Ola Hypercharger Network",
         network_scale="288 active hypercharging points across 60+ cities (last published figure, late 2024); 978 total charging points",
         connector_standard="Proprietary - Ola vehicles only",
         partnership=None, app="Ola Electric app",
         website="https://www.olaelectric.com/hypercharger-network",
         notes="Closed network: Ola scooters cannot use LECCS chargers, and other brands cannot use Hyperchargers. Tariff about Rs 2.5/min",
         source="Ola Electric Hypercharger page", verified=1),

    dict(name="Hero MotoCorp", aliases="Hero, Vida, VIDA", segment="Two-wheeler",
         operates_network=1, network_name="VIDA charging network",
         network_scale="4,600+ public fast-charging points across 320+ cities, plus 500+ community AC chargers",
         connector_standard="LECCS (Type 7) - interoperable with Ather Grid",
         partnership=None, app="My VIDA / VIDA Charge",
         website="https://www.heromotocorp.com",
         notes="Hero-Ather partnership (Dec 2023) made the two networks interoperable - the first such 2W arrangement globally. Free fast charging on the VIDA Edge plan",
         source="Hero MotoCorp / Ather partnership release; MeraEV (2026)", verified=1),

    dict(name="TVS Motor Company", aliases="TVS, iQube", segment="Two-wheeler",
         operates_network=0, network_name=None,
         network_scale="Access via partner network (no owned public chargers)",
         connector_standard="Vehicle-specific; AC points usable", partnership="Jio-bp (since 2022)",
         app="TVS iQube app", website="https://www.tvsmotor.com",
         notes="Deliberately home-charging-first; public top-ups come through the Jio-bp tie-up and third-party AC points. India's largest e2W seller by share",
         source="MeraEV public charging guide (Jul 2026)", verified=1),

    dict(name="Bajaj Auto", aliases="Bajaj, Chetak", segment="Two-wheeler",
         operates_network=0, network_name=None,
         network_scale="Dealer-based charging only; 4,000+ town dealer network",
         connector_standard="Chetak 35-series fast charging at dealerships; onboard charger plugs into a 5 A socket",
         partnership="Own dealer network", app="Chetak app",
         website="https://www.bajajauto.com",
         notes="No public fast-charging network. With 8 lakh+ Chetaks on the road, Bajaj has bet on dealer reach over public chargers",
         source="MeraEV public charging guide (Jul 2026)", verified=1),

    dict(name="Ultraviolette Automotive", aliases="Ultraviolette, UV", segment="Two-wheeler",
         operates_network=0, network_name=None,
         network_scale="130+ Type-6 DC fast chargers deployed with Bolt.Earth across 7 states (target exceeded); 200 more planned",
         connector_standard="Type 6 (IS 17017 Part 2/Section 6), also IEC 62196-6",
         partnership="Bolt.Earth", app="Ultraviolette app, Bolt.Earth app",
         website="https://www.ultraviolette.com",
         notes="Built its motorcycles around the open national Type-6 standard rather than a proprietary connector",
         source="Autocar Professional (Mar 2026, May 2026)", verified=1),

    dict(name="Simple Energy", aliases="Simple", segment="Two-wheeler", operates_network=0,
         network_name=None,
         network_scale="Access to 270+ Bolt.Earth Blaze DC chargers across 100+ cities",
         connector_standard="LEVDC / Type 6, 3 kW and 6 kW variants",
         partnership="Bolt.Earth", app="Simple Connect, Bolt.Earth app",
         website="https://www.simpleenergy.in",
         notes="Gen 2 vehicles compatible out of the box; Gen 1 via a software update",
         source="EVIndia (Mar 2026)", verified=1),

    dict(name="Tork Motors", aliases="Tork", segment="Two-wheeler", operates_network=0,
         network_name="TORK public charging (in progress)",
         network_scale="Not operational at scale - company states the network is 'in the process of setting up'",
         connector_standard="Type 6", partnership=None, app="Tork app",
         website="https://torkmotors.com",
         notes="States an aim of a charger within 5 km in a supported city, but no verified live network figure",
         source="Tork Motors FAQ", verified=0),

    dict(name="Ampere Vehicles", aliases="Ampere, Greaves", segment="Two-wheeler",
         operates_network=0, network_name=None, network_scale="No public charging network",
         connector_standard="Home charging only", partnership=None, app="Ampere app",
         website="https://www.amperevehicles.com",
         notes="Sells vehicles with home charging; no public network found in any published source",
         source="No public network found", verified=0),

    dict(name="Revolt Motors", aliases="Revolt", segment="Two-wheeler", operates_network=0,
         network_name=None, network_scale="No public charging network",
         connector_standard="Home charging only", partnership=None, app="Revolt app",
         website="https://www.revoltmotors.com",
         notes="Sells vehicles with home charging; no public network found",
         source="No public network found", verified=0),

    dict(name="Okinawa Autotech", aliases="Okinawa", segment="Two-wheeler", operates_network=0,
         network_name=None, network_scale="No public charging network",
         connector_standard="Home charging only", partnership=None, app="Okinawa app",
         website="https://www.okinawascooters.com",
         notes="Sells vehicles with home charging; no public network found",
         source="No public network found", verified=0),

    dict(name="WarWizard", aliases="WarWizard EV", segment="Two-wheeler", operates_network=0,
         network_name=None, network_scale="No public charging network",
         connector_standard="Home charging only", partnership=None, app=None, website=None,
         notes="Sells vehicles with home charging; no public network found",
         source="No public network found", verified=0),

    dict(name="Komaki", aliases="Komaki EV", segment="Two-wheeler", operates_network=0,
         network_name=None, network_scale="No public charging network",
         connector_standard="Home charging only", partnership=None, app=None, website=None,
         notes="Sells vehicles with home charging; no public network found",
         source="No public network found", verified=0),
]

# ---------------------------------------------------------------------------
# 2. Operators - only the manufacturers that actually run a network
# ---------------------------------------------------------------------------
OEM_OPERATORS = [
    ("TATA.ev", "OEM charging network", "https://ev.tatamotors.com"),
    ("Hyundai Motor India", "OEM charging network", "https://www.hyundai.com/in/en"),
    ("Kia India", "OEM charging network", "https://www.kia.com/in/"),
    ("MG Charge (JSW MG Motor India)", "OEM charging network", "https://www.mgmotor.co.in"),
    ("CHARGE_iN by Mahindra", "OEM charging network",
     "https://www.mahindraelectricsuv.com/technology/Charge_IN.html"),
    ("Mercedes-Benz India", "OEM charging network", "https://www.mercedes-benz.co.in"),
    ("BMW India", "OEM charging network", "https://www.bmw.in"),
    ("Hero Vida", "OEM charging network", "https://www.heromotocorp.com"),
    ("TVS iQube", "OEM charging network", "https://www.tvsmotor.com"),
    ("Bajaj Chetak", "OEM charging network", "https://www.bajajauto.com"),
    ("Ultraviolette", "OEM charging network", "https://www.ultraviolette.com"),
    ("Simple Energy", "OEM charging network", "https://www.simpleenergy.in"),
    ("BYD India", "OEM charging network", "https://bydindia.in"),
    ("Citroën India", "OEM charging network", "https://www.citroen.in"),
]

# ---------------------------------------------------------------------------
# 3. Stations - ONLY where the manufacturer publishes an actual location.
#    Coordinates are derived from the published address to town/area level,
#    which is why coord_precision says so.
# ---------------------------------------------------------------------------
STATIONS = [
    # --- Mahindra CHARGE_iN (published on the official CHARGE_iN site) ---
    dict(operator="CHARGE_iN by Mahindra", name="CHARGE_iN - Yedenipani, Pune-Bengaluru NH",
         address="Pune-Bengaluru National Highway, Yedenipani, Itkare, Sangli, Maharashtra 415403",
         city="Sangli", state="MH", lat=16.85, lng=74.57, precision="town",
         highway="NH-48", direction="Pune to Bengaluru bound",
         dc_kw=180, dc_qty=2, ccs2=4,
         amenities=["Restroom", "Cafe / Food Court", "Parking", "24x7 Security"]),
    dict(operator="CHARGE_iN by Mahindra", name="CHARGE_iN - Dhilwan, Amritsar-Jalandhar Hwy",
         address="Toll Plaza, Midway Premium Outlets, Amritsar-Jalandhar Highway, near Dhilwan, Vill. Miani, Bakarpur, Dhilwan, Punjab 144804",
         city="Dhilwan", state="PB", lat=31.42, lng=75.33, precision="town",
         highway="NH-3", direction="Amritsar to Jalandhar bound",
         dc_kw=180, dc_qty=2, ccs2=4,
         amenities=["Restroom", "Shopping", "Cafe / Food Court", "Parking"]),
    dict(operator="CHARGE_iN by Mahindra", name="CHARGE_iN - Paota, NH-48 Jaipur-Delhi Expy",
         address="N.H.48, Jaipur-Delhi Expressway, near Paota, Kotputli, Rajasthan 303108",
         city="Kotputli", state="RJ", lat=27.70, lng=76.20, precision="town",
         highway="NH-48", direction="Jaipur to Delhi bound",
         dc_kw=180, dc_qty=2, ccs2=4,
         amenities=["Restroom", "Cafe / Food Court", "Parking"]),
    dict(operator="CHARGE_iN by Mahindra", name="CHARGE_iN - Sajgaon, Mumbai-Pune Expy",
         address="Survey No 13, Mumbai-Pune Expressway, near Khalapur Toll Naka, Sajgaon, Sarsan, Maharashtra 410203",
         city="Khalapur", state="MH", lat=18.80, lng=73.28, precision="town",
         highway="NH-48", direction="Mumbai to Pune bound",
         dc_kw=180, dc_qty=2, ccs2=4,
         amenities=["Restroom", "Cafe / Food Court", "Parking", "Convenience Store"]),
    dict(operator="CHARGE_iN by Mahindra", name="CHARGE_iN - Hoskote, NH-75",
         address="Hoskote, NH-75, Bengaluru-Chennai highway, Karnataka",
         city="Bengaluru", state="KA", lat=13.07, lng=77.79, precision="town",
         highway="NH-75", direction="Bengaluru to Chennai bound",
         dc_kw=180, dc_qty=2, ccs2=4,
         amenities=["Restroom", "Cafe / Food Court", "Parking"]),
    dict(operator="CHARGE_iN by Mahindra", name="CHARGE_iN - Murthal, NH-44",
         address="Murthal, NH-44, approximately 50 km from Delhi, Haryana",
         city="Sonipat", state="HR", lat=29.03, lng=77.05, precision="town",
         highway="NH-44", direction="Delhi to Chandigarh bound",
         dc_kw=180, dc_qty=2, ccs2=4,
         amenities=["Restroom", "Cafe / Food Court", "Parking"]),

    # --- Ola Hypercharger (published on the official Hypercharger page) ---
    dict(operator="Ola Hypercharger", name="Ola Hypercharger - Koramangala",
         address="Ola Campus, 2, Hosur Rd, Koramangala Industrial Layout, Koramangala, Bengaluru, Karnataka 560034",
         city="Bengaluru", state="KA", lat=12.935, lng=77.614, precision="area",
         highway=None, direction=None, dc_kw=50, dc_qty=1, ccs2=0,
         amenities=["Restroom", "Parking"], hours="10:00 - 20:30"),
    dict(operator="Ola Hypercharger", name="Ola Hypercharger - Peenya BPCL",
         address="BPCL Station, Federation of Lorry Owners Assn., Peenya, Bengaluru Urban, Karnataka 560022",
         city="Bengaluru", state="KA", lat=13.03, lng=77.52, precision="area",
         highway=None, direction=None, dc_kw=50, dc_qty=1, ccs2=0,
         amenities=["Restroom", "Parking"], hours="10:00 - 20:30"),
    dict(operator="Ola Hypercharger", name="Ola Hypercharger - Indiranagar",
         address="Ola Experience Centre, 522, 1, Chinmaya Mission Hospital Rd, Stage 1, Indiranagar, Bengaluru, Karnataka 560038",
         city="Bengaluru", state="KA", lat=12.978, lng=77.640, precision="area",
         highway=None, direction=None, dc_kw=50, dc_qty=1, ccs2=0,
         amenities=["Restroom", "Parking"], hours="10:00 - 20:30"),
    dict(operator="Ola Hypercharger", name="Ola Hypercharger - Marathahalli",
         address="Ola Experience Centre, Athidhi Grand Site 310/35, Kadubeesanahalli, opp. Oracle, Bengaluru 560103",
         city="Bengaluru", state="KA", lat=12.94, lng=77.70, precision="area",
         highway=None, direction=None, dc_kw=50, dc_qty=1, ccs2=0,
         amenities=["Restroom", "Parking"], hours="10:00 - 20:30"),
    dict(operator="Ola Hypercharger", name="Ola Hypercharger - Mahadevapura",
         address="Ola Experience Centre, Mahadevapura, Bengaluru, Karnataka",
         city="Bengaluru", state="KA", lat=12.99, lng=77.70, precision="area",
         highway=None, direction=None, dc_kw=50, dc_qty=1, ccs2=0,
         amenities=["Restroom", "Parking"], hours="10:00 - 20:30"),
]

STATE_NAMES = {
    "MH": "Maharashtra", "PB": "Punjab", "RJ": "Rajasthan", "KA": "Karnataka",
    "HR": "Haryana", "DL": "Delhi",
}


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    # --- brands ---
    con.execute("DELETE FROM brands")
    for b in BRANDS:
        con.execute(
            """INSERT INTO brands(name,aliases,segment,operates_network,network_name,
               network_scale,connector_standard,partnership,app,website,notes,source,verified)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (b["name"], b["aliases"], b["segment"], b["operates_network"], b["network_name"],
             b["network_scale"], b["connector_standard"], b["partnership"], b["app"],
             b["website"], b["notes"], b["source"], b["verified"]))
    print(f"brands: {len(BRANDS)} "
          f"({sum(b['operates_network'] for b in BRANDS)} run their own network)")

    # --- operators ---
    added_ops = 0
    for name, kind, site in OEM_OPERATORS:
        if not con.execute("SELECT 1 FROM operators WHERE name=?", (name,)).fetchone():
            con.execute("INSERT INTO operators(name,kind,website) VALUES(?,?,?)",
                        (name, kind, site))
            added_ops += 1
    print(f"operators added: {added_ops}")

    # --- stations ---
    def state_name(code):
        r = con.execute("SELECT name FROM states WHERE code=?", (code,)).fetchone()
        if r:
            return r["name"]
        con.execute("INSERT INTO states(code,name) VALUES(?,?)",
                    (code, STATE_NAMES.get(code, code)))
        return STATE_NAMES.get(code, code)

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
            (city, did, code, 2)).lastrowid

    created = updated = 0
    for s in STATIONS:
        state_name(s["state"])
        op = con.execute("SELECT id,phone,website FROM operators WHERE name=?",
                         (s["operator"],)).fetchone()
        cid = city_id(s["city"], s["state"])
        did = con.execute("SELECT district_id FROM cities WHERE id=?", (cid,)).fetchone()[0]

        total_kw = (s["dc_kw"] or 0) * (s["dc_qty"] or 0)
        gmaps = f"https://www.google.com/maps/search/?api=1&query={s['lat']},{s['lng']}"
        amaps = f"https://maps.apple.com/?ll={s['lat']},{s['lng']}"
        source_label = ("Mahindra CHARGE_iN (official site)" if s["operator"].startswith("CHARGE_iN")
                        else "Ola Electric Hypercharger (official site)")

        existing = con.execute(
            "SELECT id FROM stations WHERE source_id='oem' AND source_ref=?",
            (s["name"],)).fetchone()

        if existing:
            con.execute(
                """UPDATE stations SET name=?, operator_id=?, ownership='Private', access=?
                   , location_type='Highway' , state_code=?, district_id=?, city_id=?, address=?,
                   highway_direction=?, latitude=?, longitude=?, operating_hours=?, is_24x7=?,
                   status='Operational', num_chargers=?, total_capacity_kw=?, max_power_kw=?,
                   amenities=?, google_maps_url=?, apple_maps_url=?, data_source=?,
                   coord_precision=?, last_updated=? WHERE id=?""",
                (s["name"], op["id"], "Public access", s["state"], did, cid, s["address"],
                 s["direction"], s["lat"], s["lng"], s.get("hours", "Open 24 hours"),
                 1 if s.get("hours") is None else 0, s["dc_qty"], total_kw, s["dc_kw"],
                 json.dumps(s["amenities"]), gmaps, amaps, source_label, s["precision"],
                 NOW, existing["id"]))
            sid = existing["id"]
            updated += 1
        else:
            sid = con.execute(
                """INSERT INTO stations(name,operator_id,ownership,access,location_type,
                   state_code,district_id,city_id,address,highway_id,highway_direction,
                   latitude,longitude,operating_hours,is_24x7,status,num_chargers,
                   total_capacity_kw,max_power_kw,amenities,google_maps_url,apple_maps_url,
                   data_source,source_id,source_ref,is_validated,coord_precision,
                   last_updated,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (s["name"], op["id"], "Private", "Public access", "Highway", s["state"],
                 did, cid, s["address"], None, s["direction"], s["lat"], s["lng"],
                 s.get("hours", "Open 24 hours"), 1 if s.get("hours") is None else 0,
                 "Operational", s["dc_qty"], total_kw, s["dc_kw"], json.dumps(s["amenities"]),
                 gmaps, amaps, source_label, "oem", s["name"], 0, s["precision"], NOW, NOW)).lastrowid
            created += 1

        # connectors: clear and re-add so re-runs stay clean
        con.execute("DELETE FROM connectors WHERE station_id=?", (sid,))
        if s["dc_qty"]:
            con.execute(
                """INSERT INTO connectors(station_id,connector_type,formal_name,current_type,
                   power_kw,charging_speed,quantity,status) VALUES(?,?,?,?,?,?,?,?)""",
                (sid, "CCS2" if s["ccs2"] else "Type 6 (LECCS)",
                 "IEC 62196-3 CCS Combo 2" if s["ccs2"] else "IS 17017 Type 6 / LECCS",
                 "DC", s["dc_kw"], "Turbo" if s["dc_kw"] >= 100 else "Fast",
                 s["ccs2"] or s["dc_qty"], "Operational"))

        con.execute("DELETE FROM tariffs WHERE station_id=?", (sid,))
        con.execute(
            """INSERT INTO tariffs(station_id,connector_type,price_per_kwh,session_fee,
               idle_fee_per_min,currency,notes) VALUES(?,?,?,?,?,?,?)""",
            (sid, "CCS2" if s["ccs2"] else "Type 6 (LECCS)", None, 0, 0, "INR",
             "Operator app tariff - not published as a fixed rate"))

        con.execute("DELETE FROM station_payments WHERE station_id=?", (sid,))
        for m in (["UPI", "Credit/Debit Card", "In-app Wallet", "QR Code"]
                  if s["ccs2"] else ["UPI", "In-app Wallet", "QR Code"]):
            con.execute("INSERT INTO station_payments(station_id,method) VALUES(?,?)", (sid, m))

    con.commit()

    n_brands = con.execute("SELECT COUNT(*) FROM brands").fetchone()[0]
    n_net = con.execute("SELECT COUNT(*) FROM brands WHERE operates_network=1").fetchone()[0]
    n_oem_st = con.execute("SELECT COUNT(*) FROM stations WHERE source_id='oem'").fetchone()[0]
    n_total = con.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
    con.close()

    print(f"stations: +{created} created, {updated} updated ({n_oem_st} OEM total)")
    print(f"database now holds {n_total} stations, {n_brands} brands ({n_net} with own networks)")


if __name__ == "__main__":
    main()
