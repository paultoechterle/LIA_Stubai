"""Metadaten- und Plausibilitätsprüfung der beiden DEMs.

Gibt für das moderne und das 1850-DEM die wichtigsten Kenngrößen aus
(CRS, Auflösung, Ausdehnung, NoData, Höhenbereich) und prüft, ob beide
tatsächlich pixelgenau übereinanderliegen. Dieser Schritt verändert
keine Daten, er dient nur der Kontrolle vor der Aufbereitung.

Ausführen:
    python scripts/01_inspect_dems.py
"""

import rasterio

import config


def describe_dem(path) -> dict:
    """Lies die wichtigsten Metadaten eines DEM aus.

    Args:
        path: Pfad zur GeoTIFF-Datei.

    Returns:
        dict: Kenngrößen (crs, res, bounds, nodata, dtype, min, max).
    """
    with rasterio.open(path) as dataset:
        stats = dataset.statistics(1, approx=True)
        return {
            "path": str(path),
            "crs": str(dataset.crs),
            "res": dataset.res,
            "width": dataset.width,
            "height": dataset.height,
            "bounds": tuple(round(v, 2) for v in dataset.bounds),
            "nodata": dataset.nodata,
            "dtype": dataset.dtypes[0],
            "min": round(stats.min, 2),
            "max": round(stats.max, 2),
        }


def print_report(label: str, info: dict) -> None:
    """Gib einen lesbaren Metadaten-Block auf der Konsole aus.

    Args:
        label: Bezeichnung des Datensatzes.
        info: Kenngrößen-Dict aus describe_dem().
    """
    print(f"\n=== {label} ===")
    print(f"  Datei:      {info['path']}")
    print(f"  CRS:        {info['crs']}")
    print(f"  Auflösung:  {info['res']}")
    print(f"  Größe:      {info['width']} x {info['height']} px")
    print(f"  Ausdehnung: {info['bounds']}")
    print(f"  NoData:     {info['nodata']}")
    print(f"  Datentyp:   {info['dtype']}")
    print(f"  Höhe min:   {info['min']} m")
    print(f"  Höhe max:   {info['max']} m")


def check_alignment(a: dict, b: dict) -> None:
    """Prüfe, ob zwei DEMs deckungsgleich sind (CRS, Raster, Extent).

    Args:
        a: Kenngrößen des ersten DEM.
        b: Kenngrößen des zweiten DEM.
    """
    print("\n=== Deckungsgleichheit ===")
    same_crs = a["crs"] == b["crs"]
    same_grid = (a["width"], a["height"]) == (b["width"], b["height"])
    same_res = a["res"] == b["res"]
    same_bounds = a["bounds"] == b["bounds"]
    print(f"  CRS identisch:        {same_crs}")
    print(f"  Rastergröße gleich:   {same_grid}")
    print(f"  Auflösung gleich:     {same_res}")
    print(f"  Ausdehnung gleich:    {same_bounds}")
    if all([same_crs, same_grid, same_res, same_bounds]):
        print("  -> DEMs liegen pixelgenau übereinander.")
    else:
        print("  -> ACHTUNG: DEMs sind NICHT deckungsgleich, "
              "vor dem Compositing angleichen.")


def main() -> None:
    """Führe die Inspektion beider DEMs aus."""
    modern = describe_dem(config.DEM_MODERN)
    lia = describe_dem(config.DEM_LIA)
    hs_modern = describe_dem(config.HILLSHADE_MODERN)
    hs_lia = describe_dem(config.HILLSHADE_LIA)
    print_report("DEM modern", modern)
    print_report("DEM 1850 (LIA)", lia)
    print_report("Hillshade modern", hs_modern)
    print_report("Hillshade 1850 (LIA)", hs_lia)
    check_alignment(modern, lia)


if __name__ == "__main__":
    main()