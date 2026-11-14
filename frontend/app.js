/* MarsPath simple frontend (plain JS + Leaflet). The backend owns every scientific value:
   this page only displays what the API returns and never recalculates or invents data. */
const API = "/api/v1";
const S = { region: null, regionInfo: null, mode: null, points: { start: null, stops: [], end: null },
            layers: {}, route: null, routeLayer: null, cmpLayers: [], hoverMarker: null, defaults: null };

// ---------------------------------------------------------------- helpers
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (v, d = 1, u = "") => (v === null || v === undefined ? "n/a" : `${Number(v).toFixed(d)}${u}`);
function toast(t, ms = 3500) { const el = $("toast"); el.textContent = t; el.classList.remove("hidden"); clearTimeout(toast._t); toast._t = setTimeout(() => el.classList.add("hidden"), ms); }
async function api(path, opts = {}) {
  const r = await fetch(API + path, { headers: { "Content-Type": "application/json" }, ...opts });
  let body = null; try { body = await r.json(); } catch (_) {}
  if (!r.ok) { const d = body && body.detail; const msg = (d && (d.message || (Array.isArray(d) ? d.map(x => x.msg).join("; ") : JSON.stringify(d)))) || r.statusText; throw new Error(msg); }
  return body;
}
const link = (url, text) => url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(text || "source")}</a>` : esc(text || "");

// ---------------------------------------------------------------- map
// Mars Trek EQ tiles are plate carree, so the map uses Leaflet's EPSG4326 CRS (lon/lat degrees).
// Same projection, but distances (scale bar) use the Mars 2000 sphere radius instead of Earth's.
const MARS_CRS = L.extend({}, L.CRS.EPSG4326, { R: 3396190 });
const map = L.map("map", { crs: MARS_CRS, center: [18.44, 77.43], zoom: 3, minZoom: 1, maxZoom: 17, worldCopyJump: false });
L.control.scale({ imperial: false }).addTo(map);
const panes = ["overlays", "pins", "route"]; panes.forEach((p, i) => { map.createPane(p); map.getPane(p).style.zIndex = 410 + i * 10; });
const pinLayer = L.layerGroup().addTo(map), hazardLayer = L.layerGroup().addTo(map), ptLayer = L.layerGroup().addTo(map), traverseLayer = L.layerGroup().addTo(map);

map.on("click", async (e) => {
  const lon = e.latlng.lng, lat = e.latlng.lat;
  if (S.mode) {
    const p = { lon, lat, name: null };
    if (S.mode === "start") S.points.start = p; else if (S.mode === "end") S.points.end = p; else S.points.stops.push(p);
    if (S.mode !== "stop") setMode(null);
    renderPoints(); return;
  }
  if (!S.region) return;
  try {
    const t = await api(`/terrain/sample?region_id=${S.region}&lon=${lon}&lat=${lat}`);
    L.popup().setLatLng(e.latlng).setContent(
      `<b>Terrain here</b>${t.is_test_fixture ? " <i>(TEST FIXTURE)</i>" : ""}<br>lon ${lon.toFixed(5)} E, lat ${lat.toFixed(5)}<br>
       Elevation: ${fmt(t.elevation_m, 1, " m")}<br>Slope: ${fmt(t.slope_deg, 1, " deg")}<br>Roughness: ${fmt(t.roughness_m, 2, " m")}<br>
       Unit: ${esc(t.geologic_unit || "n/a")}<br><span class="hint">DEM: ${esc(t.dem_source || "none")} - ${esc(t.source || "")}</span>`).openOn(map);
  } catch (err) { /* outside region: ignore */ }
});

function setMode(m) {
  S.mode = m;
  document.querySelectorAll("button[data-mode]").forEach((b) => b.classList.toggle("active", b.dataset.mode === m));
  $("modeHint").textContent = m ? `Click the map to place the ${m === "stop" ? "science stop(s) - click the button again to finish" : m}.` :
    "Pick a button, then click the map. Click the map with no button selected to read the terrain there.";
  map.getContainer().style.cursor = m ? "crosshair" : "";
}
document.querySelectorAll("button[data-mode]").forEach((b) => b.onclick = () => setMode(S.mode === b.dataset.mode ? null : b.dataset.mode));
$("clearPts").onclick = () => { S.points = { start: null, stops: [], end: null }; renderPoints(); clearRoute(); };

function orderedPoints() { return [S.points.start, ...S.points.stops, S.points.end]; }
function renderPoints() {
  ptLayer.clearLayers();
  const ol = $("ptList"); ol.innerHTML = "";
  const all = [["start", S.points.start, "S"], ...S.points.stops.map((p, i) => ["stop", p, String(i + 1), i]), ["end", S.points.end, "D"]];
  all.forEach(([kind, p, label, i]) => {
    if (!p) return;
    const m = L.marker([p.lat, p.lon], { draggable: true, pane: "route", icon: L.divIcon({ className: "pt-icon", html: label, iconSize: [22, 22] }) }).addTo(ptLayer);
    m.on("dragend", () => { const ll = m.getLatLng(); p.lon = ll.lng; p.lat = ll.lat; renderPoints(); });
    const li = document.createElement("li");
    li.innerHTML = `<b>${kind === "start" ? "Start" : kind === "end" ? "Destination" : "Stop " + label}</b>
      <input class="nm" placeholder="name" value="${esc(p.name || "")}">
      lon <input type="number" step="0.0001" value="${p.lon.toFixed(5)}"> lat <input type="number" step="0.0001" value="${p.lat.toFixed(5)}">
      ${kind === "stop" ? '<button class="ghost">x</button>' : ""}`;
    const [nm, lo, la] = li.querySelectorAll("input");
    nm.onchange = () => { p.name = nm.value || null; };
    lo.onchange = la.onchange = () => { p.lon = parseFloat(lo.value); p.lat = parseFloat(la.value); renderPoints(); };
    const x = li.querySelector("button"); if (x) x.onclick = () => { S.points.stops.splice(i, 1); renderPoints(); };
    ol.appendChild(li);
  });
}

// ---------------------------------------------------------------- regions & layers
async function loadRegions() {
  const r = await api("/regions");
  const sel = $("region"); sel.innerHTML = "";
  if (!r.regions.length) { $("routeMsg").innerHTML = '<span class="msg err">No processed region yet. Run prepare_data.py (see README).</span>'; return; }
  r.regions.forEach((g) => { const o = document.createElement("option"); o.value = g.region_id; o.textContent = g.name; sel.appendChild(o); });
  const pref = r.regions.find((g) => g.region_id === "jezero") || r.regions[0];
  sel.value = pref.region_id;
  sel.onchange = () => selectRegion(sel.value, r.regions.find((g) => g.region_id === sel.value));
  await selectRegion(pref.region_id, pref);
}

async function selectRegion(id, info) {
  S.region = id; S.regionInfo = info;
  $("fixtureBadge").classList.toggle("hidden", !info.is_test_fixture);
  Object.values(S.layers).forEach((l) => map.removeLayer(l.obj)); S.layers = {};
  clearRoute(); S.points = { start: null, stops: [], end: null }; renderPoints();
  const b = info.bbox; map.fitBounds([[b.south, b.west], [b.north, b.east]]);
  const ls = await api(`/layers?region_id=${id}`);
  const box = $("layers"); box.innerHTML = "";
  if (ls.notes && ls.notes.length) box.innerHTML += `<p class="hint">${ls.notes.map(esc).join("<br>")}</p>`;
  ls.layers.forEach((l) => {
    let obj;
    if (l.kind === "tiles") obj = L.tileLayer(l.url, { maxNativeZoom: 7, maxZoom: 17, noWrap: true, attribution: "NASA JPL Mars Trek / MGS MOLA", errorTileUrl: "" });
    else obj = L.imageOverlay(l.url, l.bounds, { opacity: l.opacity ?? 1, pane: "overlays", interactive: false });
    S.layers[l.id] = { obj, meta: l };
    if (l.default_on) obj.addTo(map);
    if (l.kind === "tiles") obj.bringToBack();
    const div = document.createElement("div"); div.className = "layer";
    div.innerHTML = `<label class="chk"><input type="checkbox" ${l.default_on ? "checked" : ""}> <b>${esc(l.name)}</b></label>
      <input type="range" min="0" max="1" step="0.05" value="${l.opacity ?? 1}">
      ${legendHtml(l)}
      <div class="src">${esc(l.mission || "")} ${l.instrument ? "/ " + esc(l.instrument) : ""} - ${l.resolution_m ? fmt(l.resolution_m, 1, " m/px") : esc(l.resolution || "")}
      ${l.units ? " - units: " + esc(l.units) : ""}<br>${link(l.source_url, l.source || "source")}<br><i>${esc(l.measured_or_derived || "")}.</i> ${esc(l.limitations || "")}</div>`;
    const [cb, rng] = div.querySelectorAll("input");
    cb.onchange = () => cb.checked ? obj.addTo(map) : map.removeLayer(obj);
    rng.oninput = () => obj.setOpacity(parseFloat(rng.value));
    box.appendChild(div);
  });
  await Promise.all([loadPins(), loadHazards(), loadOffline(), loadSpaceWeather()]);
  renderGoals(info);
}

function legendHtml(l) {
  const lg = l.legend; if (!lg) return "";
  if (lg.type === "gradient") {
    const st = lg.stops; const lo = st[0][0], hi = st[st.length - 1][0];
    const g = st.map(([v, c]) => `${c} ${((v - lo) / (hi - lo || 1) * 100).toFixed(0)}%`).join(",");
    return `<div class="legend" style="background:linear-gradient(to right,${g})"></div><div class="hint">${lo} ... ${hi} ${esc(l.units || "")}</div>`;
  }
  if (lg.type === "categorical") return lg.items.map(([n, c]) => `<div class="hint"><span class="cat" style="background:${c}"></span>${esc(n)}</div>`).join("");
  if (lg.type === "stretch") return `<div class="hint">contrast stretch ${fmt(lg.min, 1)} - ${fmt(lg.max, 1)}</div>`;
  return "";
}

// ---------------------------------------------------------------- pins
async function loadPins() {
  pinLayer.clearLayers(); traverseLayer.clearLayers();
  const fc = await api(`/science-sites?region_id=${S.region}`);
  if (fc.traverse && fc.traverse.features.length) L.geoJSON(fc.traverse, { pane: "pins", style: { color: "#ffffff", weight: 2, dashArray: "4 4", opacity: 0.8 } }).addTo(traverseLayer);
  fc.features.forEach((f) => {
    const p = f.properties, [lon, lat] = f.geometry.coordinates;
    const rover = p.kind === "rover_waypoint";
    const m = L.circleMarker([lat, lon], { pane: "pins", radius: rover ? 4 : 7, color: rover ? "#4dabf7" : "#2f9e44", fillOpacity: 0.9, weight: 2 }).addTo(pinLayer);
    m.bindPopup(rover ?
      `<b>${esc(p.name)}</b><br>Mission: ${esc(p.mission)}<br>Sol: ${esc(p.sol)}<br>lon ${lon.toFixed(5)}, lat ${lat.toFixed(5)}<br>
       <i>${esc(p.measured_or_derived)}</i><br>${link(p.source_url, p.source)}<br>${link(p.raw_images_url, "Perseverance raw images (filter by sol " + esc(p.sol) + ")")}
       <br><button onclick="addStop(${lon},${lat},'${esc(p.name).replace(/'/g, "")}')">Add as stop</button>` :
      `<b>${esc(p.name)}</b><br>${esc(p.observation || "")}<br>Mission/instrument: ${esc(p.mission)} / ${esc(p.instrument)}<br>
       Date: ${esc(p.observation_date || "n/a")}<br>Goal: ${esc(p.goal_id || "")} - ${esc(p.why_it_matters || "")}<br>
       <i>${esc(p.measured_or_derived)}</i><br>${link(p.source_url, p.source)}
       <br><button onclick="addStop(${lon},${lat},'${esc(p.name).replace(/'/g, "")}')">Add as stop</button>`);
  });
}
window.addStop = (lon, lat, name) => { S.points.stops.push({ lon, lat, name }); renderPoints(); map.closePopup(); toast(`Added stop: ${name}`); };

async function loadHazards() {
  hazardLayer.clearLayers();
  const fc = await api(`/hazards?region_id=${S.region}`);
  fc.features.forEach((f) => {
    const p = f.properties, [lon, lat] = f.geometry.coordinates;
    const icon = L.divIcon({ className: "hz-icon", html: p.severity === "high" ? "&#9888;&#65039;" : "&#9888;", iconSize: [18, 18] });
    L.marker([lat, lon], { icon, pane: "pins" }).addTo(hazardLayer).bindPopup(
      `<b>Terrain caution: ${esc(p.type.replace("_", " "))}</b> (${esc(p.severity)})<br>Rule: ${esc(p.rule)}<br>
       Max: ${fmt(p.metric.max, 1)} ${esc(p.metric.unit)} (threshold ${esc(p.metric.threshold)})<br>Area: ${fmt(p.area_m2 / 1e4, 2)} ha<br>
       Data: ${esc(p.source)} at ${fmt(p.data_resolution_m, 0)} m<br><i>${esc(p.measured_or_derived)}</i>. Not an observed obstacle; other ground is not "safe".`);
  });
}

function renderGoals(info) {
  const g = info.science_goals || [];
  $("goals").innerHTML = (g.length ? g.map((x) => `<div class="layer"><b>${esc(x.id)} ${esc(x.title)}</b><br>${esc(x.summary)}<br>
     <span class="hint">${esc(x.status || "")}</span><br>${link(x.source_url, x.source_title)}</div>`).join("") : '<p class="hint">No science goals defined.</p>')
    + '<p class="hint">Green pins: curated science sites. Blue pins: Perseverance stops (measured). Click a pin to add it as a stop.</p>';
}

// ---------------------------------------------------------------- EVA settings
async function loadDefaults() {
  S.defaults = await api("/eva/defaults");
  const p = S.defaults.params;
  ["max_slope_deg", "caution_slope_deg", "flat_speed_kmh", "eva_hours", "load_kg", "reserve_fraction", "roughness_max_m"].forEach((k) => $("e_" + k).value = p[k]);
  $("e_round_trip").checked = p.round_trip;
}
function evaOverrides() {
  const o = {}; ["max_slope_deg", "caution_slope_deg", "flat_speed_kmh", "eva_hours", "load_kg", "reserve_fraction", "roughness_max_m"].forEach((k) => { const v = parseFloat($("e_" + k).value); if (!isNaN(v)) o[k] = v; });
  o.round_trip = $("e_round_trip").checked; return o;
}

// ---------------------------------------------------------------- routes
function routeBody() {
  if (!S.points.start || !S.points.end) throw new Error("Set a start and a destination first.");
  return { region_id: S.region, start: S.points.start, destination: S.points.end, stops: S.points.stops, eva: evaOverrides() };
}
function clearRoute() {
  if (S.routeLayer) map.removeLayer(S.routeLayer); S.cmpLayers.forEach((l) => map.removeLayer(l)); S.cmpLayers = [];
  if (S.hoverMarker) map.removeLayer(S.hoverMarker); S.route = null; S.routeLayer = null; $("resultsBox").classList.add("hidden");
}
async function busy(btn, fn) { btn.disabled = true; $("routeMsg").className = "msg"; $("routeMsg").textContent = "Calculating..."; try { await fn(); $("routeMsg").textContent = ""; } catch (e) { $("routeMsg").className = "msg err"; $("routeMsg").textContent = e.message; } finally { btn.disabled = false; } }

$("calcBtn").onclick = () => busy($("calcBtn"), async () => {
  const body = { ...routeBody(), profile: $("profile").value, optimise_stop_order: $("optOrder").checked };
  const r = await api("/routes/calculate", { method: "POST", body: JSON.stringify(body) });
  const so = r.stop_order;
  if (so && so.changed) {  // adopt the better order in the stop list so Compare uses it too
    S.points.stops = so.order.map((i) => S.points.stops[i]); renderPoints();
    toast(`Stops reordered: ${so.cost_as_given ?? "n/a"} -> ${so.cost_optimised} ${so.cost_unit} (modelled)`, 6000);
  }
  clearRoute(); showRoute(r); $("compare").innerHTML = "";
});
$("cmpBtn").onclick = () => busy($("cmpBtn"), async () => {
  const r = await api("/routes/compare", { method: "POST", body: JSON.stringify(routeBody()) });
  clearRoute();
  const colors = { fastest: "#ff6b00", gentlest: "#20c997", shortest: "#f8f9fa" };
  r.routes.forEach((x) => { if (x.profile !== "fastest") S.cmpLayers.push(L.geoJSON(x.geometry, { pane: "route", style: { color: colors[x.profile], weight: 3, dashArray: "6 5" } }).addTo(map).bindTooltip(x.profile)); });
  showRoute(r.routes.find((x) => x.profile === "fastest") || r.routes[0]);
  const rows = r.comparison.map((c) => `<tr><td style="color:${colors[c.profile] === "#f8f9fa" ? "#666" : colors[c.profile]}"><b>${c.profile}</b></td><td>${c.distance_km}</td><td>${c.duration_min}</td><td>${c.max_slope_deg}</td><td>${c.ascent_m}</td><td>${c.within_budget ? "yes" : "NO"}</td><td>${c.warnings}</td></tr>`).join("");
  $("compare").innerHTML = `<h4>Profile comparison</h4><table><tr><th>profile</th><th>km</th><th>min out</th><th>max grade</th><th>ascent m</th><th>in budget</th><th>warn</th></tr>${rows}</table>
    ${r.errors.length ? `<p class="msg err">${r.errors.map((e) => esc(e.profile + ": " + e.message)).join("<br>")}</p>` : ""}<p class="hint">Solid line = fastest; dashed = others. Click a table row's profile in the dropdown and Calculate to see its details.</p>`;
});

function showRoute(r) {
  S.route = r;
  S.routeLayer = L.geoJSON(r.geometry, { pane: "route", style: { color: "#ff6b00", weight: 4 } }).addTo(map)
    .bindPopup(`<b>${esc(r.route_id)}</b> (${esc(r.profile_label)})<br>${r.distance_km} km, ${r.duration_min} min out<br>${r.assumptions.slice(0, 2).map(esc).join("<br>")}`);
  map.fitBounds(S.routeLayer.getBounds(), { padding: [30, 30] });
  $("resultsBox").classList.remove("hidden"); $("resultsBox").open = true;
  const e = r.eva;
  $("metrics").innerHTML = [
    ["Distance", `${r.distance_km} km`], ["Time out", `${r.duration_min} min`], ["Time back", `${r.return_duration_min} min`],
    ["Max grade", `${r.max_slope_deg} deg`], ["Mean grade", `${r.mean_slope_deg} deg`], ["Ascent / descent", `${r.ascent_m} / ${r.descent_m} m`],
    ["Elevation", `${r.elevation_min_m} .. ${r.elevation_max_m} m`], ["Max roughness", `${fmt(r.max_roughness_m, 2, " m")}`], ["Grid", `${r.grid_resolution_m} m, ${esc(r.engine)}`],
  ].map(([k, v]) => `<div>${k}<b>${v}</b></div>`).join("") + (r.is_test_fixture ? '<div style="grid-column:1/-1;color:#b00020">TEST FIXTURE - synthetic terrain</div>' : "");
  const pct = Math.min(100, e.required_min / e.usable_min * 100);
  $("budget").innerHTML = `<div class="hint">EVA time (estimate): ${e.required_min} of ${e.usable_min} usable min ${e.round_trip ? "(out + back)" : ""}</div>
    <div class="bar"><span class="${e.within_budget ? "" : "over"}" style="width:${pct}%"></span></div>
    ${r.space_weather ? `<div class="hint">Space weather: ${esc(r.space_weather.advisory.text || r.space_weather.status)}</div>` : ""}`;
  const wl = $("warnings"); wl.innerHTML = r.warnings.length ? "" : '<li class="info">No rule-based cautions triggered. This does not mean the route is safe.</li>';
  r.warnings.forEach((w) => {
    const li = document.createElement("li"); li.className = w.severity;
    li.innerHTML = `<b>${esc(w.title)}</b> <small>${esc(w.severity)} - at ${w.at_distance_km} km${w.length_m ? ", " + w.length_m + " m long" : ""}</small>
      ${esc(w.explanation)}<small>Rule: ${esc(w.rule)} | Data: ${esc((w.data_basis || []).join("; "))} | ${esc(w.measured_or_derived)}</small>`;
    li.onclick = () => { map.setView([w.location[1], w.location[0]], Math.max(map.getZoom(), 13)); L.popup().setLatLng([w.location[1], w.location[0]]).setContent(`<b>${esc(w.title)}</b><br>${esc(w.rule)}`).openOn(map); };
    wl.appendChild(li);
  });
  $("provenance").innerHTML = `<b>Data sources</b><ul>${r.data_sources.map((s) => `<li>${esc(s.role)}: ${link(s.url, s.label)} (${esc(s.mission)} / ${esc(s.instrument)})</li>`).join("")}</ul>
    <b>Assumptions</b><ul>${r.assumptions.map((a) => `<li>${esc(a)}</li>`).join("")}</ul><b>Limitations</b><ul>${r.limitations.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>
    <b>Stops</b><ul>${r.stops.map((s) => `<li>${esc(s.name)}: ETA ${s.eta_min} min, at ${s.at_distance_km} km${s.snapped_m > 0 ? `, moved ${s.snapped_m} m to walkable ground` : ""}</li>`).join("")}</ul>`;
  drawProfile(r.elevation_profile);
  $("missionLinks").innerHTML = "";
}

function drawProfile(pts) {
  const W = 340, H = 150, pad = { l: 42, r: 6, t: 8, b: 22 };
  if (!pts.length) { $("profileChart").innerHTML = ""; return; }
  const xs = pts.map((p) => p.distance_km), ys = pts.map((p) => p.elevation_m);
  const x0 = 0, x1 = Math.max(...xs) || 1, y0 = Math.min(...ys), y1 = Math.max(...ys) + 1e-6;
  const X = (v) => pad.l + (v - x0) / (x1 - x0) * (W - pad.l - pad.r), Y = (v) => H - pad.b - (v - y0) / (y1 - y0) * (H - pad.t - pad.b);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${X(p.distance_km).toFixed(1)},${Y(p.elevation_m).toFixed(1)}`).join("");
  const steep = pts.map((p, i) => i && p.grade_deg > (S.route.eva_params.caution_slope_deg) ? `<line x1="${X(pts[i - 1].distance_km)}" x2="${X(p.distance_km)}" y1="${Y(pts[i - 1].elevation_m)}" y2="${Y(p.elevation_m)}" stroke="#e8590c" stroke-width="3"/>` : "").join("");
  $("profileChart").innerHTML = `<svg viewBox="0 0 ${W} ${H}">
    <text x="2" y="${pad.t + 8}" font-size="9">${y1.toFixed(0)} m</text><text x="2" y="${H - pad.b}" font-size="9">${y0.toFixed(0)} m</text>
    <text x="${pad.l}" y="${H - 6}" font-size="9">0 km</text><text x="${W - 40}" y="${H - 6}" font-size="9">${x1.toFixed(2)} km</text>
    <path d="${d}" fill="none" stroke="#c1440e" stroke-width="1.6"/>${steep}
    <line id="pcur" x1="0" x2="0" y1="${pad.t}" y2="${H - pad.b}" stroke="#333" stroke-dasharray="2 2" visibility="hidden"/>
    <text id="ptxt" x="${pad.l + 4}" y="${pad.t + 10}" font-size="10"></text>
    <rect x="${pad.l}" y="0" width="${W - pad.l - pad.r}" height="${H}" fill="transparent" id="phit"/></svg>
    <div class="hint">Elevation profile (orange = grade above caution). Hover to locate on the map.</div>`;
  const svg = $("profileChart").querySelector("svg");
  svg.querySelector("#phit").onmousemove = (ev) => {
    const r = svg.getBoundingClientRect(); const vx = (ev.clientX - r.left) / r.width * W;
    const km = x0 + (vx - pad.l) / (W - pad.l - pad.r) * (x1 - x0);
    let best = pts[0]; for (const p of pts) if (Math.abs(p.distance_km - km) < Math.abs(best.distance_km - km)) best = p;
    const cur = svg.querySelector("#pcur"); cur.setAttribute("x1", X(best.distance_km)); cur.setAttribute("x2", X(best.distance_km)); cur.setAttribute("visibility", "visible");
    svg.querySelector("#ptxt").textContent = `${best.distance_km.toFixed(2)} km, ${best.elevation_m.toFixed(0)} m, ${best.grade_deg} deg`;
    if (!S.hoverMarker) S.hoverMarker = L.circleMarker([best.lat, best.lon], { radius: 6, color: "#000", fillColor: "#ffd43b", fillOpacity: 1, pane: "route" }).addTo(map);
    S.hoverMarker.setLatLng([best.lat, best.lon]);
  };
}

$("saveMission").onclick = async () => {
  if (!S.route) return;
  try {
    const m = await api("/missions", { method: "POST", body: JSON.stringify({ name: $("missionName").value || "Marswalk", region_id: S.region, route: S.route, science_stops: S.route.stops }) });
    $("missionLinks").innerHTML = `Saved ${esc(m.mission_id)}. Export: ${Object.entries(m.export).map(([k, u]) => `<a href="${u}">${k}</a>`).join(" | ")}`;
  } catch (e) { toast(e.message); }
};

// ---------------------------------------------------------------- space weather
async function loadSpaceWeather(refresh = false) {
  const hrs = parseFloat($("e_eva_hours").value) || 4;
  try {
    const s = await api(`/space-weather?eva_hours=${hrs}${refresh ? "&refresh=true" : ""}`);
    const a = s.advisory || {}; const rad = s.rad_reference;
    $("spaceWeather").innerHTML = `<div class="layer"><b>Advisory: ${esc(a.level || "unknown")}</b><br>${esc(a.text || "")}<br>
      <span class="hint">Status: ${esc(s.status)}${s.fetched_at ? ", fetched " + esc(s.fetched_at) : ""}${s.window ? ", window " + esc(s.window.join(" to ")) : ""}</span>
      ${s.counts ? `<br>Events in window: SEP ${s.counts.SEP}, flares M/X ${s.counts.FLR_M_or_X}, CME ${s.counts.CME}` : ""}
      ${s.latest && s.latest.SEP.length ? `<br>Latest SEP: ${s.latest.SEP.map((e) => link(e.link, e.time)).join(", ")}` : ""}
      <br>${link(s.source_url, s.source || "NASA CCMC DONKI")}<br><span class="hint">${esc(s.disclaimer)}</span></div>
      <div class="layer"><b>Measured reference:</b> ${rad.value} ${esc(rad.unit)} - ${esc(rad.quantity)}, ${esc(rad.where)}, ${esc(rad.period)} (${esc(rad.instrument)}).<br>
      For a ${hrs} h EVA this scale gives ~${s.eva_reference_dose_mSv.value} mSv. <span class="hint">${esc(s.eva_reference_dose_mSv.basis)}</span><br>
      ${link(rad.source_url, rad.source_title)}<br><span class="hint">${rad.notes.map(esc).join(" ")}</span></div>`;
  } catch (e) { $("spaceWeather").textContent = e.message; }
}
$("swRefresh").onclick = () => loadSpaceWeather(true);

// ---------------------------------------------------------------- assistant
$("askBtn").onclick = async () => {
  const q = $("askQ").value.trim(); if (!q) return;
  $("askOut").innerHTML = '<p class="hint">Searching the loaded documents...</p>';
  const c = map.getCenter();
  try {
    const r = await api("/assistant/ask", { method: "POST", body: JSON.stringify({ question: q, region_id: S.region, lon: c.lng, lat: c.lat }) });
    $("askOut").innerHTML = `<div class="layer"><b>${r.found ? "Answer" : "Not found"}</b> <span class="hint">(${esc(r.mode)}${r.offline ? ", offline" : ""})</span><br>${esc(r.answer)}
      ${r.note ? `<br><span class="hint">${esc(r.note)}</span>` : ""}</div>` +
      r.citations.map((c) => `<div class="cite">[${c.n}] ${link(c.url, c.title)} (${esc(c.date || "n.d.")})</div>`).join("");
  } catch (e) { $("askOut").textContent = e.message; }
};
$("askQ").onkeydown = (e) => { if (e.key === "Enter") $("askBtn").click(); };

// ---------------------------------------------------------------- offline
async function loadOffline() {
  try {
    const m = await api(`/offline/package?region_id=${S.region}`);
    const r = m.ready_offline;
    $("offlineInfo").innerHTML = `Data date: ${esc(m.data_date || "n/a")} (processed ${esc(m.processed_at)})<br>
      Terrain &amp; layers: ${r.terrain_and_layers ? "ready" : "missing"} (${(m.region_bytes / 1e6).toFixed(1)} MB)<br>
      Context tiles cached: ${m.tiles.count} | Space-weather cache: ${r.space_weather_cache ? esc(m.space_weather_fetched_at) : "none"} | Assistant index: ${r.assistant_index ? "ready" : "none"}<br>${esc(m.note)}`;
    $("zipLink").href = `${API}/offline/package?region_id=${S.region}&download=true`;
  } catch (e) { $("offlineInfo").textContent = e.message; }
}
$("prefetchBtn").onclick = async () => {
  $("prefetchBtn").disabled = true; toast("Caching tiles, space weather and assistant index... this can take a few minutes.", 6000);
  try { const r = await api(`/offline/prefetch?region_id=${S.region}`, { method: "POST" }); toast(`Cached ${r.tiles_ok} tiles. Space weather: ${r.donki}.`, 6000); await loadOffline(); }
  catch (e) { toast(e.message, 6000); } finally { $("prefetchBtn").disabled = false; }
};

async function pollStatus() {
  try {
    const s = await api("/status");
    const b = $("netBadge");
    const date = S.regionInfo && S.regionInfo.data_date;
    if (s.online) { b.textContent = "Online"; b.className = "badge"; }
    else { b.textContent = `Offline - using packaged data${date ? " from " + date : ""}`; b.className = "badge off"; }
  } catch (e) { $("netBadge").textContent = "Backend not reachable"; $("netBadge").className = "badge warn"; }
}

// ---------------------------------------------------------------- boot
if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
(async () => {
  try { await loadDefaults(); await loadRegions(); } catch (e) { $("routeMsg").className = "msg err"; $("routeMsg").textContent = "Startup failed: " + e.message; }
  pollStatus(); setInterval(pollStatus, 30000);
})();
