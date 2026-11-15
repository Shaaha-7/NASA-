# Third-party files in frontend/vendor/

Everything here is served locally so the app works offline. Each file's origin and any change made to it is listed below.

## mars_globe_4k.jpg (3D globe texture)

- **Product:** Mars Viking Colorized Global Mosaic 232m (MDIM 2.1, colorized). Originator: NASA Ames; publisher: USGS Astrogeology Science Center; publication date 2009-02-02.
- **Product page:** https://astrogeology.usgs.gov/search/map/mars_viking_colorized_global_mosaic_232m
- **Usage terms (from the product page, checked 2026-11-15):** Access Constraints: "Public domain"; Use Constraints: "None".
- **File downloaded:** the product's 1 km/pixel JPG, `mars_viking_mdim21_clrmosaic_1km.jpg` (21339 x 10670 px, 36,708,552 bytes, SHA-256 `fdfcd335559c3dc67052b7e8a9565d850e336ac0d1f3ea7f5eb7826ffb44ecb2`), from
  https://astrogeology.usgs.gov/ckan/dataset/7131d503-cdc9-45a5-8f83-5126c0fd397e/resource/5ea881c6-01b3-41fa-a7af-42d2131b54f1/download/mars_viking_mdim21_clrmosaic_1km.jpg
  The original is kept outside Git in `C:\NASA_DATA\globe\`.
- **Projection (from the product's .aux.xml):** Equirectangular, Mars sphere R = 3,396,190 m, centre meridian 0, extent -180..180 longitude and -90..90 latitude. USGS lists the product as planetocentric latitude, east-positive longitude. This maps directly onto a sphere.
- **Change made:** resized to 4096 x 2048 px (Pillow, JPEG draft decode then Lanczos), saved as JPEG quality 85. No colour or geometry edits. Result: about 1.85 MB, SHA-256 `25e2aca54341b052f99e06d09a94e7b1bc8018c60c28357b5caeb96c1c712feb`.
- **Caveat shown in the app:** USGS calls this an "artistically colorized" mosaic: the colours are not true colour. At about 10 km per pixel it is for orientation only, not for any terrain decision.

## three.module.min.js (Three.js r170)

- **Package:** `three@0.170.0` from the npm registry, https://registry.npmjs.org/three/-/three-0.170.0.tgz (tarball SHA-1 `6087f97aab79e9e9312f9c89fcef6808642dfbb7`, matching the registry's `dist.shasum`).
- **File:** `build/three.module.min.js`, unchanged (SHA-256 `08fd7545d13d2c7fb65ab691530a802dafefd638596501854f267d0fb13c39e7`).
- **Licence:** MIT, copied to `three.LICENSE.txt`.

## leaflet.js, leaflet.css, images/

Leaflet (BSD-2-Clause), already in the repository before the frontend-ui branch.
