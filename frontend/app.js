/* MarsPath simple frontend (plain JS + Leaflet). The backend owns every scientific value:
   this page only displays what the API returns and never recalculates or invents data. */
const API = "/api/v1";
const S = { region: null, regionInfo: null, mode: null, points: { start: null, stops: [], end: null },
            layers: {}, route: null, routeLayer: null, cmpLayers: [], hoverMarker: null, defaults: null };

// ---------------------------------------------------------------- helpers
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const NA = "not available";
const isNum = (v) => v !== null && v !== undefined && v !== "" && Number.isFinite(Number(v));
const fmt = (v, d = 1, u = "") => (isNum(v) ? `${Number(v).toFixed(d)}${u}` : NA);
// minutes -> "2 h 10 min" (formatting only; the minutes come from the API)
const hm = (min) => { if (!isNum(min)) return NA; const t = Math.round(Number(min)); const h = Math.floor(t / 60), m = t % 60; return h ? `${h} h${m ? " " + m + " min" : ""}` : `${m} min`; };
// small "?" help button; the text is shown by the shared #tip element (works with mouse, keyboard and touch)
const qTip = (text, label = "More information") => `<button type="button" class="q" aria-label="${esc(label)}" data-tip="${esc(text)}">?</button>`;
(() => {
  const tip = document.getElementById("tip");
  const show = (btn) => {
    tip.textContent = btn.dataset.tip; tip.classList.remove("hidden");
    const r = btn.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight;
    let x = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), window.innerWidth - w - 8);
    let y = r.bottom + 6; if (y + h > window.innerHeight - 8) y = r.top - h - 6;
    tip.style.left = `${x}px`; tip.style.top = `${y}px`;
  };
  const hide = () => tip.classList.add("hidden");
  const target = (e) => e.target.closest && e.target.closest(".q[data-tip]");
  document.addEventListener("mouseover", (e) => { const b = target(e); if (b) show(b); });
  document.addEventListener("mouseout", (e) => { if (target(e)) hide(); });
  document.addEventListener("focusin", (e) => { const b = target(e); if (b) show(b); });
  document.addEventListener("focusout", (e) => { if (target(e)) hide(); });
  document.addEventListener("click", (e) => { const b = target(e); if (b) { e.preventDefault(); e.stopPropagation(); show(b); } }, true);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") hide(); });
  window.addEventListener("scroll", hide, true);
})();
function toast(t, ms = 3500) { const el = $("toast"); el.textContent = t; el.classList.remove("hidden"); clearTimeout(toast._t); toast._t = setTimeout(() => el.classList.add("hidden"), ms); }
async function api(path, opts = {}) {
  const r = await fetch(API + path, { headers: { "Content-Type": "application/json" }, ...opts });
  let body = null; try { body = await r.json(); } catch (_) {}
  if (!r.ok) { const d = body && body.detail; const msg = (d && (d.message || (Array.isArray(d) ? d.map(x => x.msg).join("; ") : JSON.stringify(d)))) || r.statusText; throw new Error(msg); }
  return body;
}
// pop-up content as a DOM element, so Leaflet keeps loaded content when the pop-up re-lays out or reopens
const htmlEl = (html) => { const d = document.createElement("div"); d.innerHTML = html; return d; };
const link = (url, text) => url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(text || "source")}</a>` : esc(text || "");

// ---------------------------------------------------------------- map
// Mars Trek EQ tiles are plate carree, so the map uses Leaflet's EPSG4326 CRS (lon/lat degrees).
// Same projection, but distances (scale bar) use the Mars 2000 sphere radius instead of Earth's.
const MARS_CRS = L.extend({}, L.CRS.EPSG4326, { R: 3396190 });
const map = L.map("map", { crs: MARS_CRS, center: [18.44, 77.43], zoom: 3, minZoom: 1, maxZoom: 17, worldCopyJump: false });
L.control.scale({ imperial: false }).addTo(map);
L.Popup.mergeOptions({ autoPanPaddingTopLeft: L.point(60, 20), autoPanPaddingBottomRight: L.point(20, 30) });  // keep pop-ups clear of the zoom buttons
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
  showPointInfo(e.latlng);
});

// ---------------------------------------------------------------- "What's here?" (GET /point-info)
const distTxt = (m) => (!isNum(m) ? NA : m < 1000 ? fmt(m, 0, " m") : fmt(m / 1000, 2, " km"));
async function showPointInfo(latlng) {
  const lon = latlng.lng, lat = latlng.lat, token = (showPointInfo._n = (showPointInfo._n || 0) + 1);
  const pop = L.popup({ maxWidth: 330, minWidth: 260, maxHeight: 420, className: "pi-popup" })
    .setLatLng(latlng).setContent('<span class="hint">Reading what MarsPath knows about this point...</span>').openOn(map);
  const ev = evaOverrides();
  const q = new URLSearchParams({ region_id: S.region, lon, lat });
  ["max_slope_deg", "roughness_max_m", "eva_hours"].forEach((k) => { if (isNum(ev[k])) q.set(k, ev[k]); });
  if (S.points.start) { q.set("from_lon", S.points.start.lon); q.set("from_lat", S.points.start.lat); }
  let d;
  try { d = await api(`/point-info?${q}`); }
  catch (err) {
    if (token !== showPointInfo._n) return;
    pop.setContent(/outside/i.test(err.message) ? "<b>Outside the prepared region</b><br><span class=\"hint\">MarsPath only has terrain data inside the region box.</span>"
      : `<b>What's here?</b><br><span class="msg err">${esc(err.message)}</span>`);
    return;
  }
  if (token !== showPointInfo._n) return;  // a newer click replaced this one
  if (d.inside === false) { pop.setContent(`<b>Outside the prepared region</b><br><span class="hint">${esc(d.message || "")}</span>`); return; }
  pop.setContent(pointInfoHtml(d));
}

function pointInfoHtml(d) {
  const t = d.terrain || {}, n = d.neighbourhood || {}, g = d.geology, lim = d.eva_limits || {};
  const row = (k, v) => `<tr><th>${esc(k)}</th><td>${v}</td></tr>`;
  const limits = `slope up to ${fmt(lim.max_slope_deg, 0, " deg")}, roughness up to ${fmt(lim.roughness_max_m, 2, " m")}`;
  const walk = d.walkable
    ? `<div class="pi-walk ok"><b>Walkable under the current EVA limits</b><br><span>${esc(limits)}. Model-derived from the elevation grid; not a statement that the ground is safe.</span></div>`
    : `<div class="pi-walk bad"><b>Outside the current EVA limits</b> (the planner will not route here)<ul>${(d.not_walkable_because || []).map((x) => `<li>${esc(x)}</li>`).join("") || `<li>reason ${NA}</li>`}</ul></div>`;
  const dem = t.dem_source === "primary" ? "high-resolution DEM" : t.dem_source === "fallback" ? "lower-resolution fallback DEM" : t.dem_source ? esc(t.dem_source) : NA;
  const geo = g ? row("Unit", esc(g.unit || NA)) +
      row("Walking time", isNum(g.walking_time_multiplier) ? `x${esc(g.walking_time_multiplier)} ${g.walking_time_multiplier === 1 ? "(no slow-down)" : "(slower here)"}` : NA) +
      (g.reason ? row("Why", esc(g.reason)) : "") + row("Source", esc(g.source || NA))
    : row("Unit", NA);
  const w = d.walk_from_start;
  const walkFrom = !w ? "" : `<h5>Walk from your start point</h5>` + (w.error
    ? `<p class="msg err">${esc(w.message || w.error)}</p>`
    : `<table>${row("Path length", fmt(w.distance_km, 2, " km"))}${row("Time there", hm(w.outbound_min))}${row("Time back", hm(w.return_min))}
       ${row("EVA budget", w.within_eva_budget === true ? `<span class="ok">there and back fits the ${hm(w.usable_min)} usable</span>` : w.within_eva_budget === false ? `<span class="bad">there and back exceeds the ${hm(w.usable_min)} usable</span>` : NA)}</table>
       <div class="hint">Fastest profile, model estimate.</div>`);
  const s = d.nearest_science_site, rv = d.nearest_rover_stop, hz = d.nearest_hazard_zone;
  const goBtn = (lon, lat) => (isNum(lon) && isNum(lat) ? ` <button type="button" class="mini" onclick="piGo(${Number(lon)},${Number(lat)})">show</button>` : "");
  const near = row("Science site", s ? `${esc(s.name || NA)}, ${distTxt(s.distance_m)}${s.goal_id ? ` (goal ${esc(s.goal_id)})` : ""}${goBtn(s.lon, s.lat)}` : NA) +
    row("Rover stop", rv ? `Perseverance sol ${esc(rv.sol ?? NA)}, ${distTxt(rv.distance_m)}${goBtn(rv.lon, rv.lat)}` : NA) +
    row("Hazard zone", hz ? `${esc(String(hz.type || NA).replace(/_/g, " "))}${hz.severity ? ` (${esc(hz.severity)})` : ""}, ${distTxt(hz.distance_m)} to its centre<br><span class="hint">${esc(hz.rule || "")}</span>` : NA);
  const L5 = (v) => isNum(v) ? Number(v).toFixed(5) : NA;
  return `<div class="pi">
    <b class="pi-title">What's here?</b>${d.is_test_fixture ? ' <span class="pi-fixture">TEST FIXTURE</span>' : ""}
    <div class="hint">lon ${L5(d.lon)} E, lat ${L5(d.lat)} (planetocentric)</div>
    ${walk}
    <h5>Terrain at this point</h5><table>${row("Elevation", fmt(t.elevation_m, 1, " m"))}${row("Slope", fmt(t.slope_deg, 1, " deg"))}${row("Roughness", fmt(t.roughness_m, 2, " m"))}${row("Data", dem)}</table>
    <div class="hint">${esc(t.data_basis || "")}</div>
    <h5>${isNum(n.radius_m) ? `Within ${fmt(n.radius_m, 0, " m")}` : "Nearby"}</h5><table>${row("Steepest slope", fmt(n.max_slope_deg, 1, " deg"))}${row("Roughest", fmt(n.max_roughness_m, 2, " m"))}${row("Height range", fmt(n.relief_m, 1, " m"))}</table>
    <h5>Geology</h5><table>${geo}</table>
    ${walkFrom}
    <h5>Nearest (straight-line distance)</h5><table>${near}</table>
    <div class="row pi-actions"><button type="button" onclick="piSet('start',${d.lon},${d.lat})">Set as start</button><button type="button" onclick="piSet('stop',${d.lon},${d.lat})">Add as stop</button><button type="button" onclick="piSet('end',${d.lon},${d.lat})">Set as destination</button><button type="button" onclick="piRange(${d.lon},${d.lat})">Walking range from here</button></div>
  </div>`;
}
window.piGo = (lon, lat) => { map.closePopup(); map.setView([lat, lon], Math.max(map.getZoom(), 14)); };
window.piSet = (kind, lon, lat) => {
  const p = { lon, lat, name: null };
  if (kind === "start") S.points.start = p; else if (kind === "end") S.points.end = p; else S.points.stops.push(p);
  renderPoints(); map.closePopup(); toast(kind === "start" ? "Start set" : kind === "end" ? "Destination set" : "Stop added");
};

function setMode(m) {
  S.mode = m;
  document.querySelectorAll("button[data-mode]").forEach((b) => b.classList.toggle("active", b.dataset.mode === m));
  $("modeHint").textContent = m ? `Click the map to place the ${m === "stop" ? "science stop(s) - click the button again to finish" : m}.` :
    "Pick a button, then click the map. Click the map with no button selected to see what's there.";
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
  S.regions = r.regions;
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
  clearRoute(); clearRange(); searchLayer.clearLayers(); $("searchQ").value = ""; SR.results = [];
  S.points = { start: null, stops: [], end: null }; renderPoints();
  const b = info.bbox; map.fitBounds([[b.south, b.west], [b.north, b.east]]);
  const ls = await api(`/layers?region_id=${id}`);
  S.sources = ls.sources || {};
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
  renderDashboard();
  loadValidation();
}

// ---------------------------------------------------------------- rover benchmark (GET /validation; real Jezero data only)
async function loadValidation() {
  const box = $("validation"), rid = S.region;
  box.innerHTML = '<span class="hint">Loading...</span>';
  let v;
  try { v = await api(`/validation?region_id=${encodeURIComponent(rid)}`); }
  catch (e) {
    if (rid !== S.region) return;
    box.innerHTML = `<p class="hint"><b>Rover benchmark not available for this region.</b> It needs real Jezero data and the
      validate_against_rover.py script${S.regionInfo && S.regionInfo.is_test_fixture ? " (this region is a synthetic test fixture)" : ""}.</p>`;
    return;
  }
  if (rid !== S.region) return;
  const rows = Object.entries(v.summary || {}).map(([p, s]) => s
    ? `<tr><td><b>${esc(p)}</b></td><td>${fmt(s.median_of_medians_m, 0, " m")}</td><td>${fmt(s.baseline_median_of_medians_m, 0, " m")}</td><td>${esc(s.closer_than_straight_line ?? NA)}</td><td>${esc(s.segments ?? NA)}</td></tr>`
    : `<tr><td><b>${esc(p)}</b></td><td colspan="4">${NA}</td></tr>`).join("");
  box.innerHTML = `<p>${esc(v.method || "")}</p>
    ${rows ? `<table><tr><th>profile</th><th>median distance to rover track</th><th>straight line</th><th>closer</th><th>stretches</th></tr>${rows}</table>` : `<p>Summary ${NA}.</p>`}
    <p class="hint">Lower distance = closer to where Perseverance actually drove.</p>
    ${(v.caveats || []).length ? `<ul>${v.caveats.map((c) => `<li class="hint">${esc(c)}</li>`).join("")}</ul>` : ""}
    ${(v.data || []).length ? `<p class="hint">Data: ${v.data.map(esc).join("; ")}</p>` : ""}`;
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
    const photoBtn = `<button type="button" class="gv-btn" ${rover ? "" : `data-site="${esc(p.id || "")}"`} data-lon="${lon}" data-lat="${lat}">Show rover photos</button><div class="gv"></div>`;
    m.bindPopup(htmlEl((rover ?
      `<b>${esc(p.name)}</b><br>Mission: ${esc(p.mission)}<br>Sol: ${esc(p.sol)}<br>lon ${lon.toFixed(5)}, lat ${lat.toFixed(5)}<br>
       <i>${esc(p.measured_or_derived)}</i><br>${link(p.source_url, p.source)}<br>${link(p.raw_images_url, "Perseverance raw images (filter by sol " + esc(p.sol) + ")")}
       <br><button onclick="addStop(${lon},${lat},'${esc(p.name).replace(/'/g, "")}')">Add as stop</button> ` :
      `<b>${esc(p.name)}</b><br>${esc(p.observation || "")}<br>Mission/instrument: ${esc(p.mission)} / ${esc(p.instrument)}<br>
       Date: ${esc(p.observation_date || NA)}<br>Goal: ${esc(p.goal_id || "")} - ${esc(p.why_it_matters || "")}<br>
       <i>${esc(p.measured_or_derived)}</i><br>${link(p.source_url, p.source)}
       <br><button onclick="addStop(${lon},${lat},'${esc(p.name).replace(/'/g, "")}')">Add as stop</button> `) + photoBtn), { maxWidth: 330, minWidth: 240 });
  });
}
// ---------------------------------------------------------------- rover photos (GET /ground-view)
map.on("popupopen", (e) => { S.openPopup = e.popup; });
const utcTxt = (s) => (s ? `${String(s).slice(0, 10)} ${String(s).slice(11, 16)} UTC` : `date ${NA}`);
document.addEventListener("click", async (e) => {
  const btn = e.target.closest && e.target.closest(".gv-btn"); if (!btn) return;
  const box = btn.nextElementSibling; if (!box) return;
  const q = new URLSearchParams({ region_id: S.region, max_images: 6 });
  if (btn.dataset.site) q.set("site_id", btn.dataset.site); else { q.set("lon", btn.dataset.lon); q.set("lat", btn.dataset.lat); }
  btn.disabled = true; btn.textContent = "Loading rover photos...";
  box.innerHTML = '<p class="hint">Looking up the nearest Perseverance stop and its images (the first time can take a few seconds online)...</p>';
  const refresh = () => { if (S.openPopup) S.openPopup.update(); };
  refresh();
  try { box.innerHTML = groundViewHtml(await api(`/ground-view?${q}`)); btn.remove(); }
  catch (err) { box.innerHTML = `<p class="msg err">Rover photos ${NA}: ${esc(err.message)}</p>`; btn.disabled = false; btn.textContent = "Try again"; }
  box.querySelectorAll("img").forEach((im) => {
    im.onload = refresh;
    im.onerror = () => { const ph = document.createElement("div"); ph.className = "gv-ph"; ph.textContent = "Image could not load (needs internet, not cached)"; im.replaceWith(ph); refresh(); };
  });
  refresh();
}, true);  // capture phase: Leaflet stops click bubbling inside pop-ups

function groundViewHtml(d) {
  const stop = d.rover_stop || {};
  const fixture = S.regionInfo && S.regionInfo.is_test_fixture
    ? `<p class="gv-fixture">TEST FIXTURE: the rover stop here is synthetic. ${d.available ? `These are real Perseverance photos from sol ${esc(stop.sol ?? NA)} at Jezero, not pictures of this place.` : ""}</p>` : "";
  const sols = (d.sols_searched || []).length ? `sols ${esc(d.sols_searched[0])}${d.sols_searched.length > 1 ? "-" + esc(d.sols_searched[d.sols_searched.length - 1]) : ""}` : `sols ${NA}`;
  const head = d.rover_stop ? `<div class="hint">Nearest rover stop: sol ${esc(stop.sol ?? NA)}, ${distTxt(stop.distance_m)} away. Searched ${sols}.</div>` : "";
  if (!d.available) {
    const st = Object.entries(d.fetch_status || {}).map(([s, v]) => `sol ${esc(s)}: ${esc(v)}`).join("; ");
    return `${fixture}${head}<p class="msg">No rover photos available here${d.offline ? " offline (they were not cached before going offline)" : ""}.</p>
      ${d.reason ? `<p class="hint">${esc(d.reason)}</p>` : ""}${st ? `<p class="hint">${st}</p>` : ""}`;
  }
  const imgs = (d.images || []).map((x) => {
    const small = x.local_small_url || (d.offline ? null : x.small_url);
    const big = x.local_medium_url || (d.offline ? null : x.medium_url) || small;
    const cap = `${x.camera_label || x.camera || "camera " + NA}, sol ${x.sol ?? NA}, ${utcTxt(x.date_taken_utc)}`;
    const pic = small ? `<img src="${esc(small)}" alt="${esc(cap)}" loading="lazy">` : '<div class="gv-ph">Not cached for offline use</div>';
    return `<figure class="gv-item">${small ? `<button type="button" class="gv-open" data-big="${esc(big)}" data-cap="${esc(cap + " - " + (x.credit || "NASA/JPL-Caltech"))}" data-page="${esc(x.nasa_page || "")}">${pic}</button>` : pic}
      <figcaption>${esc(x.camera_label || x.camera || NA)}<br>sol ${esc(x.sol ?? NA)}, ${esc(utcTxt(x.date_taken_utc))}<br><span class="hint">${esc(x.credit || "NASA/JPL-Caltech")}${x.local_small_url ? " - cached" : ""}</span></figcaption></figure>`;
  }).join("");
  return `${fixture}${head}<div class="gv-grid">${imgs}</div>
    <div class="hint">Showing ${esc((d.images || []).length)} of ${esc(d.images_total ?? NA)} ground images. Source: ${link(d.source_url, d.source || "NASA Perseverance raw images")}${d.offline ? " (offline: cached copies only)" : ""}.</div>
    <ul class="gv-notes">${(d.notes || []).map((n) => `<li>${esc(n)}</li>`).join("")}</ul>`;
}

// enlarged photo view
document.addEventListener("click", (e) => {
  const b = e.target.closest && e.target.closest(".gv-open"); if (!b) return;
  const lb = $("lightbox");
  lb.querySelector("img").src = b.dataset.big; lb.querySelector("img").alt = b.dataset.cap;
  lb.querySelector(".lb-cap").innerHTML = esc(b.dataset.cap) + (b.dataset.page ? ` - ${link(b.dataset.page, "NASA image page")}` : "");
  lb.classList.remove("hidden"); lb.querySelector(".lb-close").focus();
}, true);
$("lightbox").onclick = (e) => { if (e.target.id === "lightbox" || e.target.classList.contains("lb-close")) $("lightbox").classList.add("hidden"); };
document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("lightbox").classList.add("hidden"); });

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
  if (S.hoverMarker) map.removeLayer(S.hoverMarker); S.hoverMarker = null; clearStepHighlight(); S.route = null; S.routeLayer = null; $("resultsBox").classList.add("hidden");
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
  const rows = r.comparison.map((c) => `<tr><td style="color:${colors[c.profile]}"><b>${c.profile}</b></td><td>${c.distance_km}</td><td>${c.duration_min}</td><td>${c.max_slope_deg}</td><td>${c.ascent_m}</td><td>${c.within_budget ? "yes" : "NO"}</td><td>${c.warnings}</td></tr>`).join("");
  $("compare").innerHTML = `<h4>Profile comparison</h4><table><tr><th>profile</th><th>km</th><th>min out</th><th>max grade</th><th>ascent m</th><th>in budget</th><th>warn</th></tr>${rows}</table>
    ${r.errors.length ? `<p class="msg err">${r.errors.map((e) => esc(e.profile + ": " + e.message)).join("<br>")}</p>` : ""}<p class="hint">Solid line = fastest; dashed = others. Click a table row's profile in the dropdown and Calculate to see its details.</p>`;
});

// ---------------------------------------------------------------- plain-language route explanation
// Wording only. Every number shown comes from the route response (or its eva_params).
const TIP = {
  distance: "Length of the planned walking path in kilometres, measured horizontally on the Mars 2000 sphere (hills do not add length).",
  straight: "Distance between your points as the crow flies, in kilometres, for comparison. The walking path is longer because it bends around ground outside the EVA limits.",
  timeOut: "Modelled walking time from start to destination, in minutes. It comes from the EVA walking model (Tobler's hiking function, suit speed and load are team assumptions). An estimate, not a measurement.",
  timeBack: "Modelled time to walk the same path back to the start, in minutes. It differs from the time out because walking uphill and downhill take different times.",
  maxGrade: (p) => `Steepest slope in the direction you walk, in degrees, computed from numerical elevation data. Your caution level is ${fmt(p.caution_slope_deg, 0, " deg")}; ground steeper than ${fmt(p.max_slope_deg, 0, " deg")} is never routed.`,
  meanGrade: "Average slope along the direction of walking, in degrees, weighted by distance.",
  terrainSlope: "Steepest slope of any grid square the path crosses, in degrees, measured in the steepest direction of that square (not only the walking direction). Usually higher than the grade you actually walk.",
  ascent: "Total height gained on all uphill parts of the walk, in metres.",
  descent: "Total height lost on all downhill parts of the walk, in metres.",
  elev: "Lowest and highest point of the path, in metres, from the region's elevation model (DEM). Mars has no sea level: heights are relative to the DEM's reference surface.",
  rough: (p) => `How bumpy the ground is, in metres: how much the height varies locally once the overall slope is removed (detrended RMS height). High values hint at boulders, ridges or scarp edges. Caution above ${fmt(p.roughness_caution_m, 2, " m")}; ground rougher than ${fmt(p.roughness_max_m, 2, " m")} is never routed.`,
  grid: "Size of each terrain square the route planner works on, in metres. Features smaller than this (single rocks) are not seen. The planner is A* search, a standard shortest-path method.",
  budget: (r) => `Time in the suit (EVA) is limited. Usable time = EVA length minus a safety reserve (team assumptions). The bar shows the modelled time needed${r.eva && r.eva.round_trip ? " to walk out and back" : ""} against the usable time. Red means over the budget.`,
  profile: "Side view of the walk: distance along the bottom, height up the side. Orange parts are steeper than your caution slope. Hover to see the point on the map.",
};

function metricCards(r) {
  const p = r.eva_params || {};
  const elev = isNum(r.elevation_min_m) && isNum(r.elevation_max_m) ? `${fmt(r.elevation_min_m, 0)} to ${fmt(r.elevation_max_m, 0)} m` : NA;
  return [
    ["Walking distance", fmt(r.distance_km, 2, " km"), TIP.distance],
    ["Straight-line distance", fmt(r.straight_line_km, 2, " km"), TIP.straight],
    ["Time out", hm(r.duration_min), TIP.timeOut],
    ["Time back", hm(r.return_duration_min), TIP.timeBack],
    ["Steepest grade walked", fmt(r.max_slope_deg, 1, " deg"), TIP.maxGrade(p)],
    ["Average grade", fmt(r.mean_slope_deg, 1, " deg"), TIP.meanGrade],
    ["Steepest ground crossed", fmt(r.max_terrain_slope_deg, 1, " deg"), TIP.terrainSlope],
    ["Total climb", fmt(r.ascent_m, 1, " m"), TIP.ascent],
    ["Total descent", fmt(r.descent_m, 1, " m"), TIP.descent],
    ["Lowest / highest point", elev, TIP.elev],
    ["Bumpiest ground", fmt(r.max_roughness_m, 2, " m"), TIP.rough(p)],
    ["Terrain grid", fmt(r.grid_resolution_m, 0, " m squares"), TIP.grid + (r.engine ? ` Engine: ${r.engine}.` : "")],
  ].map(([k, v, t]) => `<div><span class="mlabel">${esc(k)} ${qTip(t, "About " + k)}</span><b>${esc(v)}</b></div>`).join("");
}

function routeSummary(r) {
  const e = r.eva || {};
  const n = { warning: 0, caution: 0, info: 0 }; (r.warnings || []).forEach((w) => { if (w.severity in n) n[w.severity]++; });
  const plural = (k, one, many) => `${k} ${k === 1 ? one : many}`;
  const counts = [n.warning && plural(n.warning, "warning", "warnings"), n.caution && plural(n.caution, "caution", "cautions"), n.info && plural(n.info, "note", "notes")].filter(Boolean);
  const parts = [
    `${fmt(r.distance_km, 2, " km")}`,
    (isNum(r.duration_min) ? `about ${hm(r.duration_min)} out` : `time out ${NA}`) + (e.round_trip && isNum(e.required_min) ? ` (${hm(e.required_min)} there and back)` : ""),
    `steepest grade ${fmt(r.max_slope_deg, 1, " deg")}`,
    counts.length ? counts.join(", ") : "no rule-based cautions",
  ];
  const budget = e.within_budget === true ? '<span class="ok">fits the EVA budget</span>' : e.within_budget === false ? '<span class="bad">over the EVA budget</span>' : "";
  return `<b>${esc((r.profile || "").replace(/^./, (c) => c.toUpperCase()))} route:</b> ${esc(parts.join(", "))}${budget ? " - " + budget : ""}.
    <span class="hint">All values are model estimates${r.is_test_fixture ? " on synthetic test terrain" : ""}.</span>`;
}

// Plain-English name per backend rule id, plus how to label its value and threshold.
const RULES = {
  R1_STEEP_GRADE: { name: "Steep slope", val: "Steepest grade here", lim: "Caution level", hard: (p) => isNum(p.max_slope_deg) && `never routed above ${fmt(p.max_slope_deg, 0, " deg")}` },
  R2_ROUGH: { name: "Rough, bumpy ground", val: "Highest roughness here", lim: "Caution level", hard: (p) => isNum(p.roughness_max_m) && `never routed above ${fmt(p.roughness_max_m, 2, " m")}` },
  R3_GEOLOGIC_UNIT: { name: "Slow-going ground type", val: "Walking-time multiplier", lim: "Limit" },
  R4_LOW_RES_DEM: { name: "Less detailed terrain data", val: "Value", lim: "Limit" },
  R5_EVA_BUDGET: { name: "Suit time budget", val: "Time needed", lim: "Usable time" },
  R6_POINT_MOVED: { name: "Your point was moved", val: "Moved by", lim: "Limit" },
  R7_SPACE_WEATHER: { name: "Recent solar particle activity", val: "Value", lim: "Limit" },
};
const SEVERITY = { warning: "Warning", caution: "Caution", info: "Note" };

function warningCard(w) {
  const rule = RULES[w.rule_id] || { name: w.title, val: "Value", lim: "Limit" };
  const p = (S.route && S.route.eva_params) || {};
  const withUnit = (v) => (w.unit === "x time" ? `x${v} walking time` : `${v}${w.unit ? " " + w.unit : ""}`);
  const vals = [];
  if (isNum(w.value)) vals.push(`${rule.val}: <b>${esc(withUnit(w.value))}</b>`);
  if (isNum(w.threshold)) vals.push(`${rule.lim}: <b>${esc(withUnit(w.threshold))}</b>`);
  const hard = rule.hard && rule.hard(p); if (hard) vals.push(esc(hard));
  const where = isNum(w.at_distance_km) ? `at ${fmt(w.at_distance_km, 2, " km")} along the route${isNum(w.length_m) && w.length_m > 0 ? `, ${fmt(w.length_m, 0, " m")} long` : ""}` : "";
  return `<div class="wtop"><span class="sev">${esc(SEVERITY[w.severity] || w.severity)}</span> <b>${esc(rule.name)}</b></div>
    <div class="wsub">${esc(w.title)}${where ? " - " + esc(where) : ""}</div>
    <div>${esc(w.explanation)}</div>
    ${vals.length ? `<div class="wvals">${vals.join(" &middot; ")}</div>` : ""}
    <small>Data: ${esc((w.data_basis || []).join("; ") || NA)} (${esc(w.measured_or_derived || NA)})<br>Rule ${esc((w.rule_id || "").split("_")[0])}: ${esc(w.rule)}</small>`;
}

function showRoute(r) {
  S.route = r;
  S.routeLayer = L.geoJSON(r.geometry, { pane: "route", style: { color: "#ff6b00", weight: 4 } }).addTo(map)
    .bindPopup(`<b>${esc(r.route_id)}</b> (${esc(r.profile_label)})<br>${r.distance_km} km, ${r.duration_min} min out<br>${r.assumptions.slice(0, 2).map(esc).join("<br>")}`);
  map.fitBounds(S.routeLayer.getBounds(), { padding: [30, 30] });
  $("resultsBox").classList.remove("hidden"); $("resultsBox").open = true;
  const e = r.eva || {};
  $("routeSummary").innerHTML = routeSummary(r);
  $("metrics").innerHTML = metricCards(r) +
    (r.is_test_fixture ? '<div class="fixture-note">TEST FIXTURE - synthetic terrain: these numbers are not real Mars data.</div>' : "");
  const pct = isNum(e.required_min) && isNum(e.usable_min) && e.usable_min > 0 ? Math.min(100, e.required_min / e.usable_min * 100) : 0;
  $("budget").innerHTML = `<div class="hint"><b>EVA time budget</b> ${qTip(TIP.budget(r), "What is the EVA time budget?")}
      ${e.round_trip ? "Out and back" : "One way"}: ${fmt(e.required_min, 0, " min")} needed of ${fmt(e.usable_min, 0, " min")} usable
      (${fmt(e.budget_min, 0, " min")} EVA minus reserve) - <b class="${e.within_budget ? "ok" : "bad"}">${e.within_budget ? "fits the budget" : e.within_budget === false ? "over the budget" : NA}</b> (model estimate)</div>
    <div class="bar" role="img" aria-label="${fmt(e.required_min, 0)} of ${fmt(e.usable_min, 0)} usable minutes"><span class="${e.within_budget ? "" : "over"}" style="width:${pct}%"></span></div>
    ${r.space_weather ? `<div class="hint">Space weather: ${esc((r.space_weather.advisory || {}).text || r.space_weather.status)}</div>` : ""}`;
  const wl = $("warnings"); wl.innerHTML = r.warnings.length ? "" : '<li class="info">No rule-based cautions triggered. This does not mean the route is safe.</li>';
  r.warnings.forEach((w) => {
    const li = document.createElement("li"); li.className = w.severity; li.tabIndex = 0;
    li.innerHTML = warningCard(w);
    const go = () => { if (!w.location) return; map.setView([w.location[1], w.location[0]], Math.max(map.getZoom(), 13)); L.popup().setLatLng([w.location[1], w.location[0]]).setContent(`<b>${esc(w.title)}</b><br>${esc(w.rule)}`).openOn(map); };
    li.onclick = go; li.onkeydown = (ev) => { if (ev.key === "Enter") go(); };
    wl.appendChild(li);
  });
  $("provenance").innerHTML = `<b>Data sources</b><ul>${r.data_sources.map((s) => `<li>${esc(s.role)}: ${link(s.url, s.label)} (${esc(s.mission)} / ${esc(s.instrument)})</li>`).join("")}</ul>
    <b>Assumptions</b><ul>${r.assumptions.map((a) => `<li>${esc(a)}</li>`).join("")}</ul><b>Limitations</b><ul>${r.limitations.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>
    <b>Stops</b><ul>${r.stops.map((s) => `<li>${esc(s.name)}: ETA ${s.eta_min} min, at ${s.at_distance_km} km${s.snapped_m > 0 ? `, moved ${s.snapped_m} m to walkable ground` : ""}</li>`).join("")}</ul>`;
  drawProfile(r.elevation_profile);
  renderDirections(r);
  $("missionLinks").innerHTML = "";
}

// ---------------------------------------------------------------- turn-by-turn directions
function clearStepHighlight() {
  if (S.stepLayer) { map.removeLayer(S.stepLayer); S.stepLayer = null; }
  document.querySelectorAll("#directions li.active").forEach((li) => li.classList.remove("active"));
}

// Path of one step: the step's own start/end plus the route's profile points between this step's
// at_distance_km and the next step's (display only; nothing is recalculated).
function stepPath(r, i) {
  const d = r.directions[i], next = r.directions[i + 1];
  if (!Array.isArray(d.start) || !Array.isArray(d.end)) return null;
  const a = d.at_distance_km, b = next && isNum(next.at_distance_km) ? next.at_distance_km : Infinity;
  const mid = isNum(a) ? (r.elevation_profile || []).filter((p) => p.distance_km > a && p.distance_km < b).map((p) => [p.lat, p.lon]) : [];
  return [[d.start[1], d.start[0]], ...mid, [d.end[1], d.end[0]]];
}

function renderDirections(r) {
  const ol = $("directions"); ol.innerHTML = ""; clearStepHighlight();
  const steps = r.directions || [];
  if (!steps.length) { ol.innerHTML = `<li class="none">Directions ${NA} for this route.</li>`; return; }
  steps.forEach((d, i) => {
    const li = document.createElement("li");
    const path = stepPath(r, i);
    if (!path) { li.className = "none"; li.textContent = d.instruction || `Directions ${NA}.`; ol.appendChild(li); return; }
    const meta = [fmt(d.distance_m, 0, " m"), isNum(d.duration_min) ? "about " + hm(d.duration_min) : null,
      isNum(d.climb_m) && d.climb_m > 0 ? `up ${fmt(d.climb_m, 1, " m")}` : null,
      isNum(d.descent_m) && d.descent_m > 0 ? `down ${fmt(d.descent_m, 1, " m")}` : null,
      `steepest ${fmt(d.max_grade_deg, 1, " deg")}`].filter(Boolean);
    const warnTitles = (d.warning_ids || []).map((id) => (r.warnings || []).find((w) => w.id === id)).filter(Boolean);
    li.tabIndex = 0;
    li.innerHTML = `<div class="dtext">${esc(d.instruction)}</div>
      <div class="dmeta">${esc(meta.join(" · "))}${d.geologic_unit ? ` · ${esc(d.geologic_unit)}` : ""}</div>
      ${d.arrive_stop ? `<div class="dstop">Arrive: ${esc(d.arrive_stop)}</div>` : ""}
      ${warnTitles.length ? `<div class="dwarn">${warnTitles.map((w) => `<span class="sev-${esc(w.severity)}">${esc(SEVERITY[w.severity] || w.severity)}: ${esc(w.title)}</span>`).join(" ")}</div>` : ""}`;
    const go = () => {
      const wasActive = li.classList.contains("active");
      clearStepHighlight(); if (wasActive) return;  // second click turns the highlight off
      li.classList.add("active");
      S.stepLayer = L.layerGroup([
        L.polyline(path, { pane: "route", color: "#111", weight: 10, opacity: 0.55 }),
        L.polyline(path, { pane: "route", color: "#ffd43b", weight: 6 }),
        L.circleMarker(path[0], { pane: "route", radius: 7, color: "#111", weight: 2, fillColor: "#ffd43b", fillOpacity: 1 })
          .bindTooltip(`Step ${esc(d.step)}`, { permanent: true, direction: "top", offset: [0, -6], className: "step-tip" }),
      ]).addTo(map);
      map.fitBounds(L.latLngBounds(path), { padding: [60, 60], maxZoom: 16 });
    };
    li.onclick = go; li.onkeydown = (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); go(); } };
    ol.appendChild(li);
  });
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
    <div class="hint">Elevation profile ${qTip(TIP.profile, "About the elevation profile")} (orange = grade above caution). Hover to locate on the map.</div>`;
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

// ---------------------------------------------------------------- search (GET /search)
const KIND_LABEL = { place_name: "Official place name (IAU)", science_site: "Science site", geologic_unit: "Geologic unit",
  rover_sol: "Perseverance position", coordinates: "Coordinates" };
const searchLayer = L.layerGroup().addTo(map);
const SR = { results: [], active: -1, timer: null, n: 0 };
function closeSearch() { $("searchList").classList.add("hidden"); $("searchQ").setAttribute("aria-expanded", "false"); SR.active = -1; }
function renderSearch(msg) {
  const ul = $("searchList");
  ul.innerHTML = msg ? `<li class="none">${esc(msg)}</li>` : SR.results.map((r, i) => `<li role="option" id="sr${i}" data-i="${i}" aria-selected="${i === SR.active}" class="${i === SR.active ? "active" : ""}">
      <b>${esc(r.name)}</b><span class="kind">${esc(KIND_LABEL[r.kind] || r.kind)}${r.inside_region === false ? " - outside the study box" : ""}</span></li>`).join("");
  ul.classList.remove("hidden"); $("searchQ").setAttribute("aria-expanded", "true");
  $("searchQ").setAttribute("aria-activedescendant", SR.active >= 0 ? `sr${SR.active}` : "");
  ul.querySelectorAll("li[data-i]").forEach((li) => { li.onmousedown = (e) => { e.preventDefault(); chooseResult(SR.results[+li.dataset.i]); }; });
}
async function runSearch(pickFirst = false) {
  const q = $("searchQ").value.trim(), n = ++SR.n;
  if (!q || !S.region) { SR.results = []; closeSearch(); return; }
  try {
    const d = await api(`/search?region_id=${encodeURIComponent(S.region)}&q=${encodeURIComponent(q)}`);
    if (n !== SR.n) return;  // a newer query is running
    SR.results = d.results || []; SR.active = SR.results.length ? 0 : -1;
    if (pickFirst && SR.results.length) { chooseResult(SR.results[0]); return; }
    renderSearch(SR.results.length ? null : `No match for "${q}". Try a site name, "sol 509" or "lon, lat".`);
  } catch (e) { if (n === SR.n) renderSearch(e.message); }
}
function chooseResult(r) {
  closeSearch(); $("searchQ").value = r.name; searchLayer.clearLayers();
  if (!isNum(r.lon) || !isNum(r.lat)) { toast(`Location ${NA} for ${r.name}`); return; }
  const x = r.extra || {};
  const facts = [
    x.feature_type && `Type: ${esc(x.feature_type)}`, isNum(x.diameter_km) && `Diameter: ${fmt(x.diameter_km, 1, " km")}`,
    x.goal_id && `Science goal: ${esc(x.goal_id)}`, x.observation_date && `Observed: ${esc(x.observation_date)}`,
    isNum(x.walking_time_multiplier) && `Walking time: x${esc(x.walking_time_multiplier)}`,
    isNum(x.share_of_study_box) && `Covers ${pctTxt(x.share_of_study_box)} of the study box`,
    isNum(x.localized_sol) && `Rover localization from sol ${esc(x.localized_sol)}`,
    x.note && `<span class="hint">${esc(x.note)}</span>`, x.order && `<span class="hint">Read as ${esc(x.order)}</span>`,
    (x.source_url || x.source) && link(x.source_url, x.source || "source"),
  ].filter(Boolean);
  const outside = r.inside_region === false;
  const m = L.marker([r.lat, r.lon], { pane: "route", icon: L.divIcon({ className: "search-icon", html: "&#9679;", iconSize: [20, 20] }) }).addTo(searchLayer);
  m.bindPopup(htmlEl(`<b>${esc(r.name)}</b><br><span class="hint">${esc(KIND_LABEL[r.kind] || r.kind)}</span><br>
    lon ${fmt(r.lon, 5)} E, lat ${fmt(r.lat, 5)}<br>${facts.join("<br>")}
    ${outside ? '<p class="msg err">Outside the study box: terrain values and routes are not available here.</p>'
      : `<div class="row"><button type="button" class="sr-here">What's here?</button></div>`}`), { maxWidth: 300 });
  m.on("popupopen", (e) => { const b = e.popup.getElement().querySelector(".sr-here"); if (b) b.onclick = () => showPointInfo(L.latLng(r.lat, r.lon)); });
  map.flyTo([r.lat, r.lon], outside ? Math.min(map.getZoom(), 8) : Math.max(map.getZoom(), 14), { duration: 0.8 });
  let opened = false; const open = () => { if (!opened && searchLayer.hasLayer(m)) { opened = true; m.openPopup(); } };
  map.once("moveend", open); setTimeout(open, 1300);  // fallback when the map does not need to move
  if (outside) toast("That location is outside this region's study box.", 5000);
}
$("searchQ").oninput = () => { clearTimeout(SR.timer); SR.timer = setTimeout(() => runSearch(false), 250); };
$("searchQ").onkeydown = (e) => {
  const open = !$("searchList").classList.contains("hidden") && SR.results.length;
  if (e.key === "ArrowDown" && open) { e.preventDefault(); SR.active = (SR.active + 1) % SR.results.length; renderSearch(); }
  else if (e.key === "ArrowUp" && open) { e.preventDefault(); SR.active = (SR.active - 1 + SR.results.length) % SR.results.length; renderSearch(); }
  else if (e.key === "Enter") { e.preventDefault(); clearTimeout(SR.timer); if (open && SR.active >= 0) chooseResult(SR.results[SR.active]); else runSearch(true); }
  else if (e.key === "Escape") closeSearch();
};
$("searchQ").onblur = () => setTimeout(closeSearch, 150);
$("searchQ").onfocus = () => { if ($("searchQ").value.trim() && SR.results.length) renderSearch(); };

// ---------------------------------------------------------------- walking range (POST /reachability)
const pctTxt = (f) => (isNum(f) ? fmt(f * 100, 0, "%") : NA);
const BAND_COLORS = { 1: "#2f9e44", 2: "#94d82d", 3: "#fab005", 4: "#e8590c" };
function clearRange() {
  if (S.rangeLayer) { map.removeLayer(S.rangeLayer); S.rangeLayer = null; }
  if (S.rangeLegend) { map.removeControl(S.rangeLegend); S.rangeLegend = null; }
  $("rangeBox").classList.add("hidden"); $("rangeOut").innerHTML = "";
}
$("rangeClear").onclick = clearRange;
$("rangeBtn").onclick = () => {
  if (!S.points.start) { $("routeMsg").className = "msg err"; $("routeMsg").textContent = "Set a start point first (or use \"Walking range from here\" in a map pop-up)."; return; }
  showRange(S.points.start.lon, S.points.start.lat, $("rangeBtn"));
};
window.piRange = (lon, lat) => { map.closePopup(); showRange(lon, lat, $("rangeBtn")); };

async function showRange(lon, lat, btn) {
  await busy(btn, async () => {
    $("routeMsg").textContent = "Calculating the walking range (this can take several seconds)...";
    const d = await api("/reachability", { method: "POST", body: JSON.stringify({ region_id: S.region, start: { lon, lat }, eva: evaOverrides(), include_science_sites: true }) });
    clearRange(); drawRange(d);
  });
}

function drawRange(d) {
  const roundTrip = d.eva_params ? d.eva_params.round_trip : null;
  const tripWord = roundTrip === false ? "one way" : "round trip";
  const feats = ((d.bands || {}).features || []).slice().sort((a, b) => b.properties.band - a.properties.band);  // largest first
  const g = L.layerGroup();
  feats.forEach((f) => {
    const p = f.properties, col = BAND_COLORS[p.band] || "#888";
    L.geoJSON(f, { pane: "overlays", style: { color: col, weight: 1.5, fillColor: col, fillOpacity: 0.22, opacity: 0.9 } })
      .bindTooltip(`Within ${fmt(p.round_trip_min_max, 0, " min")} ${tripWord} (${pctTxt(p.fraction_of_usable_time)} of usable time) - ${fmt(p.area_km2, 2, " km²")}`, { sticky: true })
      .addTo(g);
  });
  const st = (d.start || {}).snapped || (d.start || {}).requested;
  if (st) L.marker([st[1], st[0]], { pane: "route", icon: L.divIcon({ className: "hab-icon", html: "H", iconSize: [24, 24] }) })
    .bindTooltip("Walking range start (habitat)").addTo(g);
  const far = d.farthest_point;
  if (far && st) {
    L.polyline([[st[1], st[0]], [far.lat, far.lon]], { pane: "route", color: "#222", weight: 2, dashArray: "4 4" }).addTo(g);
    L.circleMarker([far.lat, far.lon], { pane: "route", radius: 5, color: "#222", fillColor: "#fff", fillOpacity: 1 })
      .bindTooltip(`Farthest reach: ${fmt(far.straight_line_km, 2, " km")} straight-line, ${hm(far.round_trip_min)} ${tripWord}`).addTo(g);
  }
  S.rangeLayer = g.addTo(map);
  if (feats.length) map.fitBounds(L.geoJSON(feats[0]).getBounds(), { padding: [30, 30] });

  const legendRows = feats.slice().reverse().map((f) => `<div><span class="cat" style="background:${BAND_COLORS[f.properties.band]}"></span>within ${fmt(f.properties.round_trip_min_max, 0, " min")} (${pctTxt(f.properties.fraction_of_usable_time)})</div>`).join("");
  S.rangeLegend = L.control({ position: "bottomright" });
  S.rangeLegend.onAdd = () => htmlEl(`<div class="range-legend"><b>Walking range, ${esc(tripWord)}</b>${legendRows || `<div>${NA}</div>`}<div class="hint">of ${fmt(d.usable_min, 0, " min")} usable EVA time - model estimate</div></div>`);
  S.rangeLegend.addTo(map);

  const sites = d.science_sites || [];
  const time = (s) => hm(roundTrip === false ? s.outbound_min : s.round_trip_min);
  const rows = sites.map((s, i) => `<tr class="${s.in_range ? "in" : "out"}" data-i="${i}" tabindex="0">
      <td><b>${esc(s.name || NA)}</b>${s.goal_id ? `<br><span class="hint">goal ${esc(s.goal_id)}</span>` : ""}</td>
      <td>${s.in_range ? '<span class="ok">in range</span>' : '<span class="bad">out of range</span>'}</td>
      <td>${time(s)}<br><span class="hint">out ${hm(s.outbound_min)}</span></td><td>${fmt(s.straight_line_km, 2, " km")}</td>
      <td>${s.in_range && isNum(s.lon) ? `<button type="button" class="mini" data-stop="${i}">Add stop</button>` : ""}</td></tr>`).join("");
  const inCount = sites.filter((s) => s.in_range).length;
  $("rangeOut").innerHTML = `${d.is_test_fixture ? '<p class="fixture-note">TEST FIXTURE - synthetic terrain.</p>' : ""}
    <p class="summary"><b>${fmt(d.reachable_area_km2, 2, " km²")}</b> reachable, ${esc(d.mode || tripWord)}, within ${fmt(d.usable_min, 0, " min")} usable EVA time.
      ${far ? `Farthest point ${fmt(far.straight_line_km, 2, " km")} away in a straight line.` : ""}
      ${isNum((d.start || {}).snapped_m) && d.start.snapped_m > 0 ? `<br><span class="hint">Start moved ${fmt(d.start.snapped_m, 0, " m")} to walkable ground.</span>` : ""}
      <span class="hint">Model estimate with your EVA settings; not a safe zone, and ground outside it is not necessarily unsafe.</span></p>
    <h4>Science sites (${inCount} of ${sites.length} in range)</h4>
    ${sites.length ? `<table class="range-sites"><tr><th>site</th><th>range</th><th>${esc(tripWord)}</th><th>straight</th><th></th></tr>${rows}</table><p class="hint">Click a row to show the site on the map.</p>` : `<p class="hint">No curated science sites in this region.</p>`}
    <details class="sub"><summary>Assumptions and limitations</summary><ul>${(d.assumptions || []).concat(d.limitations || []).map((a) => `<li>${esc(a)}</li>`).join("")}</ul>
      <p class="hint">${esc(d.engine || "")}, ${fmt(d.grid_resolution_m, 0, " m")} grid.</p></details>`;
  $("rangeOut").querySelectorAll("tr[data-i]").forEach((tr) => {
    const s = sites[+tr.dataset.i];
    const go = () => { if (isNum(s.lon) && isNum(s.lat)) map.setView([s.lat, s.lon], Math.max(map.getZoom(), 14)); };
    tr.onclick = (e) => { if (!e.target.closest("button")) go(); };
    tr.onkeydown = (e) => { if (e.key === "Enter") go(); };
  });
  $("rangeOut").querySelectorAll("button[data-stop]").forEach((b) => { const s = sites[+b.dataset.stop]; b.onclick = () => addStop(s.lon, s.lat, s.name || "Science site"); });
  $("rangeBox").classList.remove("hidden"); $("rangeBox").open = true;
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
    if (refresh && S.status && S.status.online === false) toast("Refresh needs internet: showing the cached space-weather data.", 5000);
    else if (refresh && s.refresh_error) toast(`Refresh failed: ${s.refresh_error}. Showing cached data.`, 6000);
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
    S.status = s; S.statusError = null;
    const b = $("netBadge");
    const date = S.regionInfo && S.regionInfo.data_date;
    if (s.online) { b.textContent = "Online"; b.className = "badge"; }
    else { b.textContent = `Offline - using packaged data${date ? " from " + date : ""}`; b.className = "badge off"; }
  } catch (e) { S.status = null; S.statusError = e.message; $("netBadge").textContent = "Backend not reachable"; $("netBadge").className = "badge warn"; }
  renderDashboard();
}

// ---------------------------------------------------------------- boot
// ---------------------------------------------------------------- mission dashboard (values from /regions, /layers, /status)
function renderDashboard() {
  const g = S.regionInfo, st = S.status, src = S.sources || {};
  const tile = (k, v, cls = "") => `<div class="tile ${cls}"><span>${esc(k)}</span><b>${v}</b></div>`;
  const conn = st ? (st.online ? '<span class="dot ok"></span>Online' : `<span class="dot off"></span>Offline${st.force_offline ? " (rehearsal mode)" : ""}`)
    : S.statusError ? '<span class="dot bad"></span>Backend not reachable' : "checking...";
  const elev = ["dem_primary", "dem_fallback"].map((k) => src[k]).filter((x) => x && x.found).map((x) => esc(x.label));
  const tiles = !g ? '<p class="hint">No region loaded.</p>' : [
    tile("Region", esc(g.name)),
    tile("Data", g.is_test_fixture ? "TEST FIXTURE: synthetic terrain" : "Real NASA/USGS data", g.is_test_fixture ? "fixture" : "real"),
    tile("Data date", esc(g.data_date || NA) + (g.processed_at ? `<small>processed ${esc(String(g.processed_at).slice(0, 10))}</small>` : "")),
    tile("Connection", conn),
    tile("Terrain grid", isNum(g.resolution_m) ? fmt(g.resolution_m, 1, " m") : NA),
    tile("Route engine", st ? esc(st.routing_engine || NA) : NA),
    tile("Elevation data", elev.length ? elev.join("<br>") : NA, "wide"),
    tile("Assistant", st ? (st.assistant_index ? `documents indexed${st.llm_configured ? ", written answers on" : ", quote mode"}` : "no document index") : NA, "wide"),
  ].join("");
  $("dashTiles").innerHTML = tiles;
  const goals = (g && g.science_goals) || [];
  $("dashGoals").innerHTML = goals.length ? `<h3>Science goals</h3><ul class="dash-goals">${goals.map((x) => `<li><b>${esc(x.id)}</b> ${esc(x.title)}${x.status ? ` <span class="hint">(${esc(x.status)})</span>` : ""}</li>`).join("")}</ul>` : "";
}
$("dPlan").onclick = () => { $("setupBox").open = true; $("setupBox").scrollIntoView({ behavior: "smooth", block: "start" }); setMode("start"); toast("Click the map to place the start point."); };
$("dRange").onclick = () => { $("setupBox").open = true; if (S.points.start) $("rangeBtn").click(); else { setMode("start"); toast("Click the map to place the start (habitat), then press Walking range again."); } };
$("dAsk").onclick = () => { $("askBox").open = true; $("askBox").scrollIntoView({ behavior: "smooth", block: "start" }); $("askQ").focus({ preventScroll: true }); };
$("dGlobe").onclick = () => showGlobe();

// ---------------------------------------------------------------- 3D globe bridge (globe.js is an ES module)
// The globe leads to the mission dashboard. Add ?classic=1 to index.html to open the earlier map page instead.
const CLASSIC = new URLSearchParams(location.search).has("classic");
function goDashboard(regionId) { location.href = "dashboard.html" + (regionId ? "?region_id=" + encodeURIComponent(regionId) : ""); }
function hideGlobe() {
  if ($("globeScreen").classList.contains("hidden")) return;
  $("globeScreen").classList.add("hidden"); window.dispatchEvent(new Event("globe:hidden"));
  map.invalidateSize(); $("searchQ").focus({ preventScroll: true });
}
function showGlobe() {
  if (window.globeFailed || !window.globeReady) { toast("The 3D globe is not available in this browser; staying on the map."); return; }
  $("globeScreen").classList.remove("hidden"); window.dispatchEvent(new Event("globe:shown")); $("skipGlobe").focus();
}
window.MarsPath = {
  api, toast, showGlobe, hideGlobe: () => (CLASSIC ? hideGlobe() : goDashboard(S.region)),
  openRegion: async (id) => {
    try {
      await S.ready;
      const info = (S.regions || []).find((g) => g.region_id === id);
      if (info && S.region !== id) { $("region").value = id; await selectRegion(id, info); }
    } catch (e) { toast(e.message); }
    if (!CLASSIC) { goDashboard(id); return; }
    hideGlobe();
    const b = S.regionInfo && S.regionInfo.bbox; if (b) map.fitBounds([[b.south, b.west], [b.north, b.east]]);
  },
};
$("skipGlobe").onclick = () => (CLASSIC ? hideGlobe() : goDashboard(S.region));
$("globeBtn").onclick = showGlobe;
$("skipGlobe").focus();
// If the globe module cannot load or start (old browser, no WebGL, missing file), fall back to the map.
setTimeout(() => { if (!window.globeReady && !$("globeScreen").classList.contains("hidden")) { window.globeFailed = true; if (CLASSIC) { hideGlobe(); toast("3D globe not available; showing the map.", 5000); } else goDashboard(S.region); } }, 12000);

if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
S.ready = (async () => {
  try { await loadDefaults(); await loadRegions(); } catch (e) { $("routeMsg").className = "msg err"; $("routeMsg").textContent = "Startup failed: " + e.message; }
  pollStatus(); setInterval(pollStatus, 30000);
})();
