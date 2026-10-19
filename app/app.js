/* EV Charge India - PWA prototype logic.
   Data comes from data.js (embedded export of the SQLite DB).
   The agent + search work fully offline; when the FastAPI backend is
   reachable they call it instead, so the same UI runs against live data. */

const DATA = window.EV_DATA || [];
const META = window.EV_META || {};
const API = ""; // same-origin; set to a base URL if the API is elsewhere

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

let state = { speed: "", conn: "", type: "", verified: false, q: "", user: null, map: null, markers: [], chatLoc: null };

/* ---------------- boot ---------------- */
document.addEventListener("DOMContentLoaded", () => {
  // Register the service worker first: it must not be skipped because an
  // unrelated init call threw (e.g. a blocked CDN leaving Leaflet undefined).
  if (navigator.serviceWorker && location.protocol.startsWith("http")) {
    navigator.serviceWorker.register("sw.js").catch(() => {});
  }
  // Each step is isolated so one failure cannot take down the rest of the app.
  [buildChips, renderList, initMap, wireNav, wireLogin, wireDetail, wireChat, wireProfile]
    .forEach(fn => { try { fn(); } catch (e) { console.warn("init step failed:", fn.name, e); } });
});

/* ---------------- login ---------------- */
function wireLogin() {
  const stepMobile = $("#step-mobile"), stepOtp = $("#step-otp");
  let pendingMobile = "";

  $("#btn-send-otp").onclick = async () => {
    const m = $("#mobile").value.replace(/\D/g, "");
    if (m.length !== 10) { alert("Enter a valid 10-digit mobile number"); return; }
    pendingMobile = m;
    $("#otp-to").textContent = "+91 " + m;
    // try backend OTP; fall back to demo code
    let demo = "123456";
    try {
      const r = await fetch(API + "/api/auth/otp/request", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mobile: m })
      });
      if (r.ok) { const j = await r.json(); demo = j.demo_otp || demo; }
    } catch (e) { /* offline demo */ }
    $("#demo-hint").textContent = "Demo OTP: " + demo + " (SMS gateway wires in production)";
    stepMobile.classList.add("hidden");
    stepOtp.classList.remove("hidden");
  };

  $("#btn-back").onclick = () => { stepOtp.classList.add("hidden"); stepMobile.classList.remove("hidden"); };

  $("#btn-verify").onclick = async () => {
    const otp = $("#otp").value.trim();
    let ok = false, token = null;
    try {
      const r = await fetch(API + "/api/auth/otp/verify", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mobile: pendingMobile, otp })
      });
      if (r.ok) { const j = await r.json(); token = j.token; ok = true; }
      else if (r.status === 401) { ok = false; }
    } catch (e) {
      ok = otp === "123456" || otp.length === 6; // offline demo
    }
    if (!ok) { alert("Invalid OTP. Demo code is 123456."); return; }
    state.user = { mobile: pendingMobile, token };
    enterApp();
  };
}

function enterApp() {
  $("#login").classList.remove("active");
  $("#app").classList.add("active");
  $("#avatar").textContent = (state.user?.mobile || "S")[0];
  $("#p-name").textContent = "EV Owner";
  $("#p-mobile").textContent = "+91 " + (state.user?.mobile || "");
  setTimeout(() => {
    if (!state.map) return;
    state.map.invalidateSize();
    renderMarkers(); // re-fit bounds now the map has real dimensions
  }, 250);
}

/* ---------------- nav ---------------- */
function wireNav() {
  $$(".nav-btn").forEach(b => b.onclick = () => {
    $$(".nav-btn").forEach(x => x.classList.remove("active"));
    b.classList.add("active");
    const v = b.dataset.view;
    $$(".view").forEach(x => x.classList.remove("active"));
    $("#view-" + v).classList.add("active");
    $("#topbar-title").textContent = { map: "Find Chargers", list: "All Stations", agent: "Charge Agent", profile: "Profile" }[v];
    if (v === "map") setTimeout(() => { state.map.invalidateSize(); renderMarkers(); }, 150);
    if (v === "agent" && !$("#chat").dataset.init) initChat();
  });
}

/* ---------------- chips ---------------- */
function buildChips() {
  const speedRow = $("#speed-chips");
  ["", "Normal", "Fast", "Turbo"].forEach(s => {
    const c = document.createElement("div");
    c.className = "chip" + (s === "" ? " on" : "");
    c.textContent = s === "" ? "All speeds" : s + (s === "Turbo" ? " ⚡" : "");
    c.onclick = () => { state.speed = s; markChips(speedRow, c); renderList(); renderMarkers(); };
    speedRow.appendChild(c);
  });

  const typeRow = $("#type-chips");
  ["", "Urban", "Highway", "Village / Rural"].forEach(t => {
    const c = document.createElement("div");
    c.className = "chip" + (t === "" ? " on" : "");
    c.textContent = t === "" ? "All locations" : t.replace(" / Rural", "");
    c.onclick = () => { state.type = t; markChips(typeRow, c); renderList(); renderMarkers(); };
    typeRow.appendChild(c);
  });
  const vchip = document.createElement("div");
  vchip.className = "chip keep";
  vchip.textContent = "✓ Govt verified";
  vchip.onclick = () => { state.verified = !state.verified; vchip.classList.toggle("on", state.verified); renderList(); renderMarkers(); };
  typeRow.appendChild(vchip);

  const connRow = $("#conn-chips");
  const types = META.connectors || [];
  [""].concat(types).forEach(t => {
    const c = document.createElement("div");
    c.className = "chip" + (t === "" ? " on" : "");
    c.textContent = t === "" ? "All connectors" : t;
    c.onclick = () => { state.conn = t; markChips(connRow, c); renderList(); renderMarkers(); };
    connRow.appendChild(c);
  });

  $("#map-search").oninput = e => { state.q = e.target.value; $("#list-search").value = e.target.value; renderMarkers(); renderList(); };
  $("#list-search").oninput = e => { state.q = e.target.value; $("#map-search").value = e.target.value; renderList(); renderMarkers(); };
}

function markChips(row, el) { $$(".chip", row).forEach(c => { if (!c.classList.contains("keep")) c.classList.remove("on"); }); el.classList.add("on"); }

/* ---------------- filtering ---------------- */
function filtered() {
  const q = state.q.toLowerCase().trim();
  return DATA.filter(s => {
    if (state.speed && !s.connectors.some(c => c.speed === state.speed)) return false;
    if (state.conn && !s.connectors.some(c => c.type === state.conn)) return false;
    if (state.type && s.location_type !== state.type) return false;
    if (state.verified && !s.is_validated) return false;
    if (q) {
      const hay = [s.name, s.city, s.state, s.operator, s.highway, s.village, s.address, s.district].filter(Boolean).join(" ").toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

/* ---------------- map ---------------- */
function initMap() {
  if (typeof L === "undefined") { console.warn("Leaflet not loaded - map disabled"); return; }
  state.map = L.map("map", { zoomControl: false, attributionControl: false }).setView([22.5, 79], 5);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18 }).addTo(state.map);
  L.control.zoom({ position: "bottomright" }).addTo(state.map);
  renderMarkers();
}

function markerColor(s) {
  if (s.connectors.some(c => c.speed === "Turbo")) return "#B42318";
  if (s.connectors.some(c => c.speed === "Fast")) return "#C77700";
  return "#1A56A8";
}

function renderMarkers() {
  if (!state.map || typeof L === "undefined") return;
  state.markers.forEach(m => state.map.removeLayer(m));
  state.markers = [];
  const rows = filtered();
  rows.forEach(s => {
    const m = L.circleMarker([s.latitude, s.longitude], {
      radius: 6, color: "#fff", weight: 1.5, fillColor: markerColor(s), fillOpacity: .95
    });
    m.bindPopup(popupHtml(s));
    m.on("popupopen", e => {
      const btn = e.popup.getElement().querySelector(".pop-open");
      if (btn) btn.onclick = () => openDetail(s.id);
    });
    m.addTo(state.map);
    state.markers.push(m);
  });
  $("#map-count").textContent = rows.length;
  if (rows.length && state.markers.length) {
    try { state.map.fitBounds(L.featureGroup(state.markers).getBounds().pad(0.2)); } catch (e) {}
  }
}

function popupHtml(s) {
  const speeds = [...new Set(s.connectors.map(c => c.speed))].join(" · ");
  return `<div class="pop-name">${esc(s.name)}</div>
    <div class="pop-sub">${esc(s.city)}, ${esc(s.state)}<br>${speeds} · ${s.max_power_kw} kW max</div>
    <button class="pop-btn pop-open">View details</button>`;
}

/* ---------------- list ---------------- */
function renderList() {
  const loc = state.chatLoc;
  let rows = filtered().slice();
  if (loc) {
    // with a location active, nearest-first is what the user wants
    rows = rows
      .map(s => s.latitude != null
        ? { ...s, distance_km: haversine(loc.lat, loc.lng, s.latitude, s.longitude) } : s)
      .sort((a, b) => (a.distance_km ?? 1e9) - (b.distance_km ?? 1e9));
  } else {
    rows.sort((a, b) => b.max_power_kw - a.max_power_kw);
  }
  const box = $("#list-results");
  if (!rows.length) { box.innerHTML = `<div class="empty">No stations match these filters.<br>Try clearing a filter.</div>`; return; }
  box.innerHTML = rows.map(s => {
    const minP = s.tariffs.length ? Math.min(...s.tariffs.map(t => t.price_per_kwh)) : null;
    const speeds = [...new Set(s.connectors.map(c => c.speed))];
    const badgeCls = s.location_type.startsWith("Village") ? "Village" : s.location_type;
    return `<div class="card" data-id="${s.id}">
      <div class="card-top">
        <div>
          <div class="card-name">${esc(s.name)}</div>
          <div class="card-loc">${esc(s.city)}, ${esc(s.state)}${s.highway ? " · " + esc(s.highway) : ""}${s.village ? " · " + esc(s.village) : ""}${s.distance_km != null ? ' · <span class="dist">' + s.distance_km.toFixed(1) + " km</span>" : ""}</div>
        </div>
        <span class="badge ${badgeCls}">${esc(s.location_type.replace(" / Rural", ""))}</span>
      </div>
      ${s.is_validated ? '<div class="card-tags" style="margin-top:6px"><span class="tag verified">✓ Govt verified · ' + esc(s.data_source || '') + '</span></div>' : ''}
      ${s.source_id === 'oem' ? '<div class="card-tags" style="margin-top:6px"><span class="tag verified">OEM published · ' + esc(s.data_source || '') + '</span></div>' : ''}
      <div class="card-tags">
        ${speeds.map(sp => `<span class="tag ${sp.toLowerCase()}">${sp}</span>`).join("")}
        ${s.max_power_kw ? `<span class="tag">${s.max_power_kw} kW</span>` : ''}
        ${s.connectors.slice(0, 2).map(c => `<span class="tag">${esc(c.type)}</span>`).join("")}
        ${!s.connectors.length ? '<span class="tag">Connector data not reported</span>' : ''}
        <span class="tag">${esc(s.operator)}</span>
      </div>
      <div class="card-foot">
        <span class="price">${minP === 0 ? "Free" : (minP ? "₹" + minP + "/kWh" : "Tariff not reported")}</span>
        <span class="badge ${s.status === "Operational" ? "Operational" : (s.status === "Coming soon" ? "soon" : "maintenance")}">${esc(s.status)}</span>
      </div>
    </div>`;
  }).join("");
  $$(".card", box).forEach(c => c.onclick = () => openDetail(+c.dataset.id));
}

/* ---------------- detail ---------------- */
function wireDetail() { $("#detail-close").onclick = () => $("#detail").classList.remove("open"); }

function openDetail(id) {
  const s = DATA.find(x => x.id === id);
  if (!s) return;
  const b = $("#detail-body");
  b.innerHTML = `
    <div class="d-head">
      <h2 class="d-title">${esc(s.name)}</h2>
      <div class="d-sub">${esc(s.operator)} · ${esc(s.operator_kind)}</div>
      <div class="d-badges">
        <span class="badge ${s.location_type.startsWith("Village") ? "Village" : s.location_type}">${esc(s.location_type)}</span>
        <span class="badge ${s.ownership === "Public" ? "Operational" : "maintenance"}">${esc(s.ownership)}</span>
        <span class="badge ${s.status === "Operational" ? "Operational" : (s.status === "Coming soon" ? "soon" : "maintenance")}">${esc(s.status)}</span>
      </div>
    </div>

    <div class="d-section">
      <h3>Location</h3>
      <div class="d-row"><span>Address</span><b>${esc(s.address)}</b></div>
      <div class="d-row"><span>City</span><b>${esc(s.city)}</b></div>
      <div class="d-row"><span>District</span><b>${esc(s.district)}</b></div>
      <div class="d-row"><span>State</span><b>${esc(s.state)}</b></div>
      ${s.panchayat ? `<div class="d-row"><span>Panchayat</span><b>${esc(s.panchayat)}</b></div>` : ""}
      ${s.village ? `<div class="d-row"><span>Village</span><b>${esc(s.village)}</b></div>` : ""}
      ${s.highway ? `<div class="d-row"><span>Highway</span><b>${esc(s.highway)}</b></div>` : ""}
      ${s.highway_direction ? `<div class="d-row"><span>Direction</span><b>${esc(s.highway_direction)}</b></div>` : ""}
      <div class="d-row"><span>Coordinates</span><b>${s.latitude.toFixed(4)}, ${s.longitude.toFixed(4)}</b></div>
      <div class="map-btns">
        <a class="map-btn g" href="${s.google_maps_url}" target="_blank" rel="noopener">Google Maps</a>
        <a class="map-btn" href="${s.apple_maps_url}" target="_blank" rel="noopener">Apple Maps</a>
      </div>
    </div>

    <div class="d-section">
      <h3>Chargers &amp; connectors</h3>
      ${s.connectors.length ? s.connectors.map(c => `
        <div class="conn">
          <div class="conn-top">
            <span class="conn-name">${esc(c.type)} <span style="font-weight:500;color:var(--muted)">×${c.quantity}</span></span>
            <span class="pill ${c.speed}">${c.speed}</span>
          </div>
          <div class="conn-meta">${esc(c.formal)} · ${c.current} · ${c.power_kw} kW</div>
        </div>`).join("") : '<p class="fineprint" style="margin-top:0">This source does not publish connector or power data. Merge the BEE charger-level dataset to fill it in.</p>'}
      ${s.max_power_kw ? `<div class="d-row"><span>Max power</span><b>${s.max_power_kw} kW</b></div>` : ''}
      ${s.total_capacity_kw ? `<div class="d-row"><span>Total capacity</span><b>${s.total_capacity_kw} kW</b></div>` : ''}
    </div>

    <div class="d-section">
      <h3>Tariff</h3>
      ${s.tariffs.map(t => `<div class="d-row"><span>${esc(t.connector_type || 'Standard')}</span>
        <b>${t.price_per_kwh === 0 ? 'Free of charge' : '₹' + t.price_per_kwh + '/kWh'}${t.session_fee ? " + ₹" + t.session_fee + " session" : ""}${t.idle_fee_per_min ? " + ₹" + t.idle_fee_per_min + "/min idle" : ""}</b></div>`).join("") || '<p class="fineprint" style="margin-top:0">Tariff not reported by this source.</p>'}
      <p class="fineprint">Indicative tariff. Confirm the live rate in the operator's app before you plug in.</p>
    </div>

    <div class="d-section">
      <h3>Payment methods</h3>
      <div class="pay-grid">${s.payments.map(p => `<span class="pay-chip">${esc(p)}</span>`).join("")}</div>
    </div>

    <div class="d-section">
      <h3>Amenities</h3>
      <div class="amen-grid">${s.amenities.map(a => `<span class="amen-chip">${esc(a)}</span>`).join("")}</div>
    </div>

    <div class="d-section">
      <h3>Contact &amp; hours</h3>
      <div class="d-row"><span>Station phone</span><b>${esc(s.contact_phone || '—')}</b></div>
      ${s.contact_email ? `<div class="d-row"><span>Email</span><b>${esc(s.contact_email)}</b></div>` : ""}
      <div class="d-row"><span>Operator helpline</span><b>${esc(s.operator_phone || '—')}</b></div>
      <div class="d-row"><span>Hours</span><b>${esc(s.operating_hours)}</b></div>
      <div class="d-row"><span>Operator site</span><b>${s.operator_website ? `<a href="${s.operator_website}" target="_blank" rel="noopener">${esc(s.operator_website.replace(/^https?:\/\//, ""))}</a>` : '—'}</b></div>
      <a class="contact-btn" href="tel:${(s.contact_phone || "").replace(/\s/g, "")}">Call station</a>
    </div>

    <div class="d-section">
      <h3>Data</h3>
      <div class="d-row"><span>Last updated</span><b>${fmtTime(s.last_updated)}</b></div>
      <div class="d-row"><span>Source</span><b>${esc(s.data_source || 'Sample dataset')}</b></div>
      <div class="d-row"><span>Verification</span><b>${s.is_validated ? '✓ Verified (government register)' : 'Unverified sample'}</b></div>
      ${s.source_ref ? `<div class="d-row"><span>Source record</span><b>${esc(s.source_id || '')} #${esc(s.source_ref)}</b></div>` : ''}
    </div>`;
  $("#detail").classList.add("open");
  b.scrollTop = 0;
}

/* ---------------- agent ---------------- */
function initChat() {
  $("#chat").dataset.init = "1";
  botSay("Namaste! I'm your EV Charge agent. Ask me about chargers anywhere in India — by city, highway, connector, speed or price.", []);
  const sugs = ["Chargers near me", "Turbo chargers on NH-48", "Cheapest charging in Jaipur", "CCS2 stations in Pune", "Rural stations in Haryana"];
  $("#chat-suggest").innerHTML = sugs.map(s => `<div class="sug">${esc(s)}</div>`).join("");
  $$(".sug").forEach(el => el.onclick = () => { $("#chat-text").value = el.textContent; $("#chat-form").requestSubmit(); });
}

function wireChat() {
  $("#chat-form").onsubmit = async e => {
    e.preventDefault();
    const q = $("#chat-text").value.trim();
    if (!q) return;
    $("#chat-text").value = "";
    userSay(q);
    const t = botTyping();
    let res = null;
    try {
      const r = await fetch(API + "/api/agent/query", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q, lat: state.chatLoc && state.chatLoc.lat,
                               lng: state.chatLoc && state.chatLoc.lng })
      });
      if (r.ok) res = await r.json();
    } catch (e) { /* offline */ }
    if (!res) res = localAgent(q, state.chatLoc);
    t.remove();
    botSay(res.answer, res.stations || []);
  };

  // --- location controls ---
  const gps = $("#btn-loc-gps");
  if (gps) gps.onclick = () => useMyLocation();

  const clr = $("#btn-loc-clear");
  if (clr) clr.onclick = () => {
    setChatLoc(null);
    botSay("Cleared your location. Ask about any city, highway or operator.", []);
  };

  const li = $("#loc-input");
  if (li) li.onkeydown = ev => {
    if (ev.key !== "Enter") return;
    ev.preventDefault();
    const txt = li.value.trim();
    if (!txt) return;
    const loc = resolvePlace(txt);
    if (!loc) {
      botSay(`I don't recognise \u201c${txt}\u201d. Try a city like Pune, an area like ` +
             `Koramangala, a state, or a 6-digit PIN code.`, []);
      return;
    }
    li.value = "";
    setChatLoc(loc);
    botSay(`Searching around ${loc.label} \u2014 here are the closest chargers.`, nearestStations(5));
  };
}

function userSay(t) { const d = document.createElement("div"); d.className = "msg user"; d.textContent = t; $("#chat").appendChild(d); scrollChat(); }
function botSay(t, stations) {
  const d = document.createElement("div"); d.className = "msg bot";
  let html = esc(t);
  (stations || []).slice(0, 5).forEach(s => {
    const dist = s.distance_km != null ? `<span class="dist"> · ${s.distance_km.toFixed(1)} km</span>` : "";
    html += `<span class="mini-card" data-id="${s.id}"><b>${esc(s.name)}</b><small>${esc(s.city || "")}, ${esc(s.state || "")}${dist}${s.max_power_kw ? " · " + s.max_power_kw + " kW" : ""}${s.min_price ? " · ₹" + s.min_price + "/kWh" : ""}</small></span>`;
  });
  d.innerHTML = html;
  $("#chat").appendChild(d); scrollChat();
  $$(".mini-card", d).forEach(el => el.onclick = () => { openDetail(+el.dataset.id); });
}
function botTyping() {
  const d = document.createElement("div"); d.className = "msg bot";
  d.innerHTML = `<span class="typing"><i></i><i></i><i></i></span>`;
  $("#chat").appendChild(d); scrollChat(); return d;
}
function scrollChat() { const c = $("#chat"); c.scrollTop = c.scrollHeight; }

/* offline agent: mirrors the Python engine in agent.py */
/* ---------------- location ---------------- */
const R_EARTH_KM = 6371;

function haversine(lat1, lon1, lat2, lon2) {
  const rad = d => (d * Math.PI) / 180;
  const dLat = rad(lat2 - lat1), dLon = rad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2 +
            Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * R_EARTH_KM * Math.asin(Math.min(1, Math.sqrt(a)));
}

function stateCentroid(code) {
  const pts = DATA.filter(s => s.state_code === code && s.latitude != null);
  if (!pts.length) return null;
  return {
    lat: pts.reduce((a, s) => a + s.latitude, 0) / pts.length,
    lng: pts.reduce((a, s) => a + s.longitude, 0) / pts.length,
  };
}

/* Turn whatever the user typed into coordinates. Tried in order:
   PIN code -> city name -> area/landmark in a station name or address -> state. */
function resolvePlace(text) {
  const raw = (text || "").trim();
  if (!raw) return null;
  const q = raw.toLowerCase();

  const pin = raw.match(/\b\d{6}\b/);
  if (pin) {
    const hit = DATA.find(s => (s.address || "").includes(pin[0]));
    if (hit && hit.latitude != null)
      return { lat: hit.latitude, lng: hit.longitude, label: `PIN ${pin[0]}`, source: "place" };
  }

  const cities = META.cities || [];
  const city = cities.find(c => c.name.toLowerCase() === q)
            || cities.find(c => c.name.toLowerCase().startsWith(q))
            || cities.find(c => c.name.toLowerCase().includes(q));
  if (city) return { lat: city.latitude, lng: city.longitude, label: city.name, source: "place" };

  const sn = (META.states || []).find(s => s.name.toLowerCase() === q || s.code.toLowerCase() === q);
  if (sn) {
    const c = stateCentroid(sn.code);
    if (c) return { ...c, label: sn.name, source: "place" };
  }
  const st = DATA.find(s => (s.name || "").toLowerCase().includes(q))
          || DATA.find(s => (s.address || "").toLowerCase().includes(q))
          || DATA.find(s => (s.city || "").toLowerCase().includes(q));
  if (st && st.latitude != null)
    return { lat: st.latitude, lng: st.longitude, label: st.city || st.name, source: "place" };

  return null;
}

function setChatLoc(loc) {
  state.chatLoc = loc;
  const chip = $("#loc-active"), label = $("#loc-label");
  if (chip && label) {
    if (loc) {
      label.textContent = loc.source === "gps"
        ? `Using your current location (${loc.lat.toFixed(3)}, ${loc.lng.toFixed(3)})`
        : `Searching around ${loc.label}`;
      chip.hidden = false;
    } else {
      chip.hidden = true;
    }
  }
  try { renderList(); renderMarkers(); } catch (e) { /* not ready yet */ }
}

function nearestStations(n) {
  if (!state.chatLoc) return [];
  return DATA.filter(s => s.latitude != null)
    .map(s => ({ ...s, distance_km: haversine(state.chatLoc.lat, state.chatLoc.lng, s.latitude, s.longitude) }))
    .sort((a, b) => a.distance_km - b.distance_km)
    .slice(0, n);
}

function useMyLocation() {
  const chip = $("#loc-active"), label = $("#loc-label");
  if (!navigator.geolocation) {
    botSay("This browser can't share a location. Type a city, area or PIN code instead.", []);
    return;
  }
  if (!window.isSecureContext) {
    botSay("Sharing a location needs a secure (https) page. Type a city, area or PIN code instead.", []);
    return;
  }
  const btn = $("#btn-loc-gps");
  if (btn) btn.disabled = true;
  if (chip && label) { label.textContent = "Getting your location…"; chip.hidden = false; }

  navigator.geolocation.getCurrentPosition(
    p => {
      if (btn) btn.disabled = false;
      setChatLoc({ lat: p.coords.latitude, lng: p.coords.longitude,
                   label: "Current location", source: "gps" });
      const near = nearestStations(5);
      botSay(near.length
        ? `Got it — here are the chargers closest to you, nearest first.`
        : `Got your location, but I have no stations with coordinates near you yet.`,
        near);
    },
    err => {
      if (btn) btn.disabled = false;
      if (chip) chip.hidden = true;
      botSay(err && err.code === 1
        ? "Location permission was denied. Type a city, area or PIN code instead."
        : "I couldn't get your location just now. Type a city, area or PIN code instead.", []);
    },
    { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
  );
}

function localAgent(q, loc) {
  const ql = q.toLowerCase();
  const f = {};
  const speedMap = { turbo: "Turbo", ultra: "Turbo", hyper: "Turbo", rapid: "Fast", fast: "Fast", normal: "Normal", slow: "Normal" };
  for (const w in speedMap) if (new RegExp("\\b" + w + "\\b").test(ql)) { f.speed = speedMap[w]; break; }
  const connMap = { ccs2: "CCS2", ccs: "CCS2", chademo: "CHAdeMO", "type 2": "Type 2 AC", "type 1": "Type 1 AC", "bharat dc": "Bharat DC-001", "dc-001": "Bharat DC-001", "bharat ac": "Bharat AC-001", gbt: "GB/T", "gb/t": "GB/T" };
  for (const w in connMap) if (ql.includes(w)) { f.conn = connMap[w]; break; }
  if (/private/.test(ql)) f.ownership = "Private"; else if (/public/.test(ql)) f.ownership = "Public";
  if (/\b(rural|village|panchayat)\b/.test(ql)) f.type = "Village / Rural";
  else if (/highway/.test(ql)) f.type = "Highway";
  const hm = ql.match(/\bnh[\s-]?(\d{1,3})\b/); if (hm) f.highway = "NH-" + hm[1];
  if (/cheap|lowest|affordable|budget/.test(ql)) f.cheap = true;
  if (/nearest|near me|nearby|around me/.test(ql)) f.near = true;
  if (/upi/.test(ql)) f.pay = "UPI";
  const op = (META.operators || []).map(o => o.name).sort((a, b) => b.length - a.length).find(o => {
    const ol = o.toLowerCase(), parts = ol.split(" "), first = parts[0], head = parts.slice(0, 2).join(" ");
    const esc = first.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return ql.includes(ol) || (head.length > 3 && ql.includes(head)) || (first.length >= 3 && new RegExp("\\b" + esc + "\\b").test(ql));
  });
  if (op) f.operator = op;
  const st = (META.states || []).find(s => new RegExp("\\b" + s.name.toLowerCase() + "\\b").test(ql));
  if (st) f.state = st.name;
  const city = (META.cities || []).map(c => c.name).sort((a, b) => b.length - a.length).find(c => new RegExp("\\b" + c.toLowerCase() + "\\b").test(ql));
  if (city) f.city = city;

  let rows = DATA.filter(s => {
    if (f.speed && !s.connectors.some(c => c.speed === f.speed)) return false;
    if (f.conn && !s.connectors.some(c => c.type === f.conn)) return false;
    if (f.ownership && s.ownership !== f.ownership) return false;
    if (f.type && s.location_type !== f.type) return false;
    if (f.highway && s.highway !== f.highway) return false;
    if (f.pay && !s.payments.includes(f.pay)) return false;
    if (f.operator && s.operator !== f.operator) return false;
    if (f.state && s.state !== f.state) return false;
    if (f.city && s.city !== f.city) return false;
    return true;
  });
  // "near me" with no location yet: ask for one rather than guessing
  if (f.near && !loc) {
    return { needLoc: true, stations: [],
      answer: "Happy to find chargers near you. Tap 📍 Use my location, or type a city, area or PIN code in the box below." };
  }

  rows = rows.map(s => {
    const o = { ...s, min_price: s.tariffs.length ? Math.min(...s.tariffs.map(t => t.price_per_kwh)) : null };
    if (loc && s.latitude != null && s.longitude != null)
      o.distance_km = haversine(loc.lat, loc.lng, s.latitude, s.longitude);
    return o;
  });

  if (f.cheap) rows.sort((a, b) => (a.min_price || 99) - (b.min_price || 99));
  else if (loc) rows.sort((a, b) => (a.distance_km ?? 1e9) - (b.distance_km ?? 1e9));
  else rows.sort((a, b) => b.max_power_kw - a.max_power_kw);

  const nearTxt = loc
    ? (loc.source === "gps" ? "near your current location" : "near " + loc.label)
    : (f.near ? "near you" : "");
  const desc = [f.speed ? f.speed.toLowerCase() + "-charging" : "", f.conn || "", f.city ? "in " + f.city : (f.state ? "in " + f.state : ""), f.highway ? "on " + f.highway : "", f.operator ? "operated by " + f.operator : "", f.type ? f.type.toLowerCase() + " locations" : "", f.pay ? "accepting " + f.pay : "", nearTxt].filter(Boolean).join(" ");
  if (!rows.length) return { answer: `I couldn't find any stations matching ${desc || "that"}. Try a nearby city or a broader filter.`, stations: [] };
  let ans = `${rows.length === 1 ? "Here is 1 station" : "Here are " + rows.length + " stations"} ${desc}.`;
  if (f.cheap && rows[0].min_price) ans += ` Cheapest is ${rows[0].name} at ₹${rows[0].min_price}/kWh.`;
  else if (loc && rows[0].distance_km != null) ans += ` Closest is ${rows[0].name}, ${rows[0].distance_km.toFixed(1)} km away.`;
  return { answer: ans, stations: rows.slice(0, 5) };
}

/* ---------------- brand networks ---------------- */
function renderBrands() {
  const box = $("#brand-list");
  if (!box) return;
  const brands = (META.brands || []);
  if (!brands.length) { box.innerHTML = ''; return; }
  const own = brands.filter(b => b.operates_network).length;
  const partner = brands.filter(b => !b.operates_network && b.partnership &&
    !/no public network|own dealer/i.test(b.partnership)).length;
  $("#brands-sub").textContent =
    `${brands.length} vehicle brands mapped. ${own} run their own public charging network, ` +
    `${partner} rely on a charging partner, the rest have no public network.`;

  box.innerHTML = brands.map(b => {
    const isOwn = !!b.operates_network;
    const hasPartner = b.partnership && !/no public network|own dealer/i.test(b.partnership);
    const cls = isOwn ? 'own' : (hasPartner ? 'partner' : 'none');
    const label = isOwn ? 'Own network' : (hasPartner ? 'Partner network' : 'No public network');
    const net = isOwn
      ? `<div class="bc-net"><b>${esc(b.network_name || '')}</b></div>`
      : (hasPartner ? `<div class="bc-net">Charging via <b>${esc(b.partnership)}</b></div>` : '');
    const meta = [b.connector_standard, b.app, b.website ? b.website.replace(/^https?:\/\//, '') : null]
      .filter(Boolean).join(' · ');
    return `<div class="brandcard">
      <div class="bc-top">
        <div>
          <div class="bc-name">${esc(b.name)}</div>
          <div class="bc-seg">${esc(b.segment || '')}</div>
        </div>
        <span class="bc-pill ${cls}">${label}</span>
      </div>
      ${net}
      ${b.network_scale ? `<div class="bc-scale">${esc(b.network_scale)}</div>` : ''}
      ${meta ? `<div class="bc-meta">${esc(meta)}</div>` : ''}
    </div>`;
  }).join('');
}

/* ---------------- profile ---------------- */
function wireProfile() {
  renderBrands();
  const counts = {
    stations: DATA.length,
    cities: new Set(DATA.map(s => s.city)).size,
    operators: new Set(DATA.map(s => s.operator)).size,
    verified: DATA.filter(s => s.is_validated).length,
    oem: DATA.filter(s => s.source_id === 'oem').length,
    brands: (META.brands || []).length
  };
  $("#stat-grid").innerHTML = `
    <div class="stat"><b>${counts.stations}</b><span>Stations</span></div>
    <div class="stat"><b>${counts.verified}</b><span>Govt-verified</span></div>
    <div class="stat"><b>${counts.brands}</b><span>Vehicle brands</span></div>
    <div class="stat"><b>${counts.oem}</b><span>OEM-published</span></div>`;
  const latest = DATA.reduce((a, s) => s.last_updated > a ? s.last_updated : a, "");
  $("#p-refresh").textContent = fmtTime(latest);
  $("#btn-logout").onclick = () => {
    state.user = null;
    $("#app").classList.remove("active");
    $("#login").classList.add("active");
    $("#mobile").value = ""; $("#otp").value = "";
    $("#step-otp").classList.add("hidden"); $("#step-mobile").classList.remove("hidden");
  };
  $("#btn-locate").onclick = () => {
    if (!navigator.geolocation) { alert("Location not available"); return; }
    if (!state.map || typeof L === "undefined") { alert("Map is unavailable right now."); return; }
    navigator.geolocation.getCurrentPosition(p => {
      const { latitude, longitude } = p.coords;
      $$(".nav-btn").forEach(x => x.classList.remove("active"));
      $('.nav-btn[data-view="map"]').classList.add("active");
      $$(".view").forEach(x => x.classList.remove("active"));
      $("#view-map").classList.add("active");
      $("#topbar-title").textContent = "Find Chargers";
      setTimeout(() => { state.map.invalidateSize(); state.map.setView([latitude, longitude], 11); }, 200);
      const near = DATA.map(s => ({ s, d: haversine(latitude, longitude, s.latitude, s.longitude) }))
        .sort((a, b) => a.d - b.d).slice(0, 5);
      L.popup().setLatLng([latitude, longitude]).setContent("<b>You are here</b>").openOn(state.map);
      near.forEach(n => L.circleMarker([n.s.latitude, n.s.longitude], { radius: 9, color: "#0B8A5E", weight: 3, fill: false }).addTo(state.map));
    }, () => alert("Could not get your location."));
  };
}

/* ---------------- helpers ---------------- */
function haversine(a, b, c, d) {
  const R = 6371, r = Math.PI / 180;
  const dp = (c - a) * r, dl = (d - b) * r;
  const x = Math.sin(dp / 2) ** 2 + Math.cos(a * r) * Math.cos(c * r) * Math.sin(dl / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(x));
}
function esc(s) { return String(s ?? "").replace(/[&<>"']/g, m => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m])); }
function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso), now = new Date(), mins = Math.round((now - d) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return mins + " min ago";
  const h = Math.round(mins / 60);
  if (h < 24) return h + " h ago";
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}
