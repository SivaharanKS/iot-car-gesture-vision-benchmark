"""
Benchmark - Metric 2: THROUGHPUT / FPS (Nicla Vision solution)
================================================================
Instantaneous FPS = 1 / interval between two consecutive
"DETECTED:<label>" lines pushed by the Nicla Vision (inference runs
on-device, results are pushed continuously, not on request).

Each interval is classified as "gesture active" (label != "none") or
"no gesture" (label == "none"), to distinguish real-use throughput
from idle throughput.

Measurement is time-bounded (DUREE_MESURE) and stops early with a
warning if the serial connection drops (known ml.utils.NMS crash).

Requires main.py running autonomously on the Nicla Vision.
"""

import serial
import time
import csv
import statistics
from openpyxl import Workbook
from openpyxl.chart import LineChart, BarChart, Reference
from openpyxl.styles import Font, PatternFill, Alignment

# ----------------------------------------------------------------
# Parameters to adapt
# ----------------------------------------------------------------
COM_NICLA = "COM31"

DUREE_MESURE = 30.0   # measurement duration in seconds (steady state)
WARMUP_SEC = 3.0       # warm-up duration ignored at the start (seconds)

TIMESTAMP = time.strftime('%Y%m%d_%H%M%S')
CSV_FILENAME = f"benchmark_fps_nicla_{TIMESTAMP}.csv"
XLSX_FILENAME = f"benchmark_fps_nicla_{TIMESTAMP}.xlsx"


def calculer_stats(valeurs):
    if not valeurs:
        return None
    return {
        "n": len(valeurs),
        "moyenne": statistics.mean(valeurs),
        "mediane": statistics.median(valeurs),
        "ecart_type": statistics.stdev(valeurs) if len(valeurs) > 1 else 0.0,
        "min": min(valeurs),
        "max": max(valeurs),
    }


def afficher_stats(nom, stats):
    if stats is None:
        print(f"  {nom}: no measurements.")
        return
    print(f"  {nom} ({stats['n']} frames):")
    print(f"    Mean FPS     : {stats['moyenne']:.2f}")
    print(f"    Median FPS   : {stats['mediane']:.2f}")
    print(f"    Std. dev.    : {stats['ecart_type']:.2f}")
    print(f"    Min FPS      : {stats['min']:.2f}")
    print(f"    Max FPS      : {stats['max']:.2f}")


# ======================================================================
# FPS measurement
# ======================================================================

def mesurer_fps():
    print("\n=== THROUGHPUT (FPS) MEASUREMENT ===")
    print(f"Duration: {DUREE_MESURE:.0f} s (including {WARMUP_SEC:.0f} s of warm-up, ignored).")
    print("Alternate between gestures and no gesture to measure both cases.\n")

    try:
        ser_nicla = serial.Serial(COM_NICLA, 115200, timeout=1)
        print(f"Connected to the Nicla Vision on {COM_NICLA}")
    except serial.SerialException as e:
        print(f"Serial connection error (Nicla Vision): {e}")
        return []

    # Each entry: (relative_time_s, instantaneous_fps, gesture_active 0/1, warmup 0/1)
    donnees = []

    t_start = time.monotonic()
    t_prev = None

    while time.monotonic() - t_start < DUREE_MESURE:
        try:
            ligne = ser_nicla.readline().decode(errors="ignore").strip()
        except Exception as e:
            print(f"Serial read error (Nicla Vision disconnected?): {e}")
            break

        if not ligne.startswith("DETECTED:"):
            continue

        label = ligne.split(":")[1] if ":" in ligne else "none"
        t_now = time.monotonic()

        if t_prev is not None:
            dt = t_now - t_prev
            fps = (1.0 / dt) if dt > 0 else 0.0
            t_rel = t_now - t_start
            warmup = 1 if t_rel < WARMUP_SEC else 0
            gesture_active = 1 if label != "none" else 0
            donnees.append((t_rel, fps, gesture_active, warmup))

        t_prev = t_now

    ser_nicla.close()

    if time.monotonic() - t_start < DUREE_MESURE - 1.0:
        print(f"Warning: measurement stopped early at "
              f"{time.monotonic() - t_start:.1f}/{DUREE_MESURE:.0f} s "
              f"(camera may have crashed or stopped responding).")

    return donnees


# ======================================================================
# CSV and Excel export
# ======================================================================

def exporter_csv(donnees):
    with open(CSV_FILENAME, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["time_s", "fps", "gesture_active", "warmup"])
        for t_rel, fps, actif, warmup in donnees:
            writer.writerow([f"{t_rel:.3f}", f"{fps:.2f}", actif, warmup])
    print(f"\n  Raw data (CSV): {CSV_FILENAME}")


def exporter_excel(donnees_utiles, stats_global, stats_actif, stats_inactif):
    """Creates an Excel file with the data, statistics, and charts."""
    wb = Workbook()

    entete_fill = PatternFill("solid", start_color="4472C4")
    entete_font = Font(bold=True, color="FFFFFF")
    titre_font = Font(bold=True, size=13)

    # --- Sheet 1: Data ---
    ws = wb.active
    ws.title = "Data"
    ws["A1"] = "Throughput (FPS) measurement - steady state (warm-up excluded)"
    ws["A1"].font = titre_font

    entetes = ["Frame", "Time (s)", "FPS", "Gesture active"]
    for col, txt in enumerate(entetes, start=1):
        c = ws.cell(row=3, column=col, value=txt)
        c.fill = entete_fill
        c.font = entete_font
        c.alignment = Alignment(horizontal="center")

    for i, (t_rel, fps, actif, _warmup) in enumerate(donnees_utiles):
        ws.cell(row=4 + i, column=1, value=i + 1)
        ws.cell(row=4 + i, column=2, value=round(t_rel, 3))
        ws.cell(row=4 + i, column=3, value=round(fps, 2))
        ws.cell(row=4 + i, column=4, value=actif)

    for col, w in (("A", 10), ("B", 12), ("C", 10), ("D", 14)):
        ws.column_dimensions[col].width = w

    n = len(donnees_utiles)

    # --- Sheet 2: Statistics ---
    ws_stats = wb.create_sheet("Statistics")
    ws_stats["A1"] = "Throughput (FPS) statistics - Nicla Vision"
    ws_stats["A1"].font = titre_font

    entetes_s = ["Metric", "Global", "Gesture active", "No gesture"]
    for col, txt in enumerate(entetes_s, start=1):
        c = ws_stats.cell(row=3, column=col, value=txt)
        c.fill = entete_fill
        c.font = entete_font
        c.alignment = Alignment(horizontal="center")

    def ligne_stat(nom, cle):
        return (
            nom,
            round(stats_global[cle], 2) if stats_global else None,
            round(stats_actif[cle], 2) if stats_actif else None,
            round(stats_inactif[cle], 2) if stats_inactif else None,
        )

    lignes = [
        ligne_stat("Number of frames", "n"),
        ligne_stat("Mean FPS", "moyenne"),
        ligne_stat("Median FPS", "mediane"),
        ligne_stat("Std. deviation", "ecart_type"),
        ligne_stat("Min FPS", "min"),
        ligne_stat("Max FPS", "max"),
    ]
    for r, (nom, g, a, i_) in enumerate(lignes, start=4):
        ws_stats.cell(row=r, column=1, value=nom).font = Font(bold=True)
        ws_stats.cell(row=r, column=2, value=g)
        ws_stats.cell(row=r, column=3, value=a)
        ws_stats.cell(row=r, column=4, value=i_)

    for col in ("A", "B", "C", "D"):
        ws_stats.column_dimensions[col].width = 18

    if n > 0:
        # --- Chart 1: instantaneous FPS over time ---
        chart1 = LineChart()
        chart1.title = "Throughput (FPS) over the frames - Nicla Vision"
        chart1.x_axis.title = "Frame"
        chart1.y_axis.title = "FPS"
        chart1.height = 8
        chart1.width = 18
        chart1.style = 12
        data_ref = Reference(ws, min_col=3, max_col=3, min_row=3, max_row=3 + n)
        chart1.add_data(data_ref, titles_from_data=True)
        cats1 = Reference(ws, min_col=1, min_row=4, max_row=3 + n)
        chart1.set_categories(cats1)
        chart1.series[0].graphicalProperties.line.width = 15000
        ws.add_chart(chart1, "F3")

        # --- Chart 2: bar comparison of mean FPS ---
        chart2 = BarChart()
        chart2.type = "col"
        chart2.title = "Mean FPS depending on gesture presence"
        chart2.y_axis.title = "FPS"
        chart2.height = 8
        chart2.width = 12
        chart2.legend = None
        vals = Reference(ws_stats, min_col=2, max_col=4, min_row=5, max_row=5)
        cats = Reference(ws_stats, min_col=2, max_col=4, min_row=3, max_row=3)
        chart2.add_data(vals, from_rows=True)
        chart2.set_categories(cats)
        ws_stats.add_chart(chart2, "F3")

    wb.save(XLSX_FILENAME)
    print(f"  Excel file (data + charts): {XLSX_FILENAME}")


# ======================================================================
# Main program
# ======================================================================

def main():
    print("=" * 55)
    print(" THROUGHPUT (FPS) BENCHMARK - Nicla Vision solution")
    print("=" * 55)

    donnees = mesurer_fps()
    if not donnees:
        print("No data measured.")
        return

    donnees_utiles = [d for d in donnees if d[3] == 0]

    fps_global = [d[1] for d in donnees_utiles]
    fps_actif = [d[1] for d in donnees_utiles if d[2] == 1]
    fps_inactif = [d[1] for d in donnees_utiles if d[2] == 0]

    stats_global = calculer_stats(fps_global)
    stats_actif = calculer_stats(fps_actif)
    stats_inactif = calculer_stats(fps_inactif)

    print("\n" + "=" * 55)
    print(" RESULTS (warm-up excluded)")
    print("=" * 55)
    afficher_stats("Global FPS", stats_global)
    print()
    afficher_stats("FPS with gesture", stats_actif)
    print()
    afficher_stats("FPS without gesture", stats_inactif)

    exporter_csv(donnees)
    if stats_global:
        exporter_excel(donnees_utiles, stats_global, stats_actif, stats_inactif)


if __name__ == "__main__":
    main()