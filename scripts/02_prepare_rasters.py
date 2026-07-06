"""Zuschnitt aufs Projektgebiet, Reprojektion nach EPSG:3857, Ebene aussen.

Für jedes DEM wird zuerst das Fenster ausgeschnitten, das das
Projektgebiet (``project_area.shp`` + Puffer) abdeckt, dann der Höhen-
Float bilinear nach Web Mercator umprojiziert und NoData-Ränder/-Löcher
gefüllt. Anschliessend werden alle Werte AUSSERHALB der Polygonform von
``project_area.shp`` auf eine einheitliche Ebenen-Höhe gesetzt (minimale
Höhe im Projektgebiet bzw. ``config.AOI_PLANE_HEIGHT``). So entsteht rund
um das Tal eine flache Ebene statt herausragender Berge/Gletscher.

Bewusst KEIN NoData ausserhalb: MapLibre-Terrain (raster-dem) hat kein
Alpha; NoData würde als Wand/Grube gerendert. Eine flache, niedrige Ebene
liefert stattdessen einen sauberen Sockel, auf dem das Tal sitzt. Beide
DEMs (modern + 1850) nutzen dieselbe Ebenen-Höhe, damit der
Vorher/Nachher-Toggle die Ebene nicht verschiebt.

Ergebnis ist die Eingabe fürs Terrain-RGB-Encoding (Schritt 03) und den
Hillshade (Schritt 03b).

Wichtige Details:
  * Das moderne DEM trägt KEIN NoData-Tag, enthält aber den Sentinel
    -9999. Dieser muss explizit als NoData angegeben werden, sonst wird
    er beim Reprojizieren mit echten Höhen verschmiert.
  * Das 1850-DEM (Cubic-Composite aus 00_build_lia_composite.py) nutzt
    denselben NoData-Sentinel -9999.

Ausführen:
    python scripts/02_prepare_rasters.py
"""

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
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


def aoi_polygon_mask(profile) -> np.ndarray:
    """Rastere das Projektgebiet-Polygon auf das aufbereitete Raster.

    Args:
        profile: Rasterio-Profil des reprojizierten DEM (crs, transform,
            width, height).

    Returns:
        np.ndarray: Boolesche Maske (True == innerhalb des Projektgebiets).
    """
    aoi = gpd.read_file(config.AOI_PATH)
    if aoi.crs is not None and str(aoi.crs) != str(profile["crs"]):
        aoi = aoi.to_crs(profile["crs"])
    return geometry_mask(aoi.geometry,
                         out_shape=(profile["height"], profile["width"]),
                         transform=profile["transform"], invert=True)


def prepare_dem(src_path, src_nodata: float) -> tuple:
    """Schneide zu, reprojiziere, fülle NoData und maskiere das Gebiet.

    Args:
        src_path: Pfad zum Eingangs-DEM.
        src_nodata: NoData-/Sentinel-Wert des Quell-DEM.

    Returns:
        tuple: (filled, profile, inside) mit dem gefüllten Höhen-Array
        (float32), dem Profil (EPSG:3857) und der Innen-Maske des
        Projektgebiets.
    """
    print(f"\n{src_path.name} (NoData={src_nodata}):")
    data, profile = reproject_clip(src_path, config.WEB_CRS, src_nodata)
    print(f"  zugeschnitten + reprojiziert nach {config.WEB_CRS} "
          f"({profile['width']} x {profile['height']} px)")
    filled = fill_gaps(data, src_nodata)
    inside = aoi_polygon_mask(profile)
    return filled, profile, inside


def write_with_plane(filled, profile, inside, plane_height: float,
                     dst_path) -> None:
    """Setze Werte ausserhalb des Projektgebiets auf die Ebene und schreibe.

    Args:
        filled: Gefülltes Höhen-Array (float32).
        profile: Rasterio-Profil (EPSG:3857, nodata=None).
        inside: Innen-Maske des Projektgebiets (True == innerhalb).
        plane_height: Einheitliche Höhe der Aussen-Ebene in Metern.
        dst_path: Zielpfad für das aufbereitete DEM.
    """
    out = filled.copy()
    out[~inside] = plane_height
    with rasterio.open(dst_path, "w", **profile) as dst:
        dst.write(out, 1)
    print(f"  ausserhalb Projektgebiet -> Ebene {plane_height:.1f} m "
          f"({int((~inside).sum())} px), geschrieben -> {dst_path}")


def main() -> None:
    """Bereite beide DEMs auf und lege aussen eine gemeinsame Ebene an."""
    config.BUILD_DIR.mkdir(parents=True, exist_ok=True)
    build = config.BUILD_DIR

    # Modernes DEM aufbereiten; daraus die gemeinsame Ebenen-Höhe ableiten.
    modern_filled, modern_profile, modern_inside = prepare_dem(
        config.DEM_MODERN, config.MODERN_NODATA)
    if config.AOI_PLANE_HEIGHT is not None:
        plane = float(config.AOI_PLANE_HEIGHT)
        print(f"  Ebenen-Höhe (fest aus config): {plane:.1f} m")
    else:
        plane = float(modern_filled[modern_inside].min())
        print(f"  Ebenen-Höhe (Min im Projektgebiet): {plane:.1f} m")
    write_with_plane(modern_filled, modern_profile, modern_inside, plane,
                     build / "dem_modern_3857.tif")

    # 1850-DEM mit derselben Ebenen-Höhe.
    lia_filled, lia_profile, lia_inside = prepare_dem(
        config.DEM_LIA, config.MODERN_NODATA)
    write_with_plane(lia_filled, lia_profile, lia_inside, plane,
                     build / "dem_lia_3857.tif")

    print("\nFertig. Weiter mit 03_make_terrainrgb.py")


if __name__ == "__main__":
    main()
