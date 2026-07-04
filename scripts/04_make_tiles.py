"""Erzeugung von XYZ-Kacheln (`{z}/{x}/{y}.png`) mit gdal2tiles.

Kachelt sowohl die Terrain-RGB-GeoTIFFs (Höhendaten) als auch die
Overlay-Texturen (Hillshades, später ggf. Orthofoto) in das von MapLibre
erwartete XYZ-Schema.

Zwei entscheidende Unterschiede beim Resampling:
  * Terrain-RGB: ``near`` – die kodierten Höhen dürfen NICHT interpoliert
    werden, sonst entstehen falsche Höhenwerte.
  * Overlays: ``average`` – glattere Verkleinerung ist hier erwünscht.

gdal2tiles wird über ``python -m osgeo_utils.gdal2tiles`` aufgerufen
(Teil der GDAL-Python-Utilities, in conda-gdal enthalten).

Die Hillshades stammen aus 03b_make_hillshade.py (Byte 0-255, EPSG:3857)
und liegen unter app/build/hs_*_3857.tif. Fehlen sie, werden die
Overlay-Aufrufe übersprungen.

Ausführen:
    python scripts/04_make_tiles.py
"""

import importlib.util
import shutil
import subprocess
import sys

import config


def resolve_gdal2tiles() -> list:
    """Ermittle den passenden Aufruf für gdal2tiles.

    Bevorzugt die Python-Utilities (``osgeo_utils.gdal2tiles``), fällt
    sonst auf ein Skript/Programm im PATH zurück.

    Returns:
        list: Basis-Kommando als Argumentliste.

    Raises:
        SystemExit: Wenn gdal2tiles nicht gefunden wird (mit Installhinweis).
    """
    if importlib.util.find_spec("osgeo_utils") is not None:
        return [sys.executable, "-m", "osgeo_utils.gdal2tiles"]
    for name in ("gdal2tiles.py", "gdal2tiles"):
        found = shutil.which(name)
        if found:
            return [found]
    sys.exit(
        "gdal2tiles nicht gefunden. Die GDAL-Python-Utilities fehlen in\n"
        "dieser Umgebung. Bitte installieren:\n"
        "    conda install -c conda-forge gdal\n"
        "und danach 04_make_tiles.py erneut ausführen."
    )


GDAL2TILES: list = resolve_gdal2tiles()


def tile(src_path, out_dir, resampling: str) -> None:
    """Kachle ein Raster ins XYZ-Schema.

    Args:
        src_path: Pfad zum Eingangsraster (Terrain-RGB oder Overlay).
        out_dir: Zielordner für die `{z}/{x}/{y}.png`-Struktur.
        resampling: gdal2tiles-Resampling-Methode ("near"/"average").

    Raises:
        subprocess.CalledProcessError: Wenn gdal2tiles fehlschlägt.
    """
    zoom = f"{config.MIN_ZOOM}-{config.MAX_ZOOM}"
    command = GDAL2TILES + [
        "--xyz",                       # XYZ statt TMS (MapLibre-konform)
        "-z", zoom,
        "--resampling", resampling,
        "--processes", str(config.NUM_PROCESSES),
        "-w", "none",                  # kein HTML-Viewer nötig
        str(src_path),
        str(out_dir),
    ]
    print("  " + " ".join(command))
    subprocess.run(command, check=True)
    print(f"  Kacheln -> {out_dir}")


def tile_if_exists(src_path, out_dir, resampling: str) -> None:
    """Kachle nur, wenn die Quelle existiert (für optionale Overlays).

    Args:
        src_path: Pfad zum Eingangsraster.
        out_dir: Zielordner für die Kacheln.
        resampling: gdal2tiles-Resampling-Methode.
    """
    if not src_path.exists():
        print(f"  übersprungen (fehlt): {src_path}")
        return
    tile(src_path, out_dir, resampling)


def main() -> None:
    """Erzeuge Kacheln für Terrain-RGB und (falls vorhanden) Overlays."""
    build = config.BUILD_DIR
    tiles = config.TILES_DIR
    tiles.mkdir(parents=True, exist_ok=True)

    # Terrain-RGB (Pflicht, near-Resampling).
    print("\nTerrain-RGB modern:")
    tile(build / "terrainrgb_modern.tif",
         tiles / "terrain_modern", config.TERRAIN_RESAMPLING)
    print("\nTerrain-RGB 1850:")
    tile(build / "terrainrgb_lia.tif",
         tiles / "terrain_lia", config.TERRAIN_RESAMPLING)

    # Overlays (Hillshades aus 03b, Byte 0-255). Fehlen sie, wird
    # übersprungen -> dann zuerst 03b_make_hillshade.py laufen lassen.
    print("\nHillshade modern:")
    tile_if_exists(build / "hs_modern_3857.tif",
                   tiles / "hillshade_modern", config.OVERLAY_RESAMPLING)
    print("\nHillshade 1850:")
    tile_if_exists(build / "hs_lia_3857.tif",
                   tiles / "hillshade_lia", config.OVERLAY_RESAMPLING)

    print("\nFertig. Kacheln liegen unter app/tiles/.")


if __name__ == "__main__":
    main()
