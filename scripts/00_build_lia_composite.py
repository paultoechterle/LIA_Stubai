"""1850-DEM als weiches Composite aus der Reinthaler-Gletscheroberflaeche.

Erzeugt ein optisch ansprechenderes 1850-DEM, indem die alpenweite
LIA-Gletscheroberflaeche (Reinthaler et al. 2024) per Cubic-Spline aufs
5-m-Raster des modernen DEM interpoliert und als Eiskoerper auf das
moderne Terrain gelegt wird.

Warum dieser Weg das bekannte Blockmuster vermeidet:
  * Die Quelle ist grob aufgeloest; ein direktes Nearest-/Bilinear-
    Resampling auf 5 m laesst die groben Quellpixel als Stufen stehen.
  * Cubic-Spline interpoliert C1/C2-stetig zwischen den Quellpixeln und
    liefert eine glatt gewoelbte Eisoberflaeche.
  * Vor dem Resampling werden die NoData-Bereiche des Ausschnitts
    gefuellt, damit der Cubic-Kernel am Gletscherrand nicht ueber
    NoData-Kanten schwingt (Ringing). Die echte Gletscherausdehnung wird
    danach ueber eine separat resampelte Maske wiederhergestellt.

Ablauf:
  1. Reinthaler-Raster auf die (gepufferte) Ausdehnung des modernen DEM
     zuschneiden (im nativen CRS/Aufloesung der Quelle).
  2. NoData im Ausschnitt fuellen (glatte Extrapolation).
  3. Gefuelltes Feld per Cubic-Spline aufs exakte Modern-Raster
     reprojizieren (CRS + 5 m in einem Schritt).
  4. Gueltigkeitsmaske separat resampeln und schwellwerten -> saubere
     Gletscherausdehnung auf dem Zielraster.
  5. Optional maskierte Glaettungs-Iterationen ("ggf. mehrfach").
  6. Composite: modernes Terrain ueberall, innerhalb der Maske
     max(Gletscheroberflaeche, Terrain) -> nahtloser Uebergang, Eis nie
     unter Grund.

Das Ergebnis wird nach config.DEM_LIA geschrieben und ist damit direkt
das 1850-DEM der Pipeline (01_inspect_dems.py / 02_prepare_rasters.py).
Die alte QGIS-Variante (DEM_5m_LIA.tif) bleibt als Fallback erhalten.

Ausfuehren:
    python scripts/00_build_lia_composite.py
"""

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.fill import fillnodata
from rasterio.transform import array_bounds
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import from_bounds
from scipy.ndimage import distance_transform_edt, gaussian_filter

import config

# Maximale Suchdistanz (in Quellpixeln) fuer das Fuellen der NoData-Luecken
# vor dem Resampling. Grosszuegig, damit der Rand des Ausschnitts fuer den
# Cubic-Kernel durchgehend belegt ist.
FILL_MAX_DISTANCE: int = 200


def read_modern_grid() -> tuple:
    """Lies Zielraster (CRS, Transform, Groesse) und Werte des modernen DEM.

    Returns:
        tuple: (profile, transform, crs, width, height, modern) mit dem
        modernen Hoehen-Array (float32) und seinem Profil. Das Zielraster
        des Composites ist exakt dieses Raster.
    """
    with rasterio.open(config.DEM_MODERN) as src:
        modern = src.read(1).astype("float32")
        profile = src.profile.copy()
        return (profile, src.transform, src.crs, src.width, src.height,
                modern)


def clip_source_to(dst_crs, dst_bounds, buffer: float) -> tuple:
    """Schneide die Reinthaler-Quelle auf die Ziel-Ausdehnung zu.

    Args:
        dst_crs: CRS des Zielrasters (modernes DEM).
        dst_bounds: (minx, miny, maxx, maxy) des Zielrasters in dst_crs.
        buffer: Puffer in Metern (im Quell-CRS) um die Ausdehnung.

    Returns:
        tuple: (data, transform, src_crs) mit dem zugeschnittenen
        Quell-Array (float32, NoData == config.LIA_SRC_NODATA), der
        zugehoerigen Affine-Transformation und dem Quell-CRS.
    """
    with rasterio.open(config.REINTHALER_LIA_SRC) as src:
        print(f"  Quelle: CRS={src.crs}, Res={src.res}, "
              f"NoData={src.nodata}, dtype={src.dtypes[0]}")
        # Ziel-Bounds ins Quell-CRS transformieren und puffern.
        minx, miny, maxx, maxy = transform_bounds(dst_crs, src.crs,
                                                   *dst_bounds)
        minx, miny = minx - buffer, miny - buffer
        maxx, maxy = maxx + buffer, maxy + buffer
        window = from_bounds(minx, miny, maxx, maxy, transform=src.transform)
        window = window.round_offsets().round_lengths()
        src_nodata = src.nodata if src.nodata is not None \
            else config.LIA_SRC_NODATA
        data = src.read(1, window=window, boundless=True,
                        fill_value=src_nodata).astype("float32")
        transform = src.window_transform(window)
        valid = data != src_nodata
        print(f"  Ausschnitt: {data.shape[1]} x {data.shape[0]} px, "
              f"{int(valid.sum())} gueltige Gletscherpixel "
              f"({100 * valid.mean():.1f} %)")
        if not valid.any():
            raise ValueError(
                "Keine gueltigen Gletscherpixel im Ausschnitt - CRS/Bounds "
                "der Reinthaler-Quelle pruefen.")
        # Einheitlicher interner NoData-Wert.
        data[~valid] = config.LIA_SRC_NODATA
        return data, transform, src.crs


def resample_cubic(data, src_transform, src_crs, profile, dst_transform,
                   dst_crs, width, height) -> tuple:
    """Reprojiziere Werte (cubic-spline) und Maske aufs Zielraster.

    Das Werte-Array wird vor dem Resampling NoData-gefuellt, damit der
    Cubic-Kernel am Gletscherrand nicht ueber NoData schwingt. Die
    Gueltigkeitsmaske wird separat (bilinear) resampelt und
    schwellwertet, um die echte Gletscherausdehnung sauber zurueckzuholen.

    Args:
        data: Zugeschnittenes Quell-Array (NoData == LIA_SRC_NODATA).
        src_transform: Affine-Transformation des Ausschnitts.
        src_crs: CRS der Quelle.
        profile: Profil-Vorlage (vom modernen DEM).
        dst_transform: Ziel-Transformation.
        dst_crs: Ziel-CRS.
        width: Zielbreite in Pixeln.
        height: Zielhoehe in Pixeln.

    Returns:
        tuple: (surface, mask) mit der interpolierten Gletscheroberflaeche
        (float32) und der booleschen Gletschermaske aufs Zielraster.
    """
    nodata = config.LIA_SRC_NODATA
    valid = (data != nodata).astype(np.uint8)
    # 1) NoData glatt fuellen, damit Cubic durchgehend Werte hat.
    filled = fillnodata(data.copy(), mask=valid,
                        max_search_distance=FILL_MAX_DISTANCE)
    # Restliche Luecken (ausserhalb Suchdistanz) auf Mittel setzen, damit
    # kein Sentinel in die Interpolation gelangt.
    still_nodata = filled == nodata
    if still_nodata.any():
        filled[still_nodata] = float(filled[~still_nodata].mean())

    # 2) Werte per Cubic-Spline aufs Zielraster.
    surface = np.zeros((height, width), dtype="float32")
    reproject(
        source=filled,
        destination=surface,
        src_transform=src_transform,
        src_crs=src_crs,
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        resampling=Resampling.cubic_spline,
    )

    # 3) Maske separat (bilinear) resampeln -> weiche, aber saubere Kante.
    mask_f = np.zeros((height, width), dtype="float32")
    reproject(
        source=valid.astype("float32"),
        destination=mask_f,
        src_transform=src_transform,
        src_crs=src_crs,
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        resampling=Resampling.bilinear,
    )
    mask = mask_f >= config.LIA_MASK_THRESHOLD
    print(f"  Gletschermaske auf Zielraster: {int(mask.sum())} px "
          f"({100 * mask.mean():.1f} %)")
    return surface, mask


def smooth_masked(surface, mask, iterations: int, sigma: float) -> np.ndarray:
    """Glaette die Oberflaeche innerhalb der Maske (Normalized Convolution).

    Durch die Normalisierung mit der geglaetteten Maske bleibt die
    Gletscherkante ortsfest und blutet nicht in die NoData-Umgebung aus.

    Args:
        surface: Interpolierte Gletscheroberflaeche (float32).
        mask: Boolesche Gletschermaske.
        iterations: Anzahl Glaettungsdurchlaeufe (0 = keine Glaettung).
        sigma: Gauss-Sigma in Zielpixeln (5 m).

    Returns:
        np.ndarray: Geglaettete Oberflaeche (float32), ausserhalb der
        Maske unveraendert.
    """
    if iterations <= 0:
        return surface
    m = mask.astype("float32")
    result = surface.copy()
    for _ in range(iterations):
        num = gaussian_filter(result * m, sigma=sigma)
        den = gaussian_filter(m, sigma=sigma)
        smoothed = np.where(den > 0, num / den, result)
        # Nur innerhalb der Maske uebernehmen.
        result = np.where(mask, smoothed, result)
    return result.astype("float32")


def feather_weight(mask, radius_px: float) -> np.ndarray:
    """Berechne ein nach innen gefedertes Gewicht [0..1] fuer die Maske.

    Das Gewicht ist 0 an (und ausserhalb) der Maskenkante und steigt ueber
    ``radius_px`` glatt (Smoothstep) auf 1 im Inneren. So laeuft die
    Eisdicke am Rand auf 0 aus statt hart abzubrechen.

    Args:
        mask: Boolesche Gletschermaske.
        radius_px: Feather-Radius in Zielpixeln.

    Returns:
        np.ndarray: Gewichts-Array (float32) in [0, 1].
    """
    if radius_px <= 0:
        return mask.astype("float32")
    # Distanz jedes Gletscherpixels zur naechsten Nicht-Gletscherzelle.
    dist_in = distance_transform_edt(mask)
    t = np.clip(dist_in / radius_px, 0.0, 1.0)
    # Smoothstep -> C1-stetiger Uebergang an beiden Enden der Rampe.
    weight = t * t * (3.0 - 2.0 * t)
    return weight.astype("float32")


def build_composite(modern, surface, weight, mask, nodata: float
                    ) -> np.ndarray:
    """Lege die Gletscheroberflaeche gefedert als Eiskoerper aufs DEM.

    Innerhalb der Maske wird die (nie negative) Eisdicke mit dem
    Feather-Gewicht skaliert und auf das Terrain addiert:
    ``out = terrain + weight * max(0, surface - terrain)``. Der Rand geht
    damit stufenlos ins moderne DEM ueber.

    Args:
        modern: Modernes Hoehen-Array (float32, NoData == nodata).
        surface: Interpolierte Gletscheroberflaeche (float32).
        weight: Feather-Gewicht [0..1] (float32).
        mask: Boolesche Gletschermaske (fuer NoData-Faelle/Statistik).
        nodata: NoData-/Sentinel-Wert des modernen DEM.

    Returns:
        np.ndarray: Composite-Hoehen (float32). Ausserhalb der Maske
        identisch zum modernen DEM; innen gefederte Eisauflage.
    """
    out = modern.copy()
    modern_valid = modern != nodata
    thickness = np.maximum(surface - modern, 0.0)
    blended = modern + weight * thickness
    out = np.where(modern_valid, blended, out)
    # Wo das moderne DEM NoData ist, aber Gletscher vorliegt: rohe
    # Oberflaeche einsetzen (kein Terrain zum Federn vorhanden).
    out = np.where(mask & ~modern_valid, surface, out)

    stat = np.where(mask & modern_valid, surface - modern, np.nan)
    if np.isfinite(stat).any():
        print(f"  Eisdicke (Gletscher-Terrain): "
              f"min={np.nanmin(stat):.1f} m, "
              f"max={np.nanmax(stat):.1f} m, "
              f"mittel={np.nanmean(stat):.1f} m")
    return out.astype("float32")


def main() -> None:
    """Baue das weiche 1850-Composite und schreibe es nach DEM_LIA."""
    if not config.REINTHALER_LIA_SRC.exists():
        raise FileNotFoundError(
            f"Reinthaler-Quelle fehlt: {config.REINTHALER_LIA_SRC}")

    print(f"Modernes Ziel-DEM: {config.DEM_MODERN.name}")
    profile, dst_transform, dst_crs, width, height, modern = \
        read_modern_grid()
    # array_bounds liefert (left, bottom, right, top) = (minx, miny, maxx,
    # maxy) -> passt direkt fuer transform_bounds/from_bounds.
    dst_bounds = array_bounds(height, width, dst_transform)
    print(f"  Zielraster: {width} x {height} px, CRS={dst_crs}")

    print("\nSchritt 1/2: Reinthaler zuschneiden")
    data, src_transform, src_crs = clip_source_to(
        dst_crs, dst_bounds, config.LIA_CLIP_BUFFER)

    print("\nSchritt 2/2: Cubic-Spline aufs 5-m-Raster + Composite")
    surface, mask = resample_cubic(
        data, src_transform, src_crs, profile, dst_transform, dst_crs,
        width, height)
    surface = smooth_masked(surface, mask, config.LIA_SMOOTH_ITERATIONS,
                            config.LIA_SMOOTH_SIGMA)
    pixel_size = abs(dst_transform.a)
    radius_px = config.LIA_FEATHER_RADIUS / pixel_size
    print(f"  Feathering: {config.LIA_FEATHER_RADIUS:.0f} m "
          f"({radius_px:.1f} px)")
    weight = feather_weight(mask, radius_px)
    composite = build_composite(modern, surface, weight, mask,
                                config.MODERN_NODATA)

    profile.update(dtype="float32", count=1, nodata=config.MODERN_NODATA)
    with rasterio.open(config.DEM_LIA, "w", **profile) as dst:
        dst.write(composite, 1)
    print(f"\nGeschrieben -> {config.DEM_LIA}")
    print("Weiter mit der Pipeline: 01_inspect_dems.py, dann "
          "02_prepare_rasters.py.")


if __name__ == "__main__":
    main()
