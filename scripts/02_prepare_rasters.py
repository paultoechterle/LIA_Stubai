"""Zuschnitt aufs Projektgebiet, Reprojektion nach EPSG:3857, NoData füllen.

Für jedes DEM wird zuerst das Fenster ausgeschnitten, das das
Projektgebiet (``project_area.shp`` + Puffer) abdeckt, dann der Höhen-
Float bilinear nach Web Mercator umprojiziert, NoData-Ränder/-Löcher
gefüllt und das NoData-Tag entfernt. Ergebnis ist die Eingabe fürs
Terrain-RGB-Encoding (Schritt 03) und den Hillshade (Schritt 03b).

Der Zuschnitt reduziert die spätere Kachelzahl massiv (nur das Tal statt
des gesamten, überwiegend leeren DEM-Rechtecks) und entfernt die flache
Rand-Ebene, die sonst im 3D um das Tal herum entstünde.

Wichtige Details:
  * Das moderne DEM trägt KEIN NoData-Tag, enthält aber den Sentinel
    -9999. Dieser muss explizit als NoData angegeben werden, sonst wird
    er beim Reprojizieren mit echten Höhen verschmiert.
  * Das 1850-DEM hat NoData -10000.
  * Nach dem Füllen wird ``nodata=None`` gesetzt, weil das anschließende
    Terrain-RGB-Encoding (uint8) keinen Wert wie -10000 halten kann.

Ausführen:
    python scripts/02_prepare_rasters.py
"""

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.fill import fillnodata
from rasterio.warp import calculate_default_transform, reproject
from rasterio.windows import bounds as window_bounds
from rasterio.windows import from_bounds

import config

# Maximale Suchdistanz (in Pixeln) für das Füllen von NoData-Lücken.
# 100 px * 5 m = 500 m; dünne Randstreifen werden interpoliert, größere
# verbleibende Löcher danach auf die gültige Minimalhöhe gesetzt.
FILL_MAX_DISTANCE: int = 100


def aoi_bounds_in(crs) -> tuple:
    """Ermittle die (gepufferten) Bounds des Projektgebiets in einem CRS.

    Args:
        crs: Ziel-CRS, in dem die Bounds benötigt werden (z. B. das
            CRS des Quell-DEM).

    Returns:
        tuple: (minx, miny, maxx, maxy) inkl. Puffer aus config.AOI_BUFFER.
    """
    aoi = gpd.read_file(config.AOI_PATH)
    if aoi.crs is not None and str(aoi.crs) != str(crs):
        aoi = aoi.to_crs(crs)
    minx, miny, maxx, maxy = aoi.total_bounds
    buffer = config.AOI_BUFFER
    return (minx - buffer, miny - buffer, maxx + buffer, maxy + buffer)


def reproject_clip(src_path, dst_crs: str, src_nodata: float):
    """Schneide ein DEM aufs Projektgebiet zu und reprojiziere es bilinear.

    Args:
        src_path: Pfad zum Eingangs-DEM.
        dst_crs: Ziel-CRS (z. B. "EPSG:3857").
        src_nodata: NoData-Wert des Quell-DEM (explizit, da das moderne
            DEM keinen NoData-Tag trägt).

    Returns:
        tuple: (data, profile) mit dem zugeschnittenen, reprojizierten
        Array (float32, NoData-Bereiche == src_nodata) und dem Profil.
    """
    with rasterio.open(src_path) as src:
        aoi = aoi_bounds_in(src.crs)
        window = from_bounds(*aoi, transform=src.transform)
        window = window.round_offsets().round_lengths()
        # boundless: falls der gepufferte Ausschnitt leicht über den Rand
        # ragt, werden fehlende Bereiche mit src_nodata aufgefüllt.
        data = src.read(1, window=window, boundless=True,
                        fill_value=src_nodata)
        src_transform = src.window_transform(window)
        clip_bounds = window_bounds(window, src.transform)

        dst_transform, width, height = calculate_default_transform(
            src.crs, dst_crs, data.shape[1], data.shape[0], *clip_bounds)
        destination = np.full((height, width), src_nodata, dtype="float32")
        reproject(
            source=data,
            destination=destination,
            src_transform=src_transform,
            src_crs=src.crs,
            src_nodata=src_nodata,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            dst_nodata=src_nodata,
            resampling=Resampling.bilinear,
        )
        profile = src.profile.copy()
        profile.update(crs=dst_crs, transform=dst_transform, width=width,
                       height=height, dtype="float32", count=1, nodata=None)
    return destination, profile


def fill_gaps(data: np.ndarray, nodata: float) -> np.ndarray:
    """Fülle NoData-Lücken per Interpolation und beseitige Restlöcher.

    Args:
        data: Reprojiziertes Höhen-Array (NoData-Bereiche == nodata).
        nodata: NoData-Wert im Array.

    Returns:
        np.ndarray: Vollständig gefülltes float32-Array ohne NoData.
    """
    mask = (data != nodata).astype(np.uint8)
    filled = fillnodata(data, mask=mask,
                        max_search_distance=FILL_MAX_DISTANCE)
    remaining = filled == nodata
    if remaining.any():
        valid_min = float(filled[~remaining].min())
        filled[remaining] = valid_min
        print(f"  {int(remaining.sum())} Restpixel auf {valid_min:.1f} m "
              "gesetzt (außerhalb Suchdistanz)")
    return filled


def prepare(src_path, dst_path, src_nodata: float) -> None:
    """Schneide zu, reprojiziere, fülle NoData und schreibe das Ergebnis.

    Args:
        src_path: Pfad zum Eingangs-DEM.
        dst_path: Pfad für das aufbereitete DEM (EPSG:3857, ohne NoData).
        src_nodata: NoData-/Sentinel-Wert des Quell-DEM.
    """
    print(f"\n{src_path.name} (NoData={src_nodata}):")
    data, profile = reproject_clip(src_path, config.WEB_CRS, src_nodata)
    print(f"  zugeschnitten + reprojiziert nach {config.WEB_CRS} "
          f"({profile['width']} x {profile['height']} px)")
    filled = fill_gaps(data, src_nodata)
    with rasterio.open(dst_path, "w", **profile) as dst:
        dst.write(filled, 1)
    print(f"  geschrieben -> {dst_path}")


def main() -> None:
    """Bereite beide DEMs für das Terrain-RGB-Encoding auf."""
    config.BUILD_DIR.mkdir(parents=True, exist_ok=True)
    # Moderne: Sentinel -9999 (kein NoData-Tag). 1850: NoData -10000.
    prepare(config.DEM_MODERN,
            config.BUILD_DIR / "dem_modern_3857.tif", -9999.0)
    prepare(config.DEM_LIA,
            config.BUILD_DIR / "dem_lia_3857.tif", -10000.0)
    # Hillshades werden NICHT hier aufbereitet: Overlays dürfen NoData
    # nicht auf einen flachen Wert füllen (das gehört transparent). Sie
    # werden in 03b_make_hillshade.py direkt aus diesen DEMs erzeugt.
    print("\nFertig. Weiter mit 03_make_terrainrgb.py")


if __name__ == "__main__":
    main()
