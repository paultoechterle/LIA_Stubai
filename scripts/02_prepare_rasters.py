"""Reprojektion der DEMs nach EPSG:3857 und Füllen von NoData-Lücken.

Für jedes DEM wird der Höhen-Float mit bilinearer Interpolation nach
Web Mercator umprojiziert, NoData-Ränder/-Löcher werden gefüllt und
anschließend wird das NoData-Tag entfernt. Das Ergebnis ist die Eingabe
für das Terrain-RGB-Encoding (Schritt 03).

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

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.fill import fillnodata
from rasterio.warp import calculate_default_transform, reproject

import config

# Maximale Suchdistanz (in Pixeln) für das Füllen von NoData-Lücken.
# 100 px * 5 m = 500 m; dünne Randstreifen werden interpoliert, größere
# verbleibende Löcher danach auf die gültige Minimalhöhe gesetzt.
FILL_MAX_DISTANCE: int = 100


def reproject_to_array(src_path, dst_crs: str, src_nodata: float):
    """Reprojiziere ein Float-DEM bilinear in ein Ziel-CRS.

    Args:
        src_path: Pfad zum Eingangs-DEM.
        dst_crs: Ziel-CRS (z. B. "EPSG:3857").
        src_nodata: NoData-Wert des Quell-DEM (explizit, da das moderne
            DEM keinen NoData-Tag trägt).

    Returns:
        tuple: (data, profile) mit dem reprojizierten Array (float32,
        NoData-Bereiche == src_nodata) und dem passenden rasterio-Profil.
    """
    with rasterio.open(src_path) as src:
        transform, width, height = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds)
        destination = np.full((height, width), src_nodata, dtype="float32")
        reproject(
            source=rasterio.band(src, 1),
            destination=destination,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=src_nodata,
            dst_transform=transform,
            dst_crs=dst_crs,
            dst_nodata=src_nodata,
            resampling=Resampling.bilinear,
        )
        profile = src.profile.copy()
        profile.update(crs=dst_crs, transform=transform, width=width,
                       height=height, dtype="float32", count=1,
                       nodata=None)
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
    """Reprojiziere ein DEM, fülle NoData und schreibe das Ergebnis.

    Args:
        src_path: Pfad zum Eingangs-DEM.
        dst_path: Pfad für das aufbereitete DEM (EPSG:3857, ohne NoData).
        src_nodata: NoData-/Sentinel-Wert des Quell-DEM.
    """
    print(f"\n{src_path.name} (NoData={src_nodata}):")
    data, profile = reproject_to_array(src_path, config.WEB_CRS, src_nodata)
    print(f"  reprojiziert nach {config.WEB_CRS}")
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
