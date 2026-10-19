# EV Charge India

Find EV charging stations across India. Ask the agent in plain language, browse the
map, and see connectors, charging speed, price, payment methods and contact details.

**Live:** https://sree831100225-crypto.github.io/ev-charge-india/

## How this repo works

The site is **generated**, not hand-edited. A GitHub Actions workflow rebuilds the
database and republishes the page **every day at 07:00 IST**, and on every push that
touches the pipeline.

```
build/seed.py         sample seed data (deterministic)
refresh.py            pulls the live sources below
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

## Live data - action required

The daily job runs and deploys correctly, but **as shipped it imports no new records**,
because both live sources are currently unreachable from GitHub's US runners:

| Source | Result from CI | Why |
|---|---|---|
| e-AMRIT (NITI Aayog) | `URLError: timed out` | Indian government host; blocks non-Indian datacentre IPs |
| Open Charge Map | `HTTP 403 Forbidden` | Requires a free API key |

The workflow warns loudly in the Actions log when this happens, so it will not
silently look healthy.

### To turn on live refreshes (2 minutes, free)

1. Register for an API key at https://openchargemap.org/site/develop/api
2. In this repo: **Settings -> Secrets and variables -> Actions -> New repository secret**
3. Name it `OCM_API_KEY`, paste the key, save
4. Go to **Actions -> Daily data refresh -> Run workflow**

The next run will pull live records. The workflow already reads the secret.

If you would rather use e-AMRIT, run the pipeline from a server with an Indian IP -
the adapter already handles it, and falls back to a checked-in snapshot otherwise.

## Data sources

| Source | What it gives | Status |
|---|---|---|
| Open Charge Map | Community EV charging POIs for India | Needs `OCM_API_KEY` |
| e-AMRIT (NITI Aayog) | Government public charging register with an `isValidated` flag | Geo-blocked from CI |
| OEM releases | 22 vehicle brands' charging networks, plus Mahindra and Ola published sites | Static |
| Sample seed | Realistic records where no open data exists | Static |

## Read this before trusting the data

This is a **directory, not a live availability feed**. Coverage is strongest in cities
and on national highways. 29 stations are government-verified, 11 are OEM-published,
the rest are realistic sample records. Coordinates for OEM stations are derived from
the published address to town or area level - see the `coord_precision` column.

Confirm a charger is working in the operator's own app before driving to it.
