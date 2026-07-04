"""Karten-Metadaten (Mitte/Bounds) für die Web-App erzeugen.

Liest die Ausdehnung des aufbereiteten DEM (EPSG:3857), transformiert sie
nach WGS84 (Lon/Lat) und schreibt ``app/meta.json``. Die Web-App liest
diese Datei, um die Anfangsansicht auf das Tal zu zentrieren – so ist
keine Koordinate im HTML hartcodiert.

Ausführen:
    python scripts/05_web_meta.py
"""

import json
import sys

import rasterio
from rasterio.warp import transform_bounds

import config


def main() -> None:
    """Schreibe app/meta.json mit Kartenmitte und Bounds (WGS84)."""
    dem = config.BUILD_DIR / "dem_modern_3857.tif"
    if not dem.exists():
        print(f"FEHLT: {dem} - zuerst 02_prepare_rasters.py laufen lassen.")
        sys.exit(1)

    with rasterio.open(dem) as src:
        west, south, east, north = transform_bounds(
            src.crs, "EPSG:4326", *src.bounds)

    meta = {
        "center": [(west + east) / 2.0, (south + north) / 2.0],
        "bounds": [[west, south], [east, north]],
    }
    out_path = config.PROJECT_ROOT / "app" / "meta.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    print(f"  Mitte:  {meta['center']}")
    print(f"  Bounds: {meta['bounds']}")
    print(f"  geschrieben -> {out_path}")


if __name__ == "__main__":
    main()
