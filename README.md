# EV Charge India

Find EV charging stations across India. Ask the agent in plain language, browse the
map, and see connectors, charging speed, price, payment methods and contact details.

**Live:** https://sree831100225-crypto.github.io/ev-charge-india/

## How this repo works

The site is **generated**, not hand-edited. A GitHub Actions workflow rebuilds the
database and republishes the page **every day at 07:00 IST** (and on every push that
touches the pipeline).

```
build/seed.py         sample seed data (deterministic)
refresh.py            pulls the live e-AMRIT government register
build/add_oem_data.py OEM charging networks (22 vehicle brands)
build/export.py       database -> app/data.js
build/make_share.py   app -> the single self-contained page
```

Run it locally:

```bash
python build/seed.py
python refresh.py
python build/add_oem_data.py
python build/export.py
python build/make_share.py
```

## Data sources

| Source | What it gives | Refresh |
|---|---|---|
| e-AMRIT (NITI Aayog) | Government public charging register, with an `isValidated` flag | Live, daily |
| OEM releases | 22 vehicle brands' charging networks, and Mahindra/Ola published sites | As published |
| Sample seed | Realistic records for coverage where no open data exists | Static |

## Read this before trusting the data

This is a **directory, not a live availability feed**. Coverage is strongest in cities
and on national highways. 29 stations are government-verified; 11 are OEM-published;
the rest are realistic sample records. Coordinates for OEM stations are derived from
the published address to town or area level - see the `coord_precision` column.

Confirm a charger is working in the operator's own app before driving to it.
