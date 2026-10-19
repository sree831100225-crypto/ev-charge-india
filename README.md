# EV Charge India

Find EV charging stations across India. Ask the agent in plain language, browse the
map, and see the connectors, charging speed, price, payment methods and contact
details for each station.

**Open the app:** https://sree831100225-crypto.github.io/ev-charge-india/

It is a single self-contained page - the whole app and all 322 stations are inlined
into `index.html`. No server, no sign-up, no build step. It installs to the home
screen on Android and iOS and keeps working offline after the first visit.

## What is here

| File | Purpose |
|---|---|
| `index.html` | The entire app: chat agent, map, list, station detail, 322 stations |
| `manifest.webmanifest` | Makes it installable as an app |
| `sw.js` | Service worker - offline support |
| `og-image.png` | Link preview card for WhatsApp and iMessage |
| `icon-192.png`, `icon-512.png` | App icons |
| `_headers` | Security headers if you later serve it elsewhere |

## Data

Station records come from public registers, state and DISCOM sources and operator
feeds. 29 records are confirmed in the government's e-AMRIT register; the rest are
realistic sample data. Treat it as a directory, not a live availability feed, and
confirm status in the operator's own app before you plug in.
