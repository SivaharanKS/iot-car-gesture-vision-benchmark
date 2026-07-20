"""
Benchmark - Metric 1: LATENCY (HuskyLens solution)
=======================================================
Measures latency broken down into two segments, adapted to the HuskyLens
architecture (processing entirely embedded in the camera):

  - Segment A (HuskyLens query): response time to a serial request sent
    to the HuskyLens (hl.learned()), measured on the PC. This segment
    replaces the "vision" segment of the WebCam solution, since the
    HuskyLens has already determined the gesture internally.
  - Segment B+C (communication): PC -> robot -> ACK serial round-trip
    (ping/pong), strictly identical to the mechanism used for the
    WebCam solution (code.py on the robot side was not modified).

Prerequisite on the robot side: code.py must reply {"pong": N} upon
receiving {"ping": N} (already in place, unchanged since the WebCam
solution).

Two successive phases:
  Phase 1: N measurements of segment A (HuskyLens queries)
  Phase 2: N measurements of segment B+C (automatic, ping/pong)

The first measurements (warm-up) are ignored in the statistics.

Outputs:
  - a CSV with all the raw measurements;
  - an Excel (.xlsx) with the data split by segment, the statistics
    (mean, median, standard deviation, min, max), and charts.
"""

import time
import json
import csv
import serial
import statistics
from huskylib import HuskyLensLibrary
from openpyxl import Workbook
from openpyxl.chart import LineChart, BarChart, Reference
from openpyxl.styles import Font, PatternFill, Alignment

# ----------------------------------------------------------------
# Parameters to adapt
# ----------------------------------------------------------------
COM_HUSKY = "COM25"   # HuskyLens serial port
COM_ROBOT = "COM22"   # RP2040 robot serial port
BAUDRATE_ROBOT = 115200

N_HUSKY = 100        # number of measurements for segment A (HuskyLens queries)
N_PINGPONG = 100     # number of measurements for segment B+C (communication)
PING_TIMEOUT = 1.0   # max wait time for a pong (seconds)

# Number of initial measurements to IGNORE (warm-up)
WARMUP_HUSKY = 15
WARMUP_PINGPONG = 5

TIMESTAMP = time.strftime('%Y%m%d_%H%M%S')
CSV_FILENAME = f"benchmark_latence_huskylens_{TIMESTAMP}.csv"
XLSX_FILENAME = f"benchmark_latence_huskylens_{TIMESTAMP}.xlsx"


def calculer_stats(valeurs_ms):
    """Returns a dictionary of statistics for a list of measurements (ms)."""
    if not valeurs_ms:
        return None
    return {
        "n": len(valeurs_ms),
        "moyenne": statistics.mean(valeurs_ms),
        "mediane": statistics.median(valeurs_ms),
        "ecart_type": statistics.stdev(valeurs_ms) if len(valeurs_ms) > 1 else 0.0,
        "min": min(valeurs_ms),
        "max": max(valeurs_ms),
    }


def afficher_stats(nom, stats):
    if stats is None:
        print(f"  {nom}: no measurements.")
        return
    print(f"  {nom} ({stats['n']} measurements after warm-up):")
    print(f"    Mean       : {stats['moyenne']:.2f} ms")
    print(f"    Median     : {stats['mediane']:.2f} ms")
    print(f"    Std. dev.  : {stats['ecart_type']:.2f} ms")
    print(f"    Min        : {stats['min']:.2f} ms")
    print(f"    Max        : {stats['max']:.2f} ms")


# ======================================================================
# PHASE 1: Segment A (HuskyLens query)
# ======================================================================

def mesurer_segment_huskylens():
    print("\n=== PHASE 1: Segment A (HuskyLens query) ===")
    print(f"Target: {N_HUSKY} measurements (including {WARMUP_HUSKY} warm-up ones, ignored).")
    print("Keep a steady gesture in front of the camera during this phase.\n")

    try:
        hl = HuskyLensLibrary("SERIAL", COM_HUSKY)
        print(hl.knock())
        hl.algorthim("ALGORITHM_OBJECT_CLASSIFICATION")
    except Exception as e:
        print(f"Connection error to the HuskyLens ({COM_HUSKY}): {e}")
        return []

    mesures_ms = []

    while len(mesures_ms) < N_HUSKY:
        t_debut = time.perf_counter()
        try:
            hl.learned()
        except Exception:
            continue
        t_fin = time.perf_counter()

        latence_ms = (t_fin - t_debut) * 1000.0
        mesures_ms.append(latence_ms)

        idx = len(mesures_ms)
        phase_txt = "WARM-UP" if idx <= WARMUP_HUSKY else "MEASURE"
        if idx % 10 == 0 or idx <= WARMUP_HUSKY:
            print(f"  {phase_txt} {idx}/{N_HUSKY}: {latence_ms:.2f} ms")

    return mesures_ms


# ======================================================================
# PHASE 2: Segment B+C (communication) - serial ping/pong
# (identical to the mechanism used for the WebCam solution)
# ======================================================================

def mesurer_segment_communication():
    print("\n=== PHASE 2: Segment B+C (serial communication) ===")
    print(f"Target: {N_PINGPONG} ping/pong measurements (automatic).\n")

    try:
        ser = serial.Serial(COM_ROBOT, BAUDRATE_ROBOT, timeout=0)
        print(f"Connected to the robot on {COM_ROBOT}")
    except serial.SerialException as e:
        print(f"Serial connection error: {e}")
        return []

    # Software restart of the robot to start from a clean state
    time.sleep(0.3)
    ser.write(b'\x03')
    time.sleep(0.2)
    ser.write(b'\x02')
    time.sleep(0.2)
    ser.write(b'\x04')
    print("Restarting the robot, waiting for code.py to start...")

    boot_deadline = time.monotonic() + 6.0
    while time.monotonic() < boot_deadline:
        if ser.in_waiting:
            line = ser.readline().decode(errors="ignore").strip()
            if line:
                print(f"[Boot] {line}")
        time.sleep(0.02)

    time.sleep(0.5)
    while ser.in_waiting:
        ser.readline()

    mesures_ms = []
    perdus = 0

    for i in range(N_PINGPONG):
        ping_id = i
        message = json.dumps({"ping": ping_id}) + "\n"

        while ser.in_waiting:
            ser.readline()

        t_envoi = time.perf_counter()
        ser.write(message.encode())

        pong_recu = False
        deadline = time.perf_counter() + PING_TIMEOUT
        while time.perf_counter() < deadline:
            if ser.in_waiting:
                line = ser.readline().decode(errors="ignore").strip()
                if not line:
                    continue

                if line.startswith("b'") and line.endswith("'"):
                    line = line[2:-1]
                elif line.startswith('b"') and line.endswith('"'):
                    line = line[2:-1]

                if '"pong"' in line:
                    try:
                        data = json.loads(line)
                    except Exception:
                        continue
                    if data.get("pong") == ping_id:
                        t_reception = time.perf_counter()
                        latence_ms = (t_reception - t_envoi) * 1000.0
                        mesures_ms.append(latence_ms)
                        pong_recu = True
                        break
            time.sleep(0.001)

        if not pong_recu:
            perdus += 1

        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/{N_PINGPONG} pings sent "
                  f"({len(mesures_ms)} pongs received, {perdus} lost)")

        time.sleep(0.02)

    ser.close()
    if perdus:
        print(f"  Warning: {perdus} ping(s) with no reply (timeout).")
    return mesures_ms


# ======================================================================
# CSV and Excel export
# ======================================================================

def exporter_csv(mesures_husky, mesures_comm):
    with open(CSV_FILENAME, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["segment", "measurement_num", "warmup", "latency_ms"])
        for i, v in enumerate(mesures_husky):
            warmup = 1 if i < WARMUP_HUSKY else 0
            writer.writerow(["huskylens_A", i, warmup, f"{v:.3f}"])
        for i, v in enumerate(mesures_comm):
            warmup = 1 if i < WARMUP_PINGPONG else 0
            writer.writerow(["communication_BC", i, warmup, f"{v:.3f}"])
    print(f"\n  Raw data (CSV): {CSV_FILENAME}")


def exporter_excel(husky_utiles, comm_utiles, stats_a, stats_bc):
    wb = Workbook()

    entete_fill = PatternFill("solid", start_color="4472C4")
    entete_font = Font(bold=True, color="FFFFFF")
    titre_font = Font(bold=True, size=13)

    ws = wb.active
    ws.title = "Data"
    ws["A1"] = "HuskyLens latency measurements (after warm-up)"
    ws["A1"].font = titre_font

    ws["A3"] = "Measurement"
    ws["B3"] = "Segment A - HuskyLens (ms)"
    ws["D3"] = "Measurement"
    ws["E3"] = "Segment B+C - comm (ms)"
    for cell in ("A3", "B3", "D3", "E3"):
        ws[cell].fill = entete_fill
        ws[cell].font = entete_font
        ws[cell].alignment = Alignment(horizontal="center")

    for i, v in enumerate(husky_utiles):
        ws.cell(row=4 + i, column=1, value=i + 1)
        ws.cell(row=4 + i, column=2, value=round(v, 3))
    for i, v in enumerate(comm_utiles):
        ws.cell(row=4 + i, column=4, value=i + 1)
        ws.cell(row=4 + i, column=5, value=round(v, 3))

    ws.column_dimensions["A"].width = 10
    ws.column_dimensions["B"].width = 24
    ws.column_dimensions["D"].width = 10
    ws.column_dimensions["E"].width = 22

    ws_stats = wb.create_sheet("Statistics")
    ws_stats["A1"] = "HuskyLens latency statistics"
    ws_stats["A1"].font = titre_font

    entetes = ["Metric", "Segment A - HuskyLens (ms)", "Segment B+C - comm (ms)"]
    for col, txt in enumerate(entetes, start=1):
        c = ws_stats.cell(row=3, column=col, value=txt)
        c.fill = entete_fill
        c.font = entete_font
        c.alignment = Alignment(horizontal="center")

    lignes = [
        ("Number of measurements", stats_a["n"], stats_bc["n"]),
        ("Mean", round(stats_a["moyenne"], 2), round(stats_bc["moyenne"], 2)),
        ("Median", round(stats_a["mediane"], 2), round(stats_bc["mediane"], 2)),
        ("Std. deviation", round(stats_a["ecart_type"], 2), round(stats_bc["ecart_type"], 2)),
        ("Minimum", round(stats_a["min"], 2), round(stats_bc["min"], 2)),
        ("Maximum", round(stats_a["max"], 2), round(stats_bc["max"], 2)),
    ]
    for r, (nom, va, vbc) in enumerate(lignes, start=4):
        ws_stats.cell(row=r, column=1, value=nom).font = Font(bold=True)
        ws_stats.cell(row=r, column=2, value=va)
        ws_stats.cell(row=r, column=3, value=vbc)

    r_total = 4 + len(lignes) + 1
    ws_stats.cell(row=r_total, column=1, value="Total latency (means)").font = Font(bold=True)
    ws_stats.cell(row=r_total, column=2, value="=B5+C5")

    for col in ("A", "B", "C"):
        ws_stats.column_dimensions[col].width = 28

    chart1 = LineChart()
    chart1.title = "Segment A (HuskyLens) - latency per measurement"
    chart1.x_axis.title = "Measurement"
    chart1.y_axis.title = "Latency (ms)"
    chart1.height = 8
    chart1.width = 16
    chart1.style = 12
    data_ref = Reference(ws, min_col=2, max_col=2, min_row=3, max_row=3 + len(husky_utiles))
    chart1.add_data(data_ref, titles_from_data=True)
    cats1 = Reference(ws, min_col=1, min_row=4, max_row=3 + len(husky_utiles))
    chart1.set_categories(cats1)
    chart1.series[0].graphicalProperties.line.width = 15000
    ws.add_chart(chart1, "G3")

    chart2 = LineChart()
    chart2.title = "Segment B+C (communication) - latency per measurement"
    chart2.x_axis.title = "Measurement"
    chart2.y_axis.title = "Latency (ms)"
    chart2.height = 8
    chart2.width = 16
    chart2.style = 12
    data_ref2 = Reference(ws, min_col=5, max_col=5, min_row=3, max_row=3 + len(comm_utiles))
    chart2.add_data(data_ref2, titles_from_data=True)
    cats2 = Reference(ws, min_col=4, min_row=4, max_row=3 + len(comm_utiles))
    chart2.set_categories(cats2)
    chart2.series[0].graphicalProperties.line.width = 15000
    ws.add_chart(chart2, "G20")

    chart3 = BarChart()
    chart3.type = "col"
    chart3.title = "Comparison of mean latencies"
    chart3.y_axis.title = "Latency (ms)"
    chart3.height = 8
    chart3.width = 12
    chart3.legend = None
    vals = Reference(ws_stats, min_col=2, max_col=3, min_row=5, max_row=5)
    cats = Reference(ws_stats, min_col=2, max_col=3, min_row=3, max_row=3)
    chart3.add_data(vals, from_rows=True)
    chart3.set_categories(cats)
    ws_stats.add_chart(chart3, "E3")

    wb.save(XLSX_FILENAME)
    print(f"  Excel file (data + charts): {XLSX_FILENAME}")


# ======================================================================
# Main program
# ======================================================================

def main():
    print("=" * 55)
    print(" LATENCY BENCHMARK - HuskyLens solution")
    print("=" * 55)

    mesures_husky = mesurer_segment_huskylens()
    mesures_comm = mesurer_segment_communication()

    husky_utiles = mesures_husky[WARMUP_HUSKY:] if len(mesures_husky) > WARMUP_HUSKY else mesures_husky
    comm_utiles = mesures_comm[WARMUP_PINGPONG:] if len(mesures_comm) > WARMUP_PINGPONG else mesures_comm

    stats_a = calculer_stats(husky_utiles)
    stats_bc = calculer_stats(comm_utiles)

    print("\n" + "=" * 55)
    print(" RESULTS (warm-up excluded)")
    print("=" * 55)
    afficher_stats("Segment A (HuskyLens)", stats_a)
    print()
    afficher_stats("Segment B+C (communication)", stats_bc)

    if stats_a and stats_bc:
        total_moy = stats_a["moyenne"] + stats_bc["moyenne"]
        total_med = stats_a["mediane"] + stats_bc["mediane"]
        print(f"\n  Total software latency (means): {total_moy:.2f} ms")
        print(f"  Total software latency (medians): {total_med:.2f} ms")
        print("  (anti-false-positive confirmation delay and final mechanical")
        print("   delay not included)")

    exporter_csv(mesures_husky, mesures_comm)
    if stats_a and stats_bc:
        exporter_excel(husky_utiles, comm_utiles, stats_a, stats_bc)


if __name__ == "__main__":
    main()
