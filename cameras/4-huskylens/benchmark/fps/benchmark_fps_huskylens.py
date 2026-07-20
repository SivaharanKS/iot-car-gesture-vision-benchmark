"""
Benchmark - Metric 2: THROUGHPUT / FPS (HuskyLens solution)
===========================================================
Measures the rate at which the PC can read a new result from the
HuskyLens (hl.learned() request loop), adapted from the webcam version
(cap.read() + MediaPipe).

The instantaneous FPS is recorded on each request (1 / loop duration) and
classified according to whether an active gesture is detected (ID 1 to 4)
or not (ID 5/neutral or no detection), in order to distinguish:
  - FPS with an active gesture: real gesture-control use case
  - FPS with no gesture (neutral): reference

The measurement lasts DUREE_MESURE seconds. The first few seconds (serial
connection warm-up) are excluded from the statistics.

Outputs:
  - a CSV with the FPS of each request;
  - an Excel (.xlsx) with the data, the statistics, and charts.
"""

import time
import csv
import statistics
from huskylib import HuskyLensLibrary
from openpyxl import Workbook
from openpyxl.chart import LineChart, BarChart, Reference
from openpyxl.styles import Font, PatternFill, Alignment

# ----------------------------------------------------------------
# Parameters to adapt
# ----------------------------------------------------------------
COM_HUSKY = "COM25"   # HuskyLens serial port

DUREE_MESURE = 30.0   # measurement duration in seconds (steady state)
WARMUP_SEC = 3.0      # warm-up duration ignored at the start (seconds)

ID_NEUTRE = 5         # ID of the neutral class (see huskylens_training.py)

TIMESTAMP = time.strftime('%Y%m%d_%H%M%S')
CSV_FILENAME = f"benchmark_fps_huskylens_{TIMESTAMP}.csv"
XLSX_FILENAME = f"benchmark_fps_huskylens_{TIMESTAMP}.xlsx"


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
    print(f"  {nom} ({stats['n']} requests):")
    print(f"    Mean FPS     : {stats['moyenne']:.2f}")
    print(f"    Median FPS   : {stats['mediane']:.2f}")
    print(f"    Std. dev.    : {stats['ecart_type']:.2f}")
    print(f"    Min FPS      : {stats['min']:.2f}")
    print(f"    Max FPS      : {stats['max']:.2f}")


# ======================================================================
# FPS measurement
# ======================================================================

def mesurer_fps():
    print("\n=== THROUGHPUT (FPS) MEASUREMENT - HuskyLens ===")
    print(f"Duration: {DUREE_MESURE:.0f} s (including {WARMUP_SEC:.0f} s of warm-up, ignored).")
    print("Alternate between 'active gesture' and 'neutral position' to measure both cases.\n")

    try:
        hl = HuskyLensLibrary("SERIAL", COM_HUSKY)
        print(hl.knock())
        hl.algorthim("ALGORITHM_OBJECT_CLASSIFICATION")
    except Exception as e:
        print(f"Connection error to the HuskyLens ({COM_HUSKY}): {e}")
        return []

    # Each entry: (relative_time_s, instantaneous_fps, active_gesture 0/1, warmup 0/1)
    donnees = []

    t_start = time.perf_counter()
    t_prev = t_start

    while True:
        try:
            objet = hl.learned()
        except Exception:
            objet = None

        detected_id = getattr(objet, "ID", None) if objet else None
        geste_actif = 1 if (detected_id is not None and detected_id != ID_NEUTRE) else 0

        t_now = time.perf_counter()
        dt = t_now - t_prev
        t_prev = t_now
        fps = (1.0 / dt) if dt > 0 else 0.0

        t_rel = t_now - t_start
        warmup = 1 if t_rel < WARMUP_SEC else 0
        donnees.append((t_rel, fps, geste_actif, warmup))

        idx = len(donnees)
        if idx % 50 == 0:
            phase = "WARM-UP" if warmup else "MEASURE"
            print(f"  {phase}  t={t_rel:.1f}s / {DUREE_MESURE:.0f}s  "
                  f"FPS={fps:.1f}  Active gesture={'YES' if geste_actif else 'no'}")

        if t_rel >= DUREE_MESURE:
            break

    return donnees


# ======================================================================
# CSV and Excel export
# ======================================================================

def exporter_csv(donnees):
    with open(CSV_FILENAME, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["time_s", "fps", "active_gesture", "warmup"])
        for t_rel, fps, actif, warmup in donnees:
            writer.writerow([f"{t_rel:.3f}", f"{fps:.2f}", actif, warmup])
    print(f"\n  Raw data (CSV): {CSV_FILENAME}")


def exporter_excel(donnees_utiles, stats_global, stats_actif, stats_neutre):
    wb = Workbook()

    entete_fill = PatternFill("solid", start_color="4472C4")
    entete_font = Font(bold=True, color="FFFFFF")
    titre_font = Font(bold=True, size=13)

    ws = wb.active
    ws.title = "Data"
    ws["A1"] = "HuskyLens throughput (FPS) measurement - steady state (warm-up excluded)"
    ws["A1"].font = titre_font

    entetes = ["Request", "Time (s)", "FPS", "Active gesture"]
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

    ws_stats = wb.create_sheet("Statistics")
    ws_stats["A1"] = "HuskyLens throughput (FPS) statistics"
    ws_stats["A1"].font = titre_font

    entetes_s = ["Metric", "Global", "Active gesture", "Neutral"]
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
            round(stats_neutre[cle], 2) if stats_neutre else None,
        )

    lignes = [
        ligne_stat("Number of requests", "n"),
        ligne_stat("Mean FPS", "moyenne"),
        ligne_stat("Median FPS", "mediane"),
        ligne_stat("Std. deviation", "ecart_type"),
        ligne_stat("Min FPS", "min"),
        ligne_stat("Max FPS", "max"),
    ]
    for r, (nom, g, a, ne) in enumerate(lignes, start=4):
        ws_stats.cell(row=r, column=1, value=nom).font = Font(bold=True)
        ws_stats.cell(row=r, column=2, value=g)
        ws_stats.cell(row=r, column=3, value=a)
        ws_stats.cell(row=r, column=4, value=ne)

    for col in ("A", "B", "C", "D"):
        ws_stats.column_dimensions[col].width = 18

    # --- Chart 1: instantaneous FPS over time (single curve) ---
    chart1 = LineChart()
    chart1.title = "HuskyLens throughput (FPS) over the requests"
    chart1.x_axis.title = "Request"
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

    # --- Chart 2: bar comparison of mean FPS (global / active / neutral) ---
    chart2 = BarChart()
    chart2.type = "col"
    chart2.title = "Mean FPS depending on active gesture presence"
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
    print(" THROUGHPUT (FPS) BENCHMARK - HuskyLens solution")
    print("=" * 55)

    donnees = mesurer_fps()
    if not donnees:
        print("No data measured.")
        return

    donnees_utiles = [d for d in donnees if d[3] == 0]

    fps_global = [d[1] for d in donnees_utiles]
    fps_actif = [d[1] for d in donnees_utiles if d[2] == 1]
    fps_neutre = [d[1] for d in donnees_utiles if d[2] == 0]

    stats_global = calculer_stats(fps_global)
    stats_actif = calculer_stats(fps_actif)
    stats_neutre = calculer_stats(fps_neutre)

    print("\n" + "=" * 55)
    print(" RESULTS (warm-up excluded)")
    print("=" * 55)
    afficher_stats("Global FPS", stats_global)
    print()
    afficher_stats("FPS active gesture", stats_actif)
    print()
    afficher_stats("FPS neutral", stats_neutre)

    exporter_csv(donnees)
    if stats_global:
        exporter_excel(donnees_utiles, stats_global, stats_actif, stats_neutre)


if __name__ == "__main__":
    main()
