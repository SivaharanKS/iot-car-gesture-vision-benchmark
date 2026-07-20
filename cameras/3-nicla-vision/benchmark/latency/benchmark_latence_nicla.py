"""
Benchmark - Metric 1: LATENCY (Nicla Vision solution)
=======================================================
Segment A (vision): interval between two consecutive "DETECTED:<label>"
lines sent by the Nicla Vision (inference runs on-device, results are
pushed continuously). Time-bounded (SEGMENT_A_MAX_DURATION) to handle
the known ml.utils.NMS crash without hanging.

Segment B+C (communication): serial ping/pong round-trip PC -> robot,
identical to the WebCam/HuskyLens benchmarks.

Requires main.py running autonomously on the Nicla Vision, and code.py
replying {"pong": N} to {"ping": N} on the robot.
"""

import serial
import json
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
COM_ROBOT = "COM22"
BAUDRATE_ROBOT = 115200

N_VISION = 100          # target number of measurements for segment A (vision)
N_PINGPONG = 100        # number of measurements for segment B+C (communication)
PING_TIMEOUT = 1.0      # max wait time for a pong (seconds)

# Number of initial measurements to IGNORE (warm-up).
WARMUP_VISION = 5
WARMUP_PINGPONG = 5

# Safety limit: stop segment A after this many seconds even if N_VISION
# has not been reached, in case the camera crashes mid-measurement
# (known ml.utils.NMS instability, see report).
SEGMENT_A_MAX_DURATION = 90.0

TIMESTAMP = time.strftime('%Y%m%d_%H%M%S')
CSV_FILENAME = f"benchmark_latence_nicla_{TIMESTAMP}.csv"
XLSX_FILENAME = f"benchmark_latence_nicla_{TIMESTAMP}.xlsx"


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
# PHASE 1: Segment A (vision) - time between two consecutive detections
# ======================================================================

def mesurer_segment_vision():
    print("\n=== PHASE 1: Segment A (vision) ===")
    print(f"Target: {N_VISION} measurements (including {WARMUP_VISION} warm-up ones, ignored).")
    print(f"Safety time limit: {SEGMENT_A_MAX_DURATION:.0f} s (in case of camera crash).")
    print("Perform various gestures in front of the Nicla Vision.\n")

    try:
        ser_nicla = serial.Serial(COM_NICLA, 115200, timeout=1)
        print(f"Connected to the Nicla Vision on {COM_NICLA}")
    except serial.SerialException as e:
        print(f"Serial connection error (Nicla Vision): {e}")
        return []

    mesures_ms = []       # all measurements, warm-up included
    t_dernier_valide = None
    t_debut_phase = time.monotonic()

    while len(mesures_ms) < N_VISION:
        if time.monotonic() - t_debut_phase > SEGMENT_A_MAX_DURATION:
            print("Time limit reached, stopping segment A early "
                  "(camera may have crashed or stopped responding).")
            break

        try:
            ligne = ser_nicla.readline().decode(errors="ignore").strip()
        except Exception as e:
            print(f"Serial read error (Nicla Vision disconnected?): {e}")
            break

        if not ligne.startswith("DETECTED:"):
            continue  # ignore anything that is not a detection line

        t_now = time.perf_counter()

        if t_dernier_valide is not None:
            latence_ms = (t_now - t_dernier_valide) * 1000.0
            mesures_ms.append(latence_ms)

            idx = len(mesures_ms)
            phase_txt = "WARM-UP" if idx <= WARMUP_VISION else "MEASURE"
            label = ligne.split(":")[1] if ":" in ligne else "?"
            if idx % 10 == 0 or idx <= WARMUP_VISION:
                print(f"  [{phase_txt}] {idx}/{N_VISION}  "
                      f"label={label:8s}  interval={latence_ms:.1f} ms")

        t_dernier_valide = t_now

    ser_nicla.close()

    if len(mesures_ms) < N_VISION:
        print(f"Warning: only {len(mesures_ms)}/{N_VISION} measurements "
              f"collected for segment A before stopping.")

    return mesures_ms


# ======================================================================
# PHASE 2: Segment B+C (communication) - serial ping/pong
# (identical mechanism to the WebCam and HuskyLens benchmarks)
# ======================================================================

def mesurer_segment_communication():
    print("\n=== PHASE 2: Segment B+C (serial communication) ===")
    print(f"Target: {N_PINGPONG} ping/pong measurements "
          f"(including {WARMUP_PINGPONG} warm-up ones, ignored).\n")

    try:
        ser = serial.Serial(COM_ROBOT, BAUDRATE_ROBOT, timeout=0)
        print(f"Connected to the robot on {COM_ROBOT}")
    except serial.SerialException as e:
        print(f"Serial connection error (robot): {e}")
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
            boot_line = ser.readline().decode(errors="ignore").strip()
            if boot_line:
                print(f"[Boot] {boot_line}")
        time.sleep(0.02)
    time.sleep(0.5)
    while ser.in_waiting:
        ser.readline()

    mesures_ms = []
    perdus = 0

    for i in range(N_PINGPONG):
        message = json.dumps({"ping": i}) + "\n"
        while ser.in_waiting:
            ser.readline()  # flush the buffer before sending

        t_envoi = time.perf_counter()
        ser.write(message.encode())
        deadline = time.perf_counter() + PING_TIMEOUT
        pong_recu = False

        while time.perf_counter() < deadline:
            if ser.in_waiting:
                line = ser.readline().decode(errors="ignore").strip()
                if line.startswith("b'") and line.endswith("'"):
                    line = line[2:-1]
                if '"pong"' in line:
                    try:
                        data = json.loads(line)
                    except Exception:
                        continue
                    if data.get("pong") == i:
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

def exporter_csv(mesures_vision, mesures_comm):
    with open(CSV_FILENAME, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["segment", "measurement_num", "warmup", "latency_ms"])
        for i, v in enumerate(mesures_vision):
            warmup = 1 if i < WARMUP_VISION else 0
            writer.writerow(["vision_A", i, warmup, f"{v:.3f}"])
        for i, v in enumerate(mesures_comm):
            warmup = 1 if i < WARMUP_PINGPONG else 0
            writer.writerow(["communication_BC", i, warmup, f"{v:.3f}"])
    print(f"\n  Raw data (CSV): {CSV_FILENAME}")


def exporter_excel(vision_utiles, comm_utiles, stats_a, stats_bc):
    """Creates an Excel file with split data, statistics, and charts."""
    wb = Workbook()

    entete_fill = PatternFill("solid", start_color="4472C4")
    entete_font = Font(bold=True, color="FFFFFF")
    titre_font = Font(bold=True, size=13)

    # --- Sheet 1: Data ---
    ws = wb.active
    ws.title = "Data"

    ws["A1"] = "Latency measurements (after warm-up) - Nicla Vision"
    ws["A1"].font = titre_font

    ws["A3"] = "Measurement"
    ws["B3"] = "Segment A - vision (ms)"
    ws["D3"] = "Measurement"
    ws["E3"] = "Segment B+C - comm (ms)"
    for cell in ("A3", "B3", "D3", "E3"):
        ws[cell].fill = entete_fill
        ws[cell].font = entete_font
        ws[cell].alignment = Alignment(horizontal="center")

    for i, v in enumerate(vision_utiles):
        ws.cell(row=4 + i, column=1, value=i + 1)
        ws.cell(row=4 + i, column=2, value=round(v, 3))
    for i, v in enumerate(comm_utiles):
        ws.cell(row=4 + i, column=4, value=i + 1)
        ws.cell(row=4 + i, column=5, value=round(v, 3))

    ws.column_dimensions["A"].width = 10
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["D"].width = 10
    ws.column_dimensions["E"].width = 22

    # --- Sheet 2: Statistics ---
    ws_stats = wb.create_sheet("Statistics")
    ws_stats["A1"] = "Latency statistics - Nicla Vision"
    ws_stats["A1"].font = titre_font

    entetes = ["Metric", "Segment A - vision (ms)", "Segment B+C - comm (ms)"]
    for col, txt in enumerate(entetes, start=1):
        c = ws_stats.cell(row=3, column=col, value=txt)
        c.fill = entete_fill
        c.font = entete_font
        c.alignment = Alignment(horizontal="center")

    lignes = [
        ("Number of measurements", stats_a["n"] if stats_a else 0,
         stats_bc["n"] if stats_bc else 0),
        ("Mean", round(stats_a["moyenne"], 2) if stats_a else None,
         round(stats_bc["moyenne"], 2) if stats_bc else None),
        ("Median", round(stats_a["mediane"], 2) if stats_a else None,
         round(stats_bc["mediane"], 2) if stats_bc else None),
        ("Std. deviation", round(stats_a["ecart_type"], 2) if stats_a else None,
         round(stats_bc["ecart_type"], 2) if stats_bc else None),
        ("Minimum", round(stats_a["min"], 2) if stats_a else None,
         round(stats_bc["min"], 2) if stats_bc else None),
        ("Maximum", round(stats_a["max"], 2) if stats_a else None,
         round(stats_bc["max"], 2) if stats_bc else None),
    ]
    for r, (nom, va, vbc) in enumerate(lignes, start=4):
        ws_stats.cell(row=r, column=1, value=nom).font = Font(bold=True)
        ws_stats.cell(row=r, column=2, value=va)
        ws_stats.cell(row=r, column=3, value=vbc)

    for col in ("A", "B", "C"):
        ws_stats.column_dimensions[col].width = 26

    n_vision = len(vision_utiles)
    n_comm = len(comm_utiles)

    # --- Chart 1: vision latency curve over the measurements ---
    if n_vision > 0:
        chart1 = LineChart()
        chart1.title = "Segment A (vision) - interval between detections"
        chart1.x_axis.title = "Measurement"
        chart1.y_axis.title = "Interval (ms)"
        chart1.height = 8
        chart1.width = 16
        chart1.style = 12
        data_ref = Reference(ws, min_col=2, max_col=2, min_row=3,
                             max_row=3 + n_vision)
        chart1.add_data(data_ref, titles_from_data=True)
        cats1 = Reference(ws, min_col=1, min_row=4, max_row=3 + n_vision)
        chart1.set_categories(cats1)
        chart1.series[0].graphicalProperties.line.width = 15000
        ws.add_chart(chart1, "G3")

    # --- Chart 2: communication latency curve ---
    if n_comm > 0:
        chart2 = LineChart()
        chart2.title = "Segment B+C (communication) - latency per measurement"
        chart2.x_axis.title = "Measurement"
        chart2.y_axis.title = "Latency (ms)"
        chart2.height = 8
        chart2.width = 16
        chart2.style = 12
        data_ref2 = Reference(ws, min_col=5, max_col=5, min_row=3,
                              max_row=3 + n_comm)
        chart2.add_data(data_ref2, titles_from_data=True)
        cats2 = Reference(ws, min_col=4, min_row=4, max_row=3 + n_comm)
        chart2.set_categories(cats2)
        chart2.series[0].graphicalProperties.line.width = 15000
        ws.add_chart(chart2, "G20")

    wb.save(XLSX_FILENAME)
    print(f"  Excel file (data + charts): {XLSX_FILENAME}")


# ======================================================================
# Main program
# ======================================================================

def main():
    print("=" * 55)
    print(" LATENCY BENCHMARK - Nicla Vision solution")
    print("=" * 55)

    mesures_vision = mesurer_segment_vision()
    mesures_comm = mesurer_segment_communication()

    vision_utiles = mesures_vision[WARMUP_VISION:] if len(mesures_vision) > WARMUP_VISION else mesures_vision
    comm_utiles = mesures_comm[WARMUP_PINGPONG:] if len(mesures_comm) > WARMUP_PINGPONG else mesures_comm

    stats_a = calculer_stats(vision_utiles)
    stats_bc = calculer_stats(comm_utiles)

    print("\n" + "=" * 55)
    print(" RESULTS (warm-up excluded)")
    print("=" * 55)
    afficher_stats("Segment A (vision)", stats_a)
    print()
    afficher_stats("Segment B+C (communication)", stats_bc)

    if stats_a and stats_bc:
        total_moy = stats_a["moyenne"] + stats_bc["moyenne"]
        total_med = stats_a["mediane"] + stats_bc["mediane"]
        print(f"\n  Total software latency (means): {total_moy:.2f} ms")
        print(f"  Total software latency (medians): {total_med:.2f} ms")
        print("  (final mechanical delay not included)")
    elif not stats_a:
        print("\n  Segment A could not be measured (no valid detection received).")

    exporter_csv(mesures_vision, mesures_comm)
    exporter_excel(vision_utiles, comm_utiles, stats_a, stats_bc)


if __name__ == "__main__":
    main()