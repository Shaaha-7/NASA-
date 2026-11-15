// MarsPath mission dashboard. Every number shown comes from the backend; missing data is shown as "n/a".
const API = "/api/v1";
const NA = "n/a";
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (v, d = 1, u = "") => (v === null || v === undefined || Number.isNaN(+v) ? NA : (+v).toFixed(d) + u);
const hm = (min) => (min === null || min === undefined ? NA : `${Math.floor(min / 60)} h ${String(Math.round(min % 60)).padStart(2, "0")} m`);
async function api(path, opts) {
  const r = await fetch(API + path, { headers: { "Content-Type": "application/json" }, ...opts });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j?.detail?.message || j?.detail?.errors?.[0]?.message || `Request failed (${r.status})`);
  return j;
}

const ICONS = {
  map: "M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2zM9 4v14M15 6v14", check: "M4 5h16v14H4zM8 12l3 3 5-6", shield: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6zM9 12l2 2 4-4",
  spark: "M12 3v6M12 15v6M3 12h6M15 12h6M6 6l3 3M15 15l3 3M18 6l-3 3M9 15l-3 3", download: "M12 4v11M7 11l5 5 5-5M4 20h16", layers: "M12 3l9 5-9 5-9-5zM3 13l9 5 9-5M3 17l9 5 9-5",
  target: "M12 12m-7 0a7 7 0 1 0 14 0a7 7 0 1 0-14 0M12 12m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0M12 2v3M12 19v3M2 12h3M19 12h3", mountain: "M3 19l6-10 4 6 2-3 6 7zM3 19h18",
  expand: "M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5", leaf: "M5 19c0-9 5-14 15-14 0 10-5 15-14 15zM5 19l8-8", gauge: "M4 17a8 8 0 1 1 16 0M12 17l4-6", path: "M5 18m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0M19 6m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0M7 17c5-1 3-9 10-10",
  scale: "M12 4v16M5 8h14M5 8l-2 6h4zM19 8l-2 6h4zM8 20h8", chart: "M4 20V5M4 20h16M7 15l4-5 3 3 5-7", flask: "M9 3h6M10 3v6l-5 10a1 1 0 0 0 1 2h12a1 1 0 0 0 1-2l-5-10V3M8 15h8",
  suit: "M12 3a3 3 0 0 1 3 3v1h2l2 5-3 1v8H8v-8l-3-1 2-5h2V6a3 3 0 0 1 3-3z", camera: "M4 8h3l2-3h6l2 3h3v11H4zM12 13m-3 0a3 3 0 1 0 6 0a3 3 0 1 0-6 0", cloud: "M7 18a4 4 0 0 1 0-8 5 5 0 0 1 10 0 4 4 0 0 1 0 8zM9 14l2 2 4-4",
  slope: "M3 19h18L15 7l-4 6-2-3z", speed: "M13 5a1.5 1.5 0 1 0 0 .1M10 21l2-6-3-3 2-4 3 2 3 1M7 12l3-4", bag: "M6 8h12l1 12H5zM9 8V6a3 3 0 0 1 6 0v2", clock: "M12 12m-8 0a8 8 0 1 0 16 0a8 8 0 1 0-16 0M12 8v4l3 2",
  back: "M4 12a8 8 0 1 0 3-6M4 5v5h5", sun: "M12 12m-4 0a4 4 0 1 0 8 0a4 4 0 1 0-8 0M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2", rad: "M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0-18 0M12 12m-1.5 0a1.5 1.5 0 1 0 3 0a1.5 1.5 0 1 0-3 0M12 10V4M10.3 13l-5 3M13.7 13l5 3",
  dist: "M6 20a2 2 0 1 0 0-.1M18 6a2 2 0 1 0 0-.1M8 19h6a3 3 0 0 0 0-6h-4a3 3 0 0 1 0-6h6", rough: "M3 14l3-5 3 7 3-9 3 8 3-4 3 3",
};
const ico = (n) => `<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><path d="${ICONS[n] || ""}"/></svg>`;
document.querySelectorAll("[data-ico]").forEach((e) => (e.outerHTML = ico(e.dataset.ico)));

const S = { region: null, layers: {}, overlays: {}, sites: [], goals: [], goalOn: {}, goalSite: {}, eva: {}, profile: "gentlest", start: null, end: null, route: null, routeLayer: null, povImgs: [], povI: 0, povSite: null, editing: false };

const MARS_CRS = L.extend({}, L.CRS.EPSG4326, { R: 3396190 });
const map = L.map("map", { crs: MARS_CRS, zoomControl: false, attributionControl: false, minZoom: 6, maxZoom: 17, zoomSnap: 0.25 });
L.control.scale({ imperial: false, position: "topleft", maxWidth: 160 }).addTo(map);
map.createPane("overlays").style.zIndex = 300;
map.createPane("route").style.zIndex = 450;
$("zin").onclick = () => map.zoomIn();
$("zout").onclick = () => map.zoomOut();

// Layer rows of the reference design, mapped to the layers the backend really has.
const LAYER_ROWS = [
  { key: "terrain", name: "Terrain", sub: "(HiRISE DTM, 1 m)", ids: ["hillshade"], on: true },
  { key: "imagery", name: "Surface Imagery", sub: "(CTX, 6 m)", ids: ["ctx"], on: true, note: " CTX is a greyscale camera; the Mars tint is for display only." },
  { key: "geology", name: "Geologic Units", sub: "(USGS SIM 3464)", ids: ["geology"], on: true },
  { key: "thermal", name: "Thermal", sub: "(THEMIS)", ids: ["themis_day"], on: false },
  { key: "spectral", name: "Spectral", sub: "(CRISM)", ids: ["crism_carbonate"], alt: ["crism_carbonate", "crism_mafic"], on: false },
  { key: "atmos", name: "Atmospheric", sub: "(MEDA)", ids: [], special: "meda", on: false },
];
const BLEND = { crism_carbonate: 1, crism_mafic: 1, geology: 0.8, themis_day: 1, hillshade: 0.55, slope: 1 };

function setOverlay(id, on) {
  const meta = S.layers[id];
  if (!meta) return;
  if (on && !S.overlays[id]) S.overlays[id] = L.imageOverlay(meta.url, meta.bounds, { pane: id === "ctx" ? "tilePane" : "overlays", opacity: layerOpacity(id) }).addTo(map);
  else if (!on && S.overlays[id]) { map.removeLayer(S.overlays[id]); delete S.overlays[id]; }
}
function layerOpacity(id) { return id === "ctx" ? 1 : (+$("opacity").value / 100) * (BLEND[id] ?? 1); }
$("opacity").oninput = () => { $("opv").textContent = $("opacity").value + "%"; Object.entries(S.overlays).forEach(([id, o]) => o.setOpacity(layerOpacity(id))); };

function renderLayers() {
  $("layerList").innerHTML = LAYER_ROWS.map((r) => {
    const have = r.special === "meda" ? !!S.weather?.available : r.ids.length && r.ids.every((i) => S.layers[i]);
    const m = have && r.ids.length ? S.layers[r.ids[0]] : r.special === "meda" && have ? { mission: "Mars 2020", instrument: "MEDA", source: "measured weather at the science sites (historical, not live)" } : null;
    const pick = have && r.alt ? `<select data-alt="${r.key}" title="Which CRISM map">${r.alt.filter((i) => S.layers[i]).map((i) => `<option value="${i}" ${i === r.ids[0] ? "selected" : ""}>${i === "crism_mafic" ? "Mafic" : "Carbonate"}</option>`).join("")}</select>` : "";
    const tip = have ? `${m.mission || ""} ${m.instrument || ""} - ${m.source || m.name || ""}.${r.note || ""}` : "Data not loaded for this region";
    return `<label class="row ${have ? "" : "off"}"><input type="checkbox" data-row="${r.key}" ${have && r.on ? "checked" : ""} ${have ? "" : "disabled"}>
      <span class="nm">${esc(r.name)} <small>${esc(r.sub)}${have ? "" : " - not loaded"}</small></span>${pick}<span class="info" title="${esc(tip)}">i</span></label>`;
  }).join("");
  $("layerList").querySelectorAll("input").forEach((cb) => (cb.onchange = () => {
    const row = LAYER_ROWS.find((r) => r.key === cb.dataset.row);
    row.on = cb.checked; row.ids.forEach((i) => setOverlay(i, cb.checked));
    if (row.special === "meda") renderWeather();
    renderLegend();
  }));
  $("layerList").querySelectorAll("select[data-alt]").forEach((sel) => (sel.onchange = () => {
    const row = LAYER_ROWS.find((r) => r.key === sel.dataset.alt);
    row.ids.forEach((i) => setOverlay(i, false)); row.ids = [sel.value]; if (row.on) setOverlay(sel.value, true); renderLegend();
  }));
  LAYER_ROWS.forEach((r) => r.ids.forEach((i) => S.layers[i] && setOverlay(i, r.on)));
  const types = new Set(["topographic", "optical"]);
  if (S.layers.geology) types.add("geologic"); if (S.layers.themis_day) types.add("thermal"); types.add("radiation");
  if (S.layers.crism_carbonate) types.add("spectral"); if (S.weather?.available) types.add("atmospheric");
  $("ftTypes").textContent = `(${types.size} data types)`;
}
function renderLegend() {
  const items = S.layers.geology?.legend?.items || [];
  const sp = LAYER_ROWS.find((r) => r.key === "spectral"), lg = sp.on && S.layers[sp.ids[0]]?.legend;
  const crism = lg ? `<div style="display:block;border-bottom:1px solid var(--line2);padding-bottom:5px;margin-bottom:4px"><b>CRISM ${sp.ids[0] === "crism_mafic" ? "mafic" : "carbonate"} map</b><br>
    <span style="color:#ff8080">R</span> ${esc(lg.red)} · <span style="color:#7dff9a">G</span> ${esc(lg.green)} · <span style="color:#8ab4ff">B</span> ${esc(lg.blue)}<br><span style="color:var(--mut)">${esc(lg.reading)}</span></div>` : "";
  $("legend").innerHTML = crism + (items.length ? items.map(([n, c]) => `<div><i style="background:${esc(c)}"></i>${esc(n)}</div>`).join("") : `<div>Geologic map ${NA}</div>`);
}
$("tLayers").onclick = () => { const cb = document.querySelector('[data-row="geology"]'); if (cb && !cb.disabled) { cb.checked = !cb.checked; cb.onchange(); } };
$("tSlope").onclick = () => { const on = !S.overlays.slope; setOverlay("slope", on); $("tSlope").classList.toggle("on", on); };
$("tFit").onclick = () => fit();
$("tFull").onclick = () => { $("mapwrap").classList.toggle("full"); setTimeout(() => map.invalidateSize(), 60); };
function fit() { if (S.routeLayer) map.fitBounds(S.routeLayer.getBounds().pad(0.25)); else if (S.region) { const b = S.region.bbox; map.fitBounds([[b.south, b.west], [b.north, b.east]]); } }

// ---------- measured weather (MEDA) card over the map
function renderWeather() {
  const on = LAYER_ROWS.find((r) => r.key === "atmos").on, el = $("wx");
  el.classList.toggle("hidden", !on || !S.weather?.available);
  if (!on || !S.weather?.available) return;
  const stops = planPoints().stops, rng = (o, u, d = 0) => (o ? `${fmt(o.min, d)} to ${fmt(o.max, d)}${u}` : NA);
  const rows = stops.map((s) => { const w = S.weather.sites[s.site]; if (!w) return "";
    return `<tr><td><b>${esc(s.name)}</b><br><small>sol ${w.sol}</small></td><td>${rng(w.air_temp_c, " °C")}</td><td>${rng(w.ground_temp_c, " °C")}</td><td>${rng(w.pressure_pa, " Pa")}</td><td>${w.wind_speed_ms ? fmt(w.wind_speed_ms.mean, 1) + " m/s" : NA}</td></tr>`; }).join("");
  el.innerHTML = `<b>Measured weather (MEDA)</b><table><tr><th>Stop</th><th>Air</th><th>Ground</th><th>Pressure</th><th>Wind</th></tr>${rows || `<tr><td colspan="5">No record for these stops</td></tr>`}</table><small>Perseverance measurements on the sol it worked at each stop. Historical, not live.</small>`;
}

// ---------- route
const shortName = (n) => String(n || "").split(/[,(]/)[0].trim();
function planPoints() {
  const stops = S.goals.filter((g) => S.goalOn[g.id] && S.goalSite[g.id]).map((g) => {
    const f = S.goalSite[g.id]; return { lon: f.geometry.coordinates[0], lat: f.geometry.coordinates[1], name: shortName(f.properties.name), goal: g.id, site: f.properties.id };
  });
  return { start: S.start, stops, end: S.end };
}
function evaOverrides() { const o = {}; ["max_slope_deg", "flat_speed_kmh", "load_kg", "eva_hours", "reserve_fraction", "round_trip"].forEach((k) => (o[k] = S.eva[k])); return o; }
function msg(t) { $("mapmsg").textContent = t || ""; $("mapmsg").classList.toggle("hidden", !t); }

async function calc() {
  const p = planPoints();
  if (!p.start || !p.end) return;
  msg("");
  const body = { region_id: S.region.region_id, start: p.start, destination: p.end, stops: p.stops.map(({ lon, lat, name }) => ({ lon, lat, name })), optimise_stop_order: true, eva: evaOverrides() };
  try {
    if (S.profile === "compare") {
      const d = await api("/routes/compare", { method: "POST", body: JSON.stringify({ ...body, profiles: ["gentlest", "fastest", "shortest"] }) });
      const routes = d.routes || [];
      renderCompare(routes);
      S.route = routes.find((r) => r.profile === "gentlest") || routes[0];
    } else {
      S.route = await api("/routes/calculate", { method: "POST", body: JSON.stringify({ ...body, profile: S.profile }) });
      $("compare").innerHTML = "";
    }
    drawRoute(); renderSummary(); renderWeather();
  } catch (e) { msg(e.message); }
}
function tip(html, cls) { return { permanent: true, direction: "top", offset: [0, -10], className: "lbl " + (cls || ""), html }; }
function drawRoute() {
  if (S.routeLayer) map.removeLayer(S.routeLayer);
  const r = S.route; if (!r) return;
  const g = L.featureGroup();
  const ll = r.geometry.coordinates.map(([lo, la]) => [la, lo]);
  L.polyline(ll, { pane: "route", color: "#0b2a55", weight: 7, opacity: 0.75 }).addTo(g);
  L.polyline(ll, { pane: "route", color: "#9fd4ff", weight: 3.5, dashArray: "7 7" }).addTo(g);
  const stops = r.stops || [];
  stops.forEach((s, i) => {
    const first = i === 0, last = i === stops.length - 1;
    const [lo, la] = s.snapped || s.requested;
    const m = L.circleMarker([la, lo], { pane: "route", radius: first || last ? 9 : 7, color: "#fff", weight: 3, fillColor: first || last ? "#2f7fe0" : "#1b1b1b", fillOpacity: 1 }).addTo(g);
    const label = first ? `Start<small>(${esc(s.name)})</small>` : last ? `Destination<small>(${esc(s.name)})</small>` : `S${i}<small>${esc(s.name)}</small>`;
    const dir = first || last ? "bottom" : ["top", "left", "right"][(i - 1) % 3];
    const off = { top: [0, -10], bottom: [0, 10], left: [-10, 0], right: [10, 0] }[dir];
    m.bindTooltip(label, { permanent: true, direction: dir, offset: off, className: "lbl" + (first || last ? " blue" : "") });
    if (!first && !last) m.on("click", () => selectPov(planPoints().stops.find((x) => x.name === s.name)?.site));
  });
  S.routeLayer = g.addTo(map); fit();
}
function renderSummary() {
  const r = S.route; if (!r) return;
  const ok = r.eva?.within_budget;
  $("tiles").innerHTML = [
    ["dist", "Total Distance", fmt(r.distance_km, 1, " km")], ["clock", "EVA Time", hm(r.eva?.required_min)],
    ["slope", "Max Slope", fmt(r.max_slope_deg, 1, "°")], ["rough", "Roughness", fmt(r.max_roughness_m, 2)],
  ].map(([i, l, v]) => `<div class="tile">${ico(i)}<small>${l}</small><b>${v}</b></div>`).join("") +
    `<div class="tile ${ok ? "ok" : "bad"}">${ico("shield")}<b>${ok ? "EVA Feasible" : "Over budget"}</b><small>(${ok ? "Within" : "Exceeds"} ${fmt(r.eva?.usable_min / 60, 1)} h usable)</small></div>`;
  drawChart(r);
}
function drawChart(r) {
  const p = r.elevation_profile || []; if (p.length < 2) { $("chart").innerHTML = ""; return; }
  const W = 640, H = 118, L0 = 62, R0 = 10, T = 14, B = 22;
  const xs = p.map((d) => d.distance_km), ys = p.map((d) => d.elevation_m);
  const x0 = 0, x1 = Math.max(...xs), ylo = Math.min(...ys), yhi = Math.max(...ys), pad = Math.max(4, (yhi - ylo) * 0.15), y0 = ylo - pad, y1 = yhi + pad;
  const X = (v) => L0 + ((v - x0) / (x1 - x0 || 1)) * (W - L0 - R0), Y = (v) => T + (1 - (v - y0) / (y1 - y0 || 1)) * (H - T - B);
  const line = p.map((d, i) => `${i ? "L" : "M"}${X(d.distance_km).toFixed(1)} ${Y(d.elevation_m).toFixed(1)}`).join(" ");
  const yt = [0, 1, 2, 3].map((i) => y0 + ((y1 - y0) * i) / 3), xt = [0, 1, 2, 3, 4].map((i) => (x1 * i) / 4);
  const stops = (r.stops || []).slice(1, -1).map((s, i) => {
    const d = p.reduce((a, b) => (Math.abs(b.distance_km - s.at_distance_km) < Math.abs(a.distance_km - s.at_distance_km) ? b : a));
    return `<circle cx="${X(d.distance_km)}" cy="${Y(d.elevation_m)}" r="3.5" fill="#1b1b1b" stroke="#fff" stroke-width="1.5"/><text x="${X(d.distance_km)}" y="${Y(d.elevation_m) - 8}" text-anchor="middle" fill="#fff" font-size="12" font-weight="700">S${i + 1}</text>`;
  }).join("");
  $("chart").innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><defs><linearGradient id="ar" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ff8a2a" stop-opacity=".55"/><stop offset="1" stop-color="#ff8a2a" stop-opacity="0"/></linearGradient></defs>
    ${yt.map((v) => `<line x1="${L0}" x2="${W - R0}" y1="${Y(v)}" y2="${Y(v)}" stroke="rgba(255,255,255,.08)"/><text x="${L0 - 6}" y="${Y(v) + 4}" text-anchor="end" fill="#c9b8ac" font-size="10.5">${Math.round(v).toLocaleString("en-US").replace("-", "−")} m</text>`).join("")}
    ${xt.map((v) => `<text x="${X(v)}" y="${H - 5}" text-anchor="middle" fill="#c9b8ac" font-size="10.5">${v.toFixed(1)} km</text>`).join("")}
    <path d="${line} L${X(x1)} ${H - B} L${X(0)} ${H - B} Z" fill="url(#ar)"/><path d="${line}" fill="none" stroke="#ff9a3c" stroke-width="2"/>${stops}</svg>`;
}
function renderCompare(routes) {
  $("compare").innerHTML = routes.length ? `<table><tr><th>Profile</th><th>Distance</th><th>EVA time</th><th>Max slope</th><th>Budget</th></tr>${routes.map((r) =>
    `<tr><td>${esc(r.profile)}</td><td>${fmt(r.distance_km, 2, " km")}</td><td>${hm(r.eva?.required_min)}</td><td>${fmt(r.max_slope_deg, 1, "°")}</td><td>${r.eva?.within_budget ? "within" : "exceeds"}</td></tr>`).join("")}</table>` : "";
}
$("profiles").querySelectorAll("button").forEach((b) => (b.onclick = () => {
  $("profiles").querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b)); S.profile = b.dataset.p; calc();
}));

// ---------- click a point: details open next to the click
map.on("click", async (e) => {
  const lon = e.latlng.lng, lat = e.latlng.lat;
  const pop = L.popup({ maxWidth: 280 }).setLatLng(e.latlng).setContent("Reading terrain...").openOn(map);
  try {
    const d = await api(`/point-info?region_id=${encodeURIComponent(S.region.region_id)}&lon=${lon}&lat=${lat}`);
    if (!d.inside) { pop.setContent(esc(d.message || "Outside the study region")); return; }
    const t = d.terrain || {}, s = d.nearest_science_site;
    pop.setContent(`<div class="popcard"><b>${esc(d.geology?.unit || "Unit " + NA)}</b>
      <div class="kv">Elevation ${fmt(t.elevation_m, 0, " m")} · slope ${fmt(t.slope_deg, 1, "°")} · roughness ${fmt(t.roughness_m, 2, " m")}<br>
      ${d.walkable ? "Walkable under EVA limits" : "Not walkable: " + esc((d.not_walkable_because || []).join("; "))}${s ? `<br>Nearest stop: ${esc(shortName(s.name))}, ${fmt(s.distance_m, 0, " m")}` : ""}</div>
      <button data-a="start">Start here</button><button data-a="end">Destination here</button><button data-a="pov">Point of view</button></div>`);
    const el = pop.getElement();
    el.querySelector('[data-a="start"]').onclick = () => { S.start = { lon, lat, name: "Selected point" }; map.closePopup(); calc(); };
    el.querySelector('[data-a="end"]').onclick = () => { S.end = { lon, lat, name: "Selected point" }; map.closePopup(); calc(); };
    el.querySelector('[data-a="pov"]').onclick = () => (location.href = `pov.html?region_id=${encodeURIComponent(S.region.region_id)}&lon=${lon}&lat=${lat}`);
  } catch (err) { pop.setContent(esc(err.message)); }
});

// ---------- right column
async function thumbFor(siteId) {
  try { const d = await api(`/ground-view?region_id=${encodeURIComponent(S.region.region_id)}&site_id=${siteId}&max_images=1`); const x = (d.images || [])[0]; return x ? x.local_small_url || (d.offline ? null : x.small_url) : null; } catch { return null; }
}
async function renderGoals() {
  $("goalsRegion").textContent = shortName(S.region.name).replace(/ Crater.*/, "");
  $("goals").innerHTML = S.goals.map((g) => `<label class="goal"><input type="checkbox" data-g="${esc(g.id)}" ${S.goalOn[g.id] ? "checked" : ""} ${S.goalSite[g.id] ? "" : "disabled"}>
    <span class="id">${esc(g.id)}</span><span class="tx"><b>${esc(g.title)}</b><span>${esc(g.summary)}</span></span><span class="ph" id="gth_${esc(g.id)}"></span></label>`).join("") || `<div>Science goals ${NA}</div>`;
  $("goals").querySelectorAll("input").forEach((cb) => (cb.onchange = () => { S.goalOn[cb.dataset.g] = cb.checked; calc(); }));
  for (const g of S.goals) {
    const f = S.goalSite[g.id]; if (!f) continue;
    const u = await thumbFor(f.properties.id);
    if (u) $("gth_" + g.id).outerHTML = `<img src="${esc(u)}" alt="Perseverance image near ${esc(shortName(f.properties.name))}" loading="lazy">`;
  }
}
const EVA_ROWS = [["slope", "Max Slope (limit)", "max_slope_deg", (v) => `≤ ${v}°`], ["speed", "Walk Speed (flat)", "flat_speed_kmh", (v) => `${(+v).toFixed(1)} km/h`], ["bag", "Equipment Load", "load_kg", (v) => `${v} kg`],
  ["clock", "EVA Time Budget", "eva_hours", (v) => `${v} h`], ["back", "Return Reserve", "reserve_fraction", (v) => `${Math.round(v * 100)}% (≤ ${fmt(S.eva.eva_hours * (1 - v), 1)} h out)`]];
function renderEva() {
  $("eva").innerHTML = EVA_ROWS.map(([i, l, k, f]) => `<div class="kvrow">${ico(i)}<span>${l}</span>${S.editing ? `<input data-k="${k}" type="number" step="any" value="${S.eva[k]}">` : `<b>${S.eva[k] === undefined ? NA : f(S.eva[k])}</b>`}</div>`).join("") +
    `<div class="kvrow">${ico("path")}<span>Plan</span><b>${S.eva.round_trip ? "Out and back to start" : "One way to destination"}</b></div>`;
  $("evaEdit").textContent = S.editing ? "Apply" : "Edit";
}
$("evaEdit").onclick = () => {
  if (S.editing) { $("eva").querySelectorAll("input").forEach((i) => { const v = parseFloat(i.value); if (Number.isFinite(v)) S.eva[i.dataset.k] = v; }); S.editing = false; renderEva(); calc(); loadRad(); }
  else { S.editing = true; renderEva(); }
};
async function loadRad() {
  try {
    const d = await api(`/space-weather?eva_hours=${S.eva.eva_hours || 4}`);
    const lvl = d.advisory?.level || "unknown", c = d.counts || {}, n = (v) => (v === null || v === undefined ? "unknown" : v);
    $("radBadge").textContent = lvl === "nominal" ? "Nominal" : lvl === "caution" ? "Caution" : "Unknown";
    $("radBadge").className = "badge " + (lvl === "nominal" ? "ok" : lvl === "caution" ? "warn" : "");
    const rr = d.rad_reference || {};
    $("rad").innerHTML = `<div class="radrow">${ico("sun")}<div><b>Solar Activity (DONKI)</b><span>SEP ${n(c.SEP)} / Flare ${n(c.FLR)} / CME ${n(c.CME)} in the last 30 days</span><span>(Last update: ${d.fetched_at ? esc(d.fetched_at.replace("T", " ").slice(0, 16)) + " UTC" : NA})</span></div></div>
      <div class="radrow">${ico("rad")}<div><b>Surface Radiation (Reference)</b><span>${rr.value ?? NA} ${esc(rr.unit || "")} (Curiosity, ${esc(rr.where || NA)}, ${esc(rr.period || "")}, historical)</span></div></div>`;
  } catch (e) { $("rad").textContent = "Space weather " + NA; }
}
async function selectPov(siteId) {
  if (!siteId) return; S.povSite = siteId; S.povI = 0; S.povImgs = []; S.povSol = null;
  try { const d = await api(`/ground-view?region_id=${encodeURIComponent(S.region.region_id)}&site_id=${siteId}&max_images=8`);
    S.povImgs = (d.images || []).map((x) => ({ u: x.local_medium_url || (d.offline ? null : x.medium_url), sol: x.sol })).filter((x) => x.u); } catch { /* shown as not available */ }
  showPov();
}
function showPov() {
  const x = S.povImgs[S.povI], has = !!x;
  $("povImg").classList.toggle("hidden", !has); $("povNone").classList.toggle("hidden", has);
  if (has) $("povImg").src = x.u;
  const f = S.sites.find((s) => s.properties.id === S.povSite);
  $("povCap").textContent = has ? `Perseverance - Sol ${x.sol} (${f ? shortName(f.properties.name) : "Jezero"}) · ${S.povI + 1}/${S.povImgs.length}` : "No rover image cached for this stop";
  $("povLink").href = `pov.html?region_id=${encodeURIComponent(S.region.region_id)}&site_id=${encodeURIComponent(S.povSite || "")}&i=${S.povI}`;
}
$("povPrev").onclick = (e) => { e.preventDefault(); if (S.povImgs.length) { S.povI = (S.povI - 1 + S.povImgs.length) % S.povImgs.length; showPov(); } };
$("povNext").onclick = (e) => { e.preventDefault(); if (S.povImgs.length) { S.povI = (S.povI + 1) % S.povImgs.length; showPov(); } };

// ---------- tabs: assistant and offline open a drawer over the map; the others point at their panels
function flash(id) { const el = $(id); el.scrollIntoView({ behavior: "smooth", block: "nearest" }); el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash"); }
function drawer(title, html) { $("drawer").innerHTML = `<h4>${esc(title)}<button class="x" aria-label="Close">×</button></h4>${html}`; $("drawer").classList.remove("hidden"); $("drawer").querySelector(".x").onclick = closeDrawer; }
function closeDrawer() { $("drawer").classList.add("hidden"); setTab("map"); }
function setTab(t) { document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === t)); }
document.querySelectorAll(".tab").forEach((b) => (b.onclick = async () => {
  const t = b.dataset.tab; setTab(t); $("drawer").classList.add("hidden");
  if (t === "goals") flash("pGoals");
  if (t === "safety") { flash("pEva"); flash("pRad"); }
  if (t === "assistant") openAssistant();
  if (t === "offline") {
    drawer("Offline package", `<div class="body" id="offBody">Checking...</div>`);
    try { const d = await api(`/offline/package?region_id=${encodeURIComponent(S.region.region_id)}`);
      $("offBody").innerHTML = Object.entries(d.ready_offline || {}).map(([k, v]) => `<div class="kvrow"><span>${esc(k.replace(/_/g, " "))}</span><b style="color:${v ? "var(--ok)" : "var(--bad)"}">${v ? "ready" : "not cached"}</b></div>`).join("") +
        `<div class="kvrow"><span>Data date</span><b>${esc(d.data_date || NA)}</b></div><div class="kvrow"><span>Network now</span><b>${d.online_now ? "online" : "offline"}</b></div>`;
    } catch (e) { $("offBody").textContent = e.message; }
  }
}));
function openAssistant() {
  drawer("Science assistant", `<div class="body" id="chat"><div class="ans">Answers come only from the loaded NASA documents and MarsPath data, with sources.</div></div>
    <form class="ask" id="askForm"><input id="askQ" placeholder="What was found at Wildcat Ridge?" autocomplete="off"><button>Ask</button></form>`);
  $("askForm").onsubmit = async (e) => {
    e.preventDefault(); const q = $("askQ").value.trim(); if (q.length < 2) return; $("askQ").value = "";
    const box = document.createElement("div"); box.className = "ans"; box.innerHTML = `<div class="q">${esc(q)}</div>Searching the documents...`; $("chat").appendChild(box); box.scrollIntoView();
    try {
      const r = await api("/assistant/ask", { method: "POST", body: JSON.stringify({ question: q, region_id: S.region.region_id }) });
      const g = r.grounding;
      box.innerHTML = `<div class="q">${esc(q)}</div>${esc(r.answer)}<div>${g ? `<span class="chip ok">${g.supported} of ${g.total} sentences supported</span>` : ""}
        <span class="chip">${r.mode === "llm" ? esc(r.model || "LLM") : r.found ? "quoted from sources" : "not found"}</span></div>
        <div>${(r.citations || []).slice(0, 4).map((c) => `<a class="chip" href="${esc(c.url || "#")}" target="_blank" rel="noopener">[${c.n}] ${esc(String(c.title).slice(0, 42))}${c.page ? ", p." + c.page : ""}</a>`).join("")}</div>`;
    } catch (err) { box.innerHTML = `<div class="q">${esc(q)}</div>${esc(err.message)}`; }
    box.scrollIntoView();
  };
  $("askQ").focus();
}

// ---------- start-up
(async function init() {
  try {
    const regs = await api("/regions"); const list = regs.regions || regs;
    S.region = list.find((r) => !r.is_test_fixture) || list[0];
    if (!S.region) { msg("No prepared region. Run setup and prepare the data first."); return; }
    const b = S.region.bbox; map.fitBounds([[b.south, b.west], [b.north, b.east]]);
    $("regionName").textContent = shortName(S.region.name).replace(/ - .*/, "");
    $("regionSub").textContent = S.region.is_test_fixture ? "TEST FIXTURE: synthetic terrain, not real Mars data" : "Chosen: heavily studied site (Perseverance ground truth)";
    const [lay, ss, eva] = await Promise.all([api(`/layers?region_id=${encodeURIComponent(S.region.region_id)}`), api(`/science-sites?region_id=${encodeURIComponent(S.region.region_id)}`), api("/eva/defaults")]);
    (lay.layers || []).forEach((l) => (S.layers[l.id] = l));
    S.weather = await api(`/weather?region_id=${encodeURIComponent(S.region.region_id)}`).catch(() => null);
    if (S.layers.ctx) $("regionThumb").style.backgroundImage = `url(${S.layers.ctx.url})`;
    renderLayers(); renderLegend();
    S.sites = (ss.features || []).filter((f) => f.properties.kind === "science_site");
    S.goals = ss.science_goals || S.region.science_goals || [];
    S.goals.forEach((g) => { S.goalSite[g.id] = S.sites.find((f) => f.properties.goal_id === g.id); S.goalOn[g.id] = !!S.goalSite[g.id]; });
    S.eva = { ...(eva.params || {}), round_trip: false };
    const pt = (f, name) => f && { lon: f.geometry.coordinates[0], lat: f.geometry.coordinates[1], name };
    const landing = S.sites.find((f) => /landing/i.test(f.properties.name)), depot = S.sites.find((f) => /depot/i.test(f.properties.name));
    S.start = pt(landing || S.sites[0], "Landing Site"); S.end = pt(depot || S.sites[S.sites.length - 1], "Retreat / Habitat");
    renderEva(); renderGoals(); loadRad();
    const first = S.goals.map((g) => S.goalSite[g.id]).find(Boolean); if (first) selectPov(first.properties.id);
    if (S.start && S.end) await calc(); else msg("No curated science sites for this region yet: click the map to set a start and a destination.");
  } catch (e) { msg(e.message); }
})();
