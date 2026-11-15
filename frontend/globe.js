/* MarsPath opening screen: a rotatable, zoomable 3D Mars globe (Three.js, vendored locally).
   Texture: USGS Astrogeology / NASA Ames Viking MDIM 2.1 colorized global mosaic (public domain),
   equirectangular, planetocentric latitude, east-positive longitude (see vendor/SOURCES.md).
   Region markers sit at each region's centre from GET /api/v1/regions. Falls back to the 2D map if
   WebGL or the texture is not available. */
import * as THREE from "./vendor/three.module.min.js";

const MP = window.MarsPath;
const screen = document.getElementById("globeScreen");
const holder = document.getElementById("globeCanvas");
const labels = document.getElementById("globeLabels");
const list = document.getElementById("globeRegions");
const status = document.getElementById("globeStatus");
const reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function fail(why) {
  window.globeReady = false; window.globeFailed = true;
  MP.hideGlobe();
  MP.toast(`3D globe not available (${why}). Showing the map.`, 5000);
}

function webglOK() {
  try { const c = document.createElement("canvas"); return !!(window.WebGLRenderingContext && (c.getContext("webgl2") || c.getContext("webgl"))); }
  catch (_) { return false; }
}

// lon/lat (deg, east-positive, planetocentric) -> point on the unit sphere, matching SphereGeometry's UV layout
// (u = 0 at lon -180 on the -X axis, lon 0 on +X, lon +90 on -Z).
function lonLatToVec(lon, lat, r = 1) {
  const L = THREE.MathUtils.degToRad(lon), B = THREE.MathUtils.degToRad(lat);
  return new THREE.Vector3(r * Math.cos(B) * Math.cos(L), r * Math.sin(B), -r * Math.cos(B) * Math.sin(L));
}
// globe rotation that puts lon/lat facing the camera (camera on +Z)
const facing = (lon, lat) => ({ yaw: -(Math.PI / 2 + THREE.MathUtils.degToRad(lon)), pitch: THREE.MathUtils.degToRad(lat) });

async function start() {
  if (!webglOK()) { fail("WebGL is off or unsupported"); return; }
  let renderer;
  try { renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true }); }
  catch (e) { fail("WebGL could not start"); return; }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  holder.appendChild(renderer.domElement);
  renderer.domElement.setAttribute("aria-hidden", "true");

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(35, 1, 0.01, 100);
  let dist = 3.6; const DMIN = 1.35, DMAX = 6;
  scene.add(new THREE.AmbientLight(0xffffff, 0.55));
  const sun = new THREE.DirectionalLight(0xffffff, 2.2); sun.position.set(-3, 2, 4); scene.add(sun);

  const globe = new THREE.Group(); scene.add(globe);

  // texture (fails -> fall back to the map)
  let tex;
  try {
    tex = await new THREE.TextureLoader().loadAsync("vendor/mars_globe_4k.jpg");
  } catch (e) { renderer.dispose(); holder.innerHTML = ""; fail("the Mars image did not load"); return; }
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
  globe.add(new THREE.Mesh(new THREE.SphereGeometry(1, 128, 64), new THREE.MeshLambertMaterial({ map: tex })));
  // thin atmosphere rim (decorative)
  globe.add(new THREE.Mesh(new THREE.SphereGeometry(1.02, 64, 32),
    new THREE.MeshBasicMaterial({ color: 0xff9966, transparent: true, opacity: 0.07, side: THREE.BackSide })));

  // regions
  let regions = [], regionsError = "";
  try { regions = (await MP.api("/regions")).regions || []; }
  catch (e) { regionsError = `Region list not available (${e.message}). Is the MarsPath backend running? Start run.bat.`; }
  const markers = regions.filter((g) => Array.isArray(g.center) && g.center.length >= 2).map((g) => {
    const [lon, lat] = g.center;
    const dot = new THREE.Mesh(new THREE.SphereGeometry(0.014, 16, 12), new THREE.MeshBasicMaterial({ color: g.is_test_fixture ? 0xff4d6d : 0xffd43b }));
    dot.position.copy(lonLatToVec(lon, lat, 1.003)); globe.add(dot);
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.022, 0.03, 32), new THREE.MeshBasicMaterial({ color: g.is_test_fixture ? 0xff4d6d : 0xffd43b, side: THREE.DoubleSide, transparent: true, opacity: 0.9 }));
    ring.position.copy(lonLatToVec(lon, lat, 1.004)); ring.lookAt(lonLatToVec(lon, lat, 2)); globe.add(ring);
    const btn = document.createElement("button");
    btn.type = "button"; btn.className = "globe-label" + (g.is_test_fixture ? " fixture" : "");
    btn.innerHTML = `${esc(g.name)}${g.is_test_fixture ? " <small>TEST FIXTURE</small>" : ""}`;
    btn.setAttribute("aria-label", `Open ${g.name} on the map${g.is_test_fixture ? " (test fixture, synthetic terrain)" : ""}`);
    btn.onclick = () => openRegion(g);
    labels.appendChild(btn);
    return { g, lon, lat, dot, ring, btn };
  });
  list.innerHTML = regions.length ? "" : `<p class="hint">${regionsError ? "No regions to show." : "No processed region yet. Run prepare_data.py (see README)."}</p>`;
  regions.forEach((g) => {
    const b = document.createElement("button"); b.type = "button"; b.className = "globe-card";
    const c = Array.isArray(g.center) ? `${Number(g.center[0]).toFixed(2)} E, ${Number(g.center[1]).toFixed(2)} N` : "centre not available";
    b.innerHTML = `<b>${esc(g.name)}</b>${g.is_test_fixture ? ' <span class="fx">TEST FIXTURE</span>' : ""}
      <span>${esc(c)} &middot; ${g.resolution_m != null ? esc(g.resolution_m) + " m grid" : "grid not available"} &middot; data ${esc(g.data_date || "date not available")}</span>`;
    b.onclick = () => openRegion(g);
    const m = markers.find((x) => x.g === g);
    if (m) { b.onmouseenter = b.onfocus = () => aimAt(m.lon, m.lat); }
    list.appendChild(b);
  });

  // view state + interaction
  const first = markers[0];
  let { yaw, pitch } = first ? facing(first.lon, first.lat) : { yaw: 0, pitch: 0 };
  let vYaw = 0, vPitch = 0, auto = !reduceMotion, anim = null, running = true;
  const clampPitch = (p) => Math.max(-1.45, Math.min(1.45, p));
  function aimAt(lon, lat, d) {
    const t = facing(lon, lat);
    let dy = ((t.yaw - yaw) % (2 * Math.PI) + 3 * Math.PI) % (2 * Math.PI) - Math.PI;  // shortest way round
    anim = { y0: yaw, p0: pitch, d0: dist, y1: yaw + dy, p1: t.pitch, d1: d ?? dist, t0: performance.now(), ms: reduceMotion ? 1 : 900 };
    auto = false; vYaw = vPitch = 0;
  }
  const el = renderer.domElement, ptrs = new Map();
  let last = null, pinch0 = null;
  el.addEventListener("pointerdown", (e) => { el.setPointerCapture(e.pointerId); ptrs.set(e.pointerId, [e.clientX, e.clientY]); last = [e.clientX, e.clientY]; auto = false; anim = null; vYaw = vPitch = 0; });
  el.addEventListener("pointermove", (e) => {
    if (!ptrs.has(e.pointerId)) return;
    ptrs.set(e.pointerId, [e.clientX, e.clientY]);
    if (ptrs.size === 2) {
      const [a, b] = [...ptrs.values()]; const d = Math.hypot(a[0] - b[0], a[1] - b[1]);
      if (pinch0) dist = Math.max(DMIN, Math.min(DMAX, dist * pinch0 / d)); pinch0 = d; return;
    }
    const k = 2.2 * (dist - 0.9) / el.clientHeight;
    vYaw = (e.clientX - last[0]) * k; vPitch = (e.clientY - last[1]) * k;
    yaw += vYaw; pitch = clampPitch(pitch + vPitch); last = [e.clientX, e.clientY];
  });
  const up = (e) => { ptrs.delete(e.pointerId); pinch0 = null; if (ptrs.size === 1) last = [...ptrs.values()][0]; };
  el.addEventListener("pointerup", up); el.addEventListener("pointercancel", up);
  el.addEventListener("wheel", (e) => { e.preventDefault(); auto = false; anim = null; dist = Math.max(DMIN, Math.min(DMAX, dist * Math.exp(e.deltaY * 0.0012))); }, { passive: false });
  screen.addEventListener("keydown", (e) => {
    if (e.target.closest && e.target.closest("button, a, input")) { if (e.key === "Escape") MP.hideGlobe(); return; }
    const step = 0.12;
    if (e.key === "ArrowLeft") yaw -= step; else if (e.key === "ArrowRight") yaw += step;
    else if (e.key === "ArrowUp") pitch = clampPitch(pitch - step); else if (e.key === "ArrowDown") pitch = clampPitch(pitch + step);
    else if (e.key === "+" || e.key === "=") dist = Math.max(DMIN, dist * 0.85); else if (e.key === "-") dist = Math.min(DMAX, dist / 0.85);
    else if (e.key === "Escape") MP.hideGlobe(); else return;
    auto = false; anim = null; e.preventDefault();
  });

  function openRegion(g) {
    const m = markers.find((x) => x.g === g);
    if (m) aimAt(m.lon, m.lat, DMIN + 0.15);
    setTimeout(() => MP.openRegion(g.region_id), m && !reduceMotion ? 950 : 0);
  }

  function resize() {
    const w = holder.clientWidth || window.innerWidth, h = holder.clientHeight || window.innerHeight;
    renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
  }
  window.addEventListener("resize", resize); resize();

  const tmp = new THREE.Vector3(), camDir = new THREE.Vector3();
  function frame(now) {
    if (!running) return;
    if (anim) {
      const t = Math.min(1, (now - anim.t0) / anim.ms), s = t * t * (3 - 2 * t);
      yaw = anim.y0 + (anim.y1 - anim.y0) * s; pitch = anim.p0 + (anim.p1 - anim.p0) * s; dist = anim.d0 + (anim.d1 - anim.d0) * s;
      if (t >= 1) anim = null;
    } else if (auto) yaw += 0.0015;
    else if (!ptrs.size && (Math.abs(vYaw) > 1e-5 || Math.abs(vPitch) > 1e-5)) {  // gentle inertia
      yaw += vYaw; pitch = clampPitch(pitch + vPitch); vYaw *= 0.92; vPitch *= 0.92;
    }
    globe.rotation.set(pitch, yaw, 0);
    camera.position.set(0, 0, dist); camera.lookAt(0, 0, 0);
    renderer.render(scene, camera);
    // HTML labels follow their markers; hidden on the far side
    camDir.copy(camera.position).normalize();
    const w = el.clientWidth, h = el.clientHeight;
    markers.forEach((m) => {
      m.dot.getWorldPosition(tmp);
      const front = tmp.clone().normalize().dot(camDir) > 0.15;
      tmp.project(camera);
      m.btn.style.transform = `translate(${((tmp.x + 1) / 2 * w).toFixed(1)}px, ${((1 - tmp.y) / 2 * h).toFixed(1)}px)`;
      m.btn.classList.toggle("behind", !front); m.btn.tabIndex = front ? 0 : -1;
    });
    requestAnimationFrame(frame);
  }
  window.addEventListener("globe:hidden", () => { running = false; });
  window.addEventListener("globe:shown", () => { if (!running) { running = true; resize(); requestAnimationFrame(frame); } });
  if (screen.classList.contains("hidden")) running = false; else requestAnimationFrame(frame);  // user already skipped
  window.globeReady = true;
  status.textContent = regionsError;
  screen.classList.add("ready");
}

start().catch((e) => fail(e && e.message ? e.message : "unexpected error"));
