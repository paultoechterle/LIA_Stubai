# Datenaufbereitung (Phase A)

Pipeline, die aus den beiden 5-m-DEMs die für MapLibre benötigten
Terrain-RGB- und Overlay-Kacheln erzeugt. **Die Skripte werden von dir in
deiner conda-Umgebung ausgeführt** (der KI-Agent hat hier nur
eingeschränkte Rechte). Alle Pfade/Parameter stehen zentral in
`config.py`.

## Reihenfolge

| Schritt | Skript | Zweck | Ausgabe |
|---|---|---|---|
| 1 | `01_inspect_dems.py` | Metadaten + Deckungsgleichheit prüfen | nur Konsolenausgabe |
| 2 | `02_prepare_rasters.py` | DEMs reprojizieren → EPSG:3857, NoData füllen | `app/build/dem_*_3857.tif` |
| 3 | `03_make_terrainrgb.py` | Höhe → Terrain-RGB (rio-rgbify) | `app/build/terrainrgb_*.tif` |
| 3b | `03b_make_hillshade.py` | Multidirektionaler Hillshade aus DEM (8-bit) | `app/build/hs_*_3857.tif` |
| 4 | `04_make_tiles.py` | XYZ-Kacheln (gdal2tiles) | `app/tiles/<name>/{z}/{x}/{y}.png` |

Ausführen jeweils aus dem Projekt-Root, z. B.:

```bash
python scripts/01_inspect_dems.py
python scripts/02_prepare_rasters.py
python scripts/03_make_terrainrgb.py
python scripts/03b_make_hillshade.py
python scripts/04_make_tiles.py
```

Nach jedem Schritt kurz das Ergebnis kontrollieren (Schritt 1 liefert die
Sanity-Checks, Schritt 2–3b/4 schreiben Dateien).

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

## Bekanntes Thema: NoData-Rand

Die DEMs haben große NoData-Ränder außerhalb des Tals (~1/3 der Fläche).
Schritt 2 füllt diese aktuell auf die Minimalhöhe → im 3D entsteht dort
eine flache Ebene. Für den ersten Prototyp ist das ok (der Kartenaus-
schnitt wird in Phase B aufs Tal begrenzt). Später ggf. die build-Raster
vor dem Kacheln auf die Tal-Bounding-Box zuschneiden, um flache Ränder
und unnötige Kacheln zu vermeiden.

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

Im Browser `http://localhost:8000/` öffnen. Es erscheint das aktuelle
3D-Relief (Hillshade über Terrain-RGB). Vorher/Nachher-Toggle, Export
und Zeichnen folgen in Phase C.
