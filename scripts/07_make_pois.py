"""POIs (Gipfel & Gletscher) fürs Web aufbereiten.

Nimmt den TIRIS-Export (``POIs_all.geojson``, EPSG:31254), schneidet ihn
aufs Projektgebiet zu, reprojiziert nach WGS84 (EPSG:4326, von MapLibre
erwartet) und schreibt eine schlanke ``app/pois.geojson`` mit nur den
Feldern, die die Web-App braucht.

Ableitung der Felder aus ``OBJEKTART``:
  * ``kind``  = "glacier" (beginnt mit "Gletscher") | "peak"
  * ``rank``  = "major" (regional bedeutender Gipfel ODER Gletscher) |
                "minor" (lokal bedeutender Gipfel)
  * ``name``  = ``NAME``
  * ``ele``   = ``HOEHE`` als int (bei Gletschern ohne Höhe weggelassen)

``rank`` steuert im Style, ab welcher Zoomstufe ein Gipfel erscheint:
markante Gipfel + alle Gletscher sind immer sichtbar, lokale Gipfel erst
beim Reinzoomen. Der Zuschnitt aufs Projektgebiet entfernt weit entfernte
Punkte (z. B. Rettenbach-/Taschachferner im Ötztal), die sonst auf dem
flachen Füllgelände am Rand "schweben" würden.

Ausführen:
    python scripts/07_make_pois.py
"""

import json
import math

import geopandas as gpd

import config

# Nachkommastellen für die Ausgabe-Koordinaten (Grad). 6 -> ~0,1 m,
# mehr als ausreichend und hält die Datei klein.
COORD_PRECISION: int = 6

# Ziel-CRS der Web-Ausgabe (Längengrad/Breitengrad).
OUT_CRS: str = "EPSG:4326"


def classify(objektart: str) -> tuple:
    """Leite (kind, rank) aus dem TIRIS-Feld ``OBJEKTART`` ab.

    Args:
        objektart: Wert des Felds ``OBJEKTART`` (z. B. "Berg regional
            bedeutend" oder "Gletscher regional bedeutend").

    Returns:
        tuple: (kind, rank) mit kind in {"peak", "glacier"} und rank in
        {"major", "minor"}.
    """
    text = objektart or ""
    if text.startswith("Gletscher"):
        return "glacier", "major"
    if "regional" in text:
        return "peak", "major"
    return "peak", "minor"


def build_feature(name: str, ele, kind: str, rank: str,
                  lon: float, lat: float) -> dict:
    """Baue ein schlankes GeoJSON-Feature mit gerundeten Koordinaten.

    Args:
        name: Anzeigename des POI.
        ele: Höhe in Metern oder None (Gletscher ohne Höhenangabe).
        kind: "peak" oder "glacier".
        rank: "major" oder "minor".
        lon: Längengrad (Grad).
        lat: Breitengrad (Grad).

    Returns:
        dict: GeoJSON-Feature (Point) mit den Properties name/kind/rank
        und – falls vorhanden – ele.
    """
    properties = {"name": name, "kind": kind, "rank": rank}
    # Manche Gipfel (und alle Gletscher) haben keine Höhe -> NaN/None.
    has_ele = ele is not None and not (
        isinstance(ele, float) and math.isnan(ele))
    if has_ele:
        properties["ele"] = int(round(ele))
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {
            "type": "Point",
            "coordinates": [round(lon, COORD_PRECISION),
                            round(lat, COORD_PRECISION)],
        },
    }


def clip_to_aoi(pois: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Schneide die POIs aufs (gepufferte) Projektgebiet zu.

    Args:
        pois: Eingelesene POIs im Quell-CRS (EPSG:31254).

    Returns:
        gpd.GeoDataFrame: Nur die Punkte innerhalb von project_area +
        Puffer, im selben CRS wie die Eingabe.
    """
    aoi = gpd.read_file(config.AOI_PATH)
    if aoi.crs is not None and str(aoi.crs) != str(pois.crs):
        aoi = aoi.to_crs(pois.crs)
    aoi_buffered = gpd.GeoDataFrame(
        geometry=aoi.buffer(config.AOI_BUFFER), crs=aoi.crs)
    return gpd.clip(pois, aoi_buffered)


def main() -> None:
    """Lies den TIRIS-Export, klippe/reprojiziere und schreibe die Web-POIs.

    Raises:
        FileNotFoundError: Wenn der TIRIS-Export nicht gefunden wird.
    """
    if not config.POIS_SRC.exists():
        raise FileNotFoundError(
            f"POI-Quelle nicht gefunden: {config.POIS_SRC}")

    pois = gpd.read_file(config.POIS_SRC)
    print(f"{len(pois)} POIs eingelesen ({pois.crs}).")

    pois = clip_to_aoi(pois)
    print(f"  {len(pois)} POIs im Projektgebiet (+{config.AOI_BUFFER} m).")

    pois = pois.to_crs(OUT_CRS)

    features = []
    counts = {"peak_major": 0, "peak_minor": 0, "glacier": 0}
    for row in pois.itertuples(index=False):
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        kind, rank = classify(getattr(row, "OBJEKTART", ""))
        ele = getattr(row, "HOEHE", None)
        features.append(build_feature(
            name=getattr(row, "NAME", ""), ele=ele, kind=kind, rank=rank,
            lon=geom.x, lat=geom.y))
        key = "glacier" if kind == "glacier" else f"peak_{rank}"
        counts[key] += 1

    collection = {"type": "FeatureCollection", "features": features}
    config.POIS_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(config.POIS_OUT, "w", encoding="utf-8") as handle:
        json.dump(collection, handle, ensure_ascii=False)

    print(f"\n{len(features)} POIs geschrieben -> {config.POIS_OUT}")
    print(f"  markante Gipfel: {counts['peak_major']}, "
          f"lokale Gipfel: {counts['peak_minor']}, "
          f"Gletscher: {counts['glacier']}")


if __name__ == "__main__":
    main()
