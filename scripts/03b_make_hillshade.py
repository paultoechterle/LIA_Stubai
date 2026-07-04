"""Multidirektionale Hillshade-Overlays aus den DEMs erzeugen.

Erzeugt aus den in Schritt 02 aufbereiteten DEMs (EPSG:3857) mit
``gdal.DEMProcessing`` 8-bit-Hillshades (0-255). Diese dienen in
Schritt 04 als Overlay-Textur.

Warum aus dem DEM statt aus externen (QGIS-)Dateien:
  * gdal2tiles akzeptiert nur 8-bit-Raster; DEMProcessing liefert das
    direkt als Byte 0-255.
  * Das Ergebnis liegt pixelgenau auf dem Terrain (dasselbe DEM).
  * Keine Abhängigkeit von Float-Hillshades mit unklarem Wertebereich.

Der Hillshade ist multidirektional (Beleuchtung aus mehreren Richtungen),
das wirkt plastischer und vermeidet harte Schattenkanten.

Benötigt die osgeo/GDAL-Python-Bindings (conda-forge gdal).

Ausführen:
    python scripts/03b_make_hillshade.py
"""

import sys

from osgeo import gdal

import config

gdal.UseExceptions()


def make_hillshade(src_path, dst_path) -> None:
    """Erzeuge einen multidirektionalen 8-bit-Hillshade aus einem DEM.

    Args:
        src_path: Pfad zum aufbereiteten DEM (EPSG:3857, float32).
        dst_path: Pfad für den Hillshade (GeoTIFF, Byte 0-255).

    Raises:
        RuntimeError: Wenn gdal.DEMProcessing fehlschlägt.
    """
    options = gdal.DEMProcessingOptions(
        multiDirectional=config.HS_MULTIDIRECTIONAL,
        altitude=config.HS_ALTITUDE,
        zFactor=config.HS_Z_FACTOR,
        computeEdges=True,
        format="GTiff",
    )
    gdal.DEMProcessing(str(dst_path), str(src_path), "hillshade",
                       options=options)
    print(f"  Hillshade -> {dst_path}")


def main() -> None:
    """Erzeuge Hillshades für das moderne und das 1850-DEM."""
    build = config.BUILD_DIR
    pairs = [
        (build / "dem_modern_3857.tif", build / "hs_modern_3857.tif"),
        (build / "dem_lia_3857.tif", build / "hs_lia_3857.tif"),
    ]
    for src_path, dst_path in pairs:
        if not src_path.exists():
            print(f"FEHLT: {src_path} - zuerst 02_prepare_rasters.py "
                  "laufen lassen.")
            sys.exit(1)
        print(f"\n{src_path.name}:")
        make_hillshade(src_path, dst_path)
    print("\nFertig. Weiter mit 04_make_tiles.py")


if __name__ == "__main__":
    main()
