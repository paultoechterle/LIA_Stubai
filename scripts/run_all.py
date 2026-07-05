"""Gesamte Datenaufbereitungs-Pipeline in einem Rutsch ausfuehren.

Ruft die Phase-A-Skripte in der richtigen Reihenfolge auf und bricht beim
ersten Fehler ab (Exit-Code != 0). Jeder Schritt laeuft als eigener
Python-Prozess mit demselben Interpreter (sys.executable), damit die
Umgebung (geodata_env) erhalten bleibt.

Reihenfolge:
    00_build_lia_composite.py -> weiches 1850-DEM aus Reinthaler-Quelle
    01_inspect_dems.py        -> Metadaten/Deckungsgleichheit (Report)
    02_prepare_rasters.py     -> Zuschnitt, Reprojektion, NoData fuellen
    03_make_terrainrgb.py     -> Terrain-RGB-Encoding
    03b_make_hillshade.py     -> Hillshade-Overlays
    04_make_tiles.py          -> XYZ-Kacheln
    05_web_meta.py            -> app/meta.json (Kartenmitte/Bounds)
    07_make_pois.py           -> app/pois.geojson (Gipfel & Gletscher)

Ausfuehren (aus dem Projekt-Root oder beliebig):
    python scripts/run_all.py

    # Einzelne Schritte ueberspringen (z. B. das teure Composite):
    python scripts/run_all.py --skip 00 --skip 04
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

# Pipeline-Schritte in Ausfuehrungsreihenfolge. Der Schluessel ist das
# Kuerzel fuer --skip, der Wert der Dateiname im scripts/-Ordner.
STEPS: list = [
    ("00", "00_build_lia_composite.py"),
    ("01", "01_inspect_dems.py"),
    ("02", "02_prepare_rasters.py"),
    ("03", "03_make_terrainrgb.py"),
    ("03b", "03b_make_hillshade.py"),
    ("04", "04_make_tiles.py"),
    ("05", "05_web_meta.py"),
    ("07", "07_make_pois.py"),
]

SCRIPTS_DIR: Path = Path(__file__).resolve().parent


def run_step(name: str, filename: str) -> None:
    """Fuehre einen Pipeline-Schritt als Subprozess aus.

    Args:
        name: Kuerzel des Schritts (z. B. "02").
        filename: Skript-Dateiname im scripts/-Ordner.

    Raises:
        SystemExit: Wenn das Skript mit Exit-Code != 0 endet.
    """
    script = SCRIPTS_DIR / filename
    print(f"\n{'=' * 70}\n[{name}] {filename}\n{'=' * 70}", flush=True)
    start = time.perf_counter()
    result = subprocess.run([sys.executable, str(script)], cwd=SCRIPTS_DIR)
    dauer = time.perf_counter() - start
    if result.returncode != 0:
        print(f"\nABBRUCH: [{name}] {filename} endete mit Exit-Code "
              f"{result.returncode} (nach {dauer:.1f} s).")
        sys.exit(result.returncode)
    print(f"[{name}] fertig in {dauer:.1f} s.")


def main() -> None:
    """Parse Argumente und fuehre alle (nicht uebersprungenen) Schritte aus."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip", action="append", default=[], metavar="NAME",
                        help="Schritt-Kuerzel ueberspringen (mehrfach "
                             "moeglich), z. B. --skip 00")
    args = parser.parse_args()
    skip = set(args.skip)

    gesamt = time.perf_counter()
    for name, filename in STEPS:
        if name in skip:
            print(f"\n[{name}] {filename} uebersprungen (--skip).")
            continue
        run_step(name, filename)
    print(f"\n{'=' * 70}\nPipeline komplett in "
          f"{time.perf_counter() - gesamt:.1f} s.\n{'=' * 70}")


if __name__ == "__main__":
    main()
