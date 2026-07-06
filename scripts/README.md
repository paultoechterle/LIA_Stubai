# Datenaufbereitung (Phase A)

Pipeline, die aus den beiden 5-m-DEMs die für MapLibre benötigten
Terrain-RGB- und Overlay-Kacheln erzeugt. **Die Skripte werden von dir in
deiner conda-Umgebung ausgeführt** (der KI-Agent hat hier nur
eingeschränkte Rechte). Alle Pfade/Parameter stehen zentral in
`config.py`.

## Reihenfolge

| Schritt | Skript | Zweck | Ausgabe |
|---|---|---|---|
| 0 | `00_build_lia_composite.py` | Reinthaler-LIA-Fläche auf `project_area` zuschneiden, per Cubic-Spline aufs 5-m-Raster interpolieren, als Eiskörper aufs moderne Terrain legen | `data/DEM_5m_LIA_cubic.tif` |
| 1 | `01_inspect_dems.py` | Metadaten + Deckungsgleichheit prüfen | nur Konsolenausgabe |
| 2 | `02_prepare_rasters.py` | → EPSG:3857, NoData füllen, außerhalb `project_area` auf Ebene setzen | `app/build/dem_*_3857.tif` |
| 3 | `03_make_terrainrgb.py` | Höhe → Terrain-RGB (rio-rgbify) | `app/build/terrainrgb_*.tif` |
| 3b | `03b_make_hillshade.py` | Multidirektionaler Hillshade aus DEM (8-bit) | `app/build/hs_*_3857.tif` |
| 4 | `04_make_tiles.py` | XYZ-Kacheln (gdal2tiles) | `app/tiles/<name>/{z}/{x}/{y}.png` |
| 5 | `05_web_meta.py` | Kartenmitte/Bounds für die App | `app/meta.json` |
| 7 | `07_make_pois.py` | Gipfel/Gletscher-POIs fürs Web aufbereiten | `app/pois.geojson` |

Alles in einem Rutsch (bricht bei Fehler ab):

```bash
python scripts/run_all.py
# einzelne Schritte überspringen, z. B. das teure Composite:
python scripts/run_all.py --skip 00 --skip 04
```

Oder einzeln aus dem Projekt-Root, z. B.:

```bash
python scripts/00_build_lia_composite.py
python scripts/01_inspect_dems.py
python scripts/02_prepare_rasters.py
python scripts/03_make_terrainrgb.py
python scripts/03b_make_hillshade.py
python scripts/04_make_tiles.py
python scripts/05_web_meta.py
python scripts/07_make_pois.py
```

Nach jedem Schritt kurz das Ergebnis kontrollieren (Schritt 1 liefert die
Sanity-Checks, die übrigen schreiben Dateien).

## Wichtige fachliche Punkte

- **Reihenfolge Reprojektion vor Encoding:** Das DEM wird als *Float*
  bilinear nach 3857 umprojiziert (Schritt 2), erst danach in RGB kodiert
  (Schritt 3). Würde man das kodierte RGB reprojizieren/interpolieren,
  entstünden falsche Höhen.
- **Terrain-RGB-Kacheln nur mit `near`** resampeln (in `config.py` gesetzt).
  Overlays (Hillshade/Orthofoto) dürfen `average` nutzen.
- **MapLibre-Encoding:** Die Terrain-Source muss `encoding: 'mapbox'`
  verwenden (passend zu rio-rgbify Standard, base −10000 / interval 0.1).
- **Hillshade aus dem DEM:** Der Hillshade wird in Schritt 3b direkt aus
  dem reprojizierten DEM erzeugt (`gdal.DEMProcessing`, multidirektional,
  8-bit 0–255). Das garantiert Pixelgenauigkeit zum Terrain und ein von
  gdal2tiles akzeptiertes 8-bit-Format (Float-Hillshades scheitern dort).
  Parameter (Höhenwinkel, z-Faktor) stehen in `config.py`.

## Zuschnitt aufs Projektgebiet

Der Bezug ist überall `data/project_area.shp`:

- **Schritt 0** schneidet schon das grobe, alpenweite Reinthaler-Original
  auf das Projektgebiet (+ `LIA_CLIP_BUFFER`) zu, damit nur die
  relevanten Gletscher verarbeitet werden.
- **Schritt 2** grenzt den verarbeiteten Ausschnitt per Fenster auf die
  Polygon-Bounds (+ `AOI_BUFFER`) ein (viel weniger Kacheln: ohne
  Zuschnitt würde das gesamte, überwiegend leere DEM-Rechteck von
  ~51 × 55 km gekachelt, ≈ 90.000 Dateien / 1,2 GB). Anschließend werden
  bei **beiden** DEMs alle Werte **außerhalb der Polygonform** auf eine
  einheitliche **Ebenen-Höhe** gesetzt (Minimum im Projektgebiet bzw.
  `AOI_PLANE_HEIGHT`).

**Warum eine Ebene statt NoData?** MapLibre-Terrain (`raster-dem`) hat
kein Alpha; ein hartes NoData außerhalb würde als Wand/Grube ums Tal
gerendert. Eine flache, niedrige Ebene liefert stattdessen einen
sauberen Sockel, auf dem das Tal sitzt. Beide Epochen nutzen dieselbe
Ebenen-Höhe, damit der Vorher/Nachher-Toggle die Ebene nicht verschiebt.
Der Hillshade dieser Ebene ist gleichmäßig getönt (kein Relief) – deshalb
braucht Schritt 3b keine zusätzliche Maskierung.

Passt der Ausschnitt/die Ebene nicht, `AOI_PATH`/`AOI_BUFFER`/
`AOI_PLANE_HEIGHT` in `config.py` ändern und ab Schritt 0 (bei Gletscher-
Änderungen) bzw. Schritt 2 neu laufen lassen.

## Web-App (Phase B)

Nach dem Kacheln einmalig die Karten-Metadaten erzeugen (Mitte/Bounds
aus dem DEM, damit nichts im HTML hartcodiert ist):

```bash
python scripts/05_web_meta.py       # schreibt app/meta.json
```

Dann die App lokal testen – statischer Server aus dem `app/`-Ordner:

```bash
cd app
python -m http.server 8000
```

Im Browser `http://localhost:8000/` öffnen. Es erscheint das 3D-Relief
mit Vorher/Nachher-Toggle (heute/1850) und PNG-Export. (Die
Zeichenfunktion ist im HTML aktuell auskommentiert.)

## Deployment auf GitHub Pages (Phase E)

Die App ist statisch und wird über GitHub Actions veröffentlicht
(`.github/workflows/pages.yml` deployt den `app/`-Ordner).

1. **Tiles müssen ins Repo.** Sie sind in `.gitignore` ausgeschlossen –
   sobald sie nach dem Zuschnitt klein genug sind (Größe prüfen!), die
   Zeile `app/tiles/` in `.gitignore` entfernen und committen.
2. Repo zu GitHub pushen.
3. Auf GitHub unter **Settings → Pages → Build and deployment → Source**
   „GitHub Actions" wählen.
4. Der Workflow läuft bei jedem Push auf `main`/`master`; die Seiten-URL
   steht danach in der Actions-Ausgabe.

Läuft die App unter einer Projekt-URL wie
`https://<user>.github.io/<repo>/`, funktionieren die relativen
Tile-Pfade (`TILE_BASE = "tiles"` in `index.html`) unverändert, weil die
Tiles im selben `app/`-Ordner liegen.
