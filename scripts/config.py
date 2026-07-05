"""Zentrale Konfiguration für die Datenaufbereitungs-Pipeline.

Alle Pfade und Parameter der Phase-A-Skripte stehen hier an einer
Stelle. Pfade werden relativ zum Projekt-Root aufgelöst, damit nichts
absolut hartcodiert ist und das Projekt verschiebbar bleibt.

Reihenfolge der Skripte:
    01_inspect_dems.py    -> Metadaten/Sanity-Check der DEMs
    02_prepare_rasters.py -> Reprojektion nach EPSG:3857 + NoData füllen
    03_make_terrainrgb.py -> Terrain-RGB-Encoding (rio-rgbify)
    04_make_tiles.py      -> XYZ-Kacheln (gdal2tiles) für Terrain + Overlays
"""

from pathlib import Path

# --- Verzeichnisse -------------------------------------------------------
# Projekt-Root ist der Ordner eine Ebene über diesem scripts/-Ordner.
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = PROJECT_ROOT / "data"
BUILD_DIR: Path = PROJECT_ROOT / "app" / "build"      # Zwischenprodukte
TILES_DIR: Path = PROJECT_ROOT / "app" / "tiles"      # fertige XYZ-Kacheln

# --- Eingangsdaten (vorhanden) ------------------------------------------
DEM_MODERN: Path = DATA_DIR / "DEM_5m_modern.tif"
# 1850-DEM der Pipeline: das weiche Cubic-Composite aus
# 00_build_lia_composite.py. Die alte, grob resampelte QGIS-Variante
# (DEM_5m_LIA.tif) bleibt als Fallback auf der Platte, wird aber nicht
# mehr verarbeitet.
DEM_LIA: Path = DATA_DIR / "DEM_5m_LIA_cubic.tif"     # Gletscherstand 1850

# --- 1850-Composite aus der Reinthaler-Gletscheroberfläche --------------
# Rohdaten: Alpenweite LIA-Gletscheroberfläche (Reinthaler et al. 2024),
# grob aufgelöst und größtenteils NoData (nur Gletscherflächen). Das
# Script 00_build_lia_composite.py schneidet sie aufs Projektgebiet zu,
# resampled sie per Cubic-Spline aufs 5-m-Raster des modernen DEM und
# legt sie gefedert als Eiskörper auf das moderne Terrain -> weicheres,
# schöneres 1850-DEM als die grob resampelte QGIS-Variante. Das Ergebnis
# wird nach DEM_LIA geschrieben und von der Pipeline (01/02) konsumiert.
REINTHALER_LIA_SRC: Path = (
    DATA_DIR / "Reinthaler et al 2024" / "LIA_glacier_surface_Alps.tif")

# Puffer (in Metern, Quell-CRS) für den Zuschnitt der groben Quelle. Etwas
# großzügig, damit der Cubic-Kernel am Rand echten Kontext hat statt
# gefüllter Werte.
LIA_CLIP_BUFFER: float = 500.0

# NoData-/Sentinel-Werte der Eingangsraster (kein sauberer NoData-Tag).
LIA_SRC_NODATA: float = -10000.0
MODERN_NODATA: float = -9999.0

# Nach dem Cubic-Spline optional zusätzliche maskierte Glättungs-
# Iterationen (Normalized Convolution) zum Polieren der Treppenstufen der
# groben Quelle. 0 = reines Cubic-Spline. Sigma in Ziel-Pixeln (5 m).
LIA_SMOOTH_ITERATIONS: int = 2
LIA_SMOOTH_SIGMA: float = 1.5

# Maskenschwelle: Anteil Gletscherüberdeckung, ab dem ein Zielpixel als
# Gletscher gilt (0.5 = Pixelmittelpunkt lag im Gletscher).
LIA_MASK_THRESHOLD: float = 0.5

# Feathering des Gletscherrandes: Die Eisdicke fadet von der Maskenkante
# (Dicke 0) ueber diesen Radius nach innen auf volle Dicke. Vermeidet die
# harte Stufe zum modernen DEM und entspricht dem natuerlichen Auslaufen
# eines Gletschers auf ~0 Dicke am Rand. In Metern; 0 = harte Kante.
LIA_FEATHER_RADIUS: float = 50.0

# --- Hillshades ----------------------------------------------------------
# Die Hillshade-Overlays werden NICHT aus diesen Dateien gekachelt,
# sondern in 03b_make_hillshade.py direkt aus den reprojizierten DEMs
# erzeugt (garantiert 8-bit 0-255, pixelgenau zum Terrain). Die Pfade
# bleiben nur für die Inspektion (01) als Referenz erhalten.
HILLSHADE_MODERN: Path = DATA_DIR / "HS_5m_modern.tif"
HILLSHADE_LIA: Path = DATA_DIR / "HS_5m_LIA.tif"

# --- Projektgebiet (Zuschnitt) ------------------------------------------
# Vor dem Kacheln werden die Raster auf dieses Gebiet zugeschnitten, damit
# nur das Tal gekachelt wird statt des großen, leeren DEM-Randes. Das
# reduziert die Kachelzahl massiv und entfernt die flache Rand-Ebene im 3D.
AOI_PATH: Path = DATA_DIR / "project_area.shp"
AOI_BUFFER: float = 200.0     # Puffer um das Gebiet in Metern (Quell-CRS)

# --- POIs (Gipfel & Gletscher) ------------------------------------------
# TIRIS-Export (Quelle, EPSG:31254) -> schlanke, web-fertige GeoJSON in
# WGS84 fürs MapLibre-Rendering (Schritt 07_make_pois.py).
POIS_SRC: Path = PROJECT_ROOT / "GIS" / "temp files" / "POIs_all.geojson"
POIS_OUT: Path = PROJECT_ROOT / "app" / "pois.geojson"

# --- Projektionsparameter ------------------------------------------------
SRC_CRS: str = "EPSG:31254"      # MGI / Austria GK West (Ausgangs-CRS)
WEB_CRS: str = "EPSG:3857"       # Web Mercator (von MapLibre erwartet)

# --- Terrain-RGB-Encoding (Mapbox-Spezifikation) ------------------------
# height = base + (R*256*256 + G*256 + B) * interval
# MapLibre-Source muss dazu passend "encoding: 'mapbox'" verwenden.
RGBIFY_BASE: float = -10000.0
RGBIFY_INTERVAL: float = 0.1

# --- Kachel-Parameter ----------------------------------------------------
# 5 m Auflösung entspricht grob Zoom 15; z16 wäre bereits Überabtastung
# (z15 ~ 3,3 m/px bei 47° N) und vervierfacht nur die Kachelzahl.
MIN_ZOOM: int = 10
MAX_ZOOM: int = 15

# Resampling: Terrain-RGB MUSS "near" sein, sonst werden die kodierten
# Höhenwerte interpoliert und dadurch verfälscht. Overlays (Hillshade,
# Orthofoto) dürfen "average" nutzen (glattere Verkleinerung).
TERRAIN_RESAMPLING: str = "near"
OVERLAY_RESAMPLING: str = "average"

# Anzahl paralleler Prozesse für gdal2tiles (an CPU anpassen).
NUM_PROCESSES: int = 4

# --- Hillshade-Erzeugung (gdal.DEMProcessing) ---------------------------
# Multidirektionaler Hillshade: kombiniert Beleuchtung aus mehreren
# Richtungen -> plastischer, keine harten Schattenkanten. Der Azimut
# wird dabei ignoriert (deshalb hier nicht gesetzt).
HS_MULTIDIRECTIONAL: bool = True
HS_ALTITUDE: float = 45.0     # Sonnenhöhe über dem Horizont in Grad
HS_Z_FACTOR: float = 1.0      # Überhöhung (1.0 = keine)