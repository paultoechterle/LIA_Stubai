"""Terrain-RGB-Encoding der aufbereiteten DEMs mit rio-rgbify.

Wandelt die Float-Höhen in ein RGB-GeoTIFF um, in dem die Höhe nach der
Mapbox-Terrain-RGB-Spezifikation als Farbwert kodiert ist:

    height = base + (R*65536 + G*256 + B) * interval

Das Ergebnis (RGB-GeoTIFF) ist die Eingabe für das Kacheln in Schritt 04.
In MapLibre muss die zugehörige Source ``encoding: 'mapbox'`` verwenden.

Ruft das CLI ``rio rgbify`` per subprocess auf – dieses muss in der
aktiven (conda-)Umgebung installiert sein.

Ausführen:
    python scripts/03_make_terrainrgb.py
"""

import subprocess
import sys

import config


def rgbify(src_path, dst_path) -> None:
    """Encodiere ein Float-DEM als Terrain-RGB-GeoTIFF.

    Args:
        src_path: Pfad zum aufbereiteten DEM (EPSG:3857).
        dst_path: Pfad für das Terrain-RGB-GeoTIFF.

    Raises:
        subprocess.CalledProcessError: Wenn der rio-rgbify-Aufruf
            fehlschlägt.
    """
    command = [
        "rio", "rgbify",
        "-b", str(config.RGBIFY_BASE),
        "-i", str(config.RGBIFY_INTERVAL),
        str(src_path),
        str(dst_path),
    ]
    print("  " + " ".join(command))
    subprocess.run(command, check=True)
    print(f"  Terrain-RGB -> {dst_path}")


def main() -> None:
    """Encodiere beide aufbereiteten DEMs als Terrain-RGB."""
    build = config.BUILD_DIR
    pairs = [
        (build / "dem_modern_3857.tif", build / "terrainrgb_modern.tif"),
        (build / "dem_lia_3857.tif", build / "terrainrgb_lia.tif"),
    ]
    for src_path, dst_path in pairs:
        if not src_path.exists():
            print(f"FEHLT: {src_path} – zuerst 02_prepare_rasters.py laufen "
                  "lassen.")
            sys.exit(1)
        print(f"\n{src_path.name}:")
        rgbify(src_path, dst_path)
    print("\nFertig. Weiter mit 04_make_tiles.py")


if __name__ == "__main__":
    main()
