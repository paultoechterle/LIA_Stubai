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
DEM_LIA: Path = DATA_DIR / "DEM_5m_LIA.tif"           # Gletscherstand 1850

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