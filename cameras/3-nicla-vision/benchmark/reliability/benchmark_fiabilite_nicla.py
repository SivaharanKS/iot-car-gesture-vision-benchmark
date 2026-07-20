"""
Benchmark - Metric 3: RECOGNITION RELIABILITY (Nicla Vision solution)
========================================================================
Builds a confusion matrix between the INTENDED gesture (indicated by the
user via a key press) and the gesture VALIDATED by the same temporal
confirmation filter used in nicla_to_serial.py (CONFIRM_COUNT identical
detections in a row), rather than the raw single-frame detection.

Protocol (manual mode, same as WebCam/HuskyLens):
  - Perform a gesture in front of the Nicla Vision.
  - Press the key for the gesture you INTENDED to make:
        1 = Forward   2 = Stop   3 = Left   4 = Right
  - The script records (intended, validated) at the moment of the key press.
  - Target: N_PAR_GESTE trials for each of the 4 gestures.
  - Press 'q' to stop before the end.

Requires main.py running autonomously on the Nicla Vision (Windows only,
uses msvcrt for non-blocking key reads).

Outputs:
  - a CSV with each trial (intended, validated, correct);
  - an Excel (.xlsx) with the confusion matrix (heatmap) and the overall rate.
"""

import serial
import csv
import time
import msvcrt
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# ----------------------------------------------------------------
# Parameters
# ----------------------------------------------------------------
COM_NICLA = "COM31"
CONFIRM_COUNT = 5   # same temporal filter as nicla_to_serial.py
N_PAR_GESTE = 20    # target number of trials for each gesture

TIMESTAMP = time.strftime('%Y%m%d_%H%M%S')
CSV_FILENAME = f"benchmark_fiabilite_nicla_{TIMESTAMP}.csv"
XLSX_FILENAME = f"benchmark_fiabilite_nicla_{TIMESTAMP}.xlsx"

GESTES = ["forward", "stop", "turn_left", "turn_right"]
GESTE_LABEL = {
    "forward": "Forward",
    "stop": "Stop",
    "turn_left": "Left",
    "turn_right": "Right",
}
TOUCHE_GESTE = {
    b'1': "forward",
    b'2': "stop",
    b'3': "turn_left",
    b'4': "turn_right",
}
NICLA_LABEL_TO_CMD = {
    "Forward": "forward",
    "Stop": "stop",
    "Left": "turn_left",
    "Right": "turn_right",
}


# ======================================================================
# Trial acquisition
# ======================================================================

def acquerir_essais():
    print("\n=== RELIABILITY MEASUREMENT (confusion matrix) ===")
    print("Perform a gesture, then press the key for the INTENDED gesture:")
    print("   1 = Forward   2 = Stop   3 = Left   4 = Right")
    print(f"Target: {N_PAR_GESTE} trials per gesture. Press 'q' to stop.\n")

    try:
        ser_nicla = serial.Serial(COM_NICLA, 115200, timeout=0)
        print(f"Connected to the Nicla Vision on {COM_NICLA}")
    except serial.SerialException as e:
        print(f"Serial connection error (Nicla Vision): {e}")
        return []

    essais = []  # (intended, validated)
    compteur = {g: 0 for g in GESTES}

    dernier_label = None
    compteur_confirm = 0
    label_valide = "none"

    try:
        while True:
            # Non-blocking read of any pending detection lines
            while ser_nicla.in_waiting:
                ligne = ser_nicla.readline().decode(errors="ignore").strip()
                if not ligne.startswith("DETECTED:"):
                    continue
                label = ligne.split(":")[1] if ":" in ligne else "none"

                if label == dernier_label:
                    compteur_confirm += 1
                else:
                    dernier_label = label
                    compteur_confirm = 1

                if compteur_confirm >= CONFIRM_COUNT:
                    label_valide = NICLA_LABEL_TO_CMD.get(label, "none")

            # Non-blocking key read
            if msvcrt.kbhit():
                touche = msvcrt.getch()
                if touche == b'q':
                    print("Manual stop of the acquisition.")
                    break
                if touche in TOUCHE_GESTE:
                    voulu = TOUCHE_GESTE[touche]
                    essais.append((voulu, label_valide))
                    compteur[voulu] += 1
                    ok = "OK" if voulu == label_valide else "X"
                    print(f"  [{ok}] Intended={GESTE_LABEL[voulu]:8s} "
                          f"Validated={GESTE_LABEL.get(label_valide, 'Not detected')}  "
                          f"({compteur[voulu]}/{N_PAR_GESTE})")

                    if all(compteur[g] >= N_PAR_GESTE for g in GESTES):
                        print("\nTarget reached for all 4 gestures.")
                        break

            time.sleep(0.01)

    except KeyboardInterrupt:
        print("Interrupted by user.")

    ser_nicla.close()
    return essais


# ======================================================================
# Building the confusion matrix
# ======================================================================

def construire_matrice(essais):
    colonnes = GESTES + [None]  # None = "not detected / none" column
    matrice = {v: {d: 0 for d in colonnes} for v in GESTES}
    for voulu, valide in essais:
        d = valide if valide in GESTES else None
        if voulu in matrice:
            matrice[voulu][d] += 1
    return matrice


def afficher_matrice(matrice, essais):
    print("\n" + "=" * 55)
    print(" CONFUSION MATRIX")
    print("=" * 55)
    colonnes = GESTES + [None]
    entete = "Intended \\ Valid. | " + " ".join(
        f"{GESTE_LABEL.get(d, 'NotDet'):>7s}" for d in colonnes
    )
    print(entete)
    print("-" * len(entete))
    for v in GESTES:
        ligne = f"{GESTE_LABEL[v]:12s} | "
        ligne += " ".join(f"{matrice[v][d]:>7d}" for d in colonnes)
        print(ligne)

    total = len(essais)
    corrects = sum(1 for voulu, valide in essais if voulu == valide)
    taux = (corrects / total * 100) if total else 0.0
    print("-" * len(entete))
    print(f"Overall recognition rate: {corrects}/{total} = {taux:.1f} %")
    return taux, corrects, total


# ======================================================================
# CSV and Excel export
# ======================================================================

def exporter_csv(essais):
    with open(CSV_FILENAME, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["trial", "intended", "validated", "correct"])
        for i, (voulu, valide) in enumerate(essais):
            v = valide if valide in GESTES else "not_detected"
            correct = 1 if voulu == valide else 0
            writer.writerow([i + 1, voulu, v, correct])
    print(f"\n  Raw data (CSV): {CSV_FILENAME}")


def exporter_excel(matrice, essais, taux, corrects, total):
    wb = Workbook()
    entete_fill = PatternFill("solid", start_color="4472C4")
    entete_font = Font(bold=True, color="FFFFFF")
    titre_font = Font(bold=True, size=13)
    diag_fill = PatternFill("solid", start_color="C6EFCE")
    err_fill = PatternFill("solid", start_color="FFC7CE")
    bord = Border(*[Side(style="thin")] * 4)

    ws = wb.active
    ws.title = "Confusion matrix"
    ws["A1"] = "Confusion matrix - Nicla Vision reliability"
    ws["A1"].font = titre_font

    colonnes = GESTES + [None]
    col_labels = [GESTE_LABEL.get(d, "Not detected") for d in colonnes]

    ws.cell(row=3, column=1, value="Intended \\ Validated").fill = entete_fill
    ws.cell(row=3, column=1).font = entete_font
    for j, lab in enumerate(col_labels, start=2):
        c = ws.cell(row=3, column=j, value=lab)
        c.fill = entete_fill
        c.font = entete_font
        c.alignment = Alignment(horizontal="center")

    for i, v in enumerate(GESTES, start=4):
        cv_ = ws.cell(row=i, column=1, value=GESTE_LABEL[v])
        cv_.fill = entete_fill
        cv_.font = entete_font
        for j, d in enumerate(colonnes, start=2):
            val = matrice[v][d]
            c = ws.cell(row=i, column=j, value=val)
            c.alignment = Alignment(horizontal="center")
            c.border = bord
            if v == d:
                c.fill = diag_fill
            elif val > 0:
                c.fill = err_fill

    r = 4 + len(GESTES) + 1
    ws.cell(row=r, column=1, value="Overall recognition rate").font = Font(bold=True)
    ws.cell(row=r, column=2, value=f"{taux:.1f} %")
    ws.cell(row=r + 1, column=1, value="Correct trials / total")
    ws.cell(row=r + 1, column=2, value=f"{corrects} / {total}")

    ws.column_dimensions["A"].width = 18
    for col in "BCDEF":
        ws.column_dimensions[col].width = 13

    ws2 = wb.create_sheet("Rate per gesture")
    ws2["A1"] = "Recognition rate per gesture"
    ws2["A1"].font = titre_font
    ws2.cell(row=3, column=1, value="Gesture").fill = entete_fill
    ws2.cell(row=3, column=1).font = entete_font
    ws2.cell(row=3, column=2, value="Rate (%)").fill = entete_fill
    ws2.cell(row=3, column=2).font = entete_font

    for i, v in enumerate(GESTES, start=4):
        n_voulu = sum(matrice[v][d] for d in colonnes)
        n_ok = matrice[v][v]
        taux_g = (n_ok / n_voulu * 100) if n_voulu else 0.0
        ws2.cell(row=i, column=1, value=GESTE_LABEL[v])
        ws2.cell(row=i, column=2, value=round(taux_g, 1))

    ws2.column_dimensions["A"].width = 14
    ws2.column_dimensions["B"].width = 12

    chart = BarChart()
    chart.type = "col"
    chart.title = "Recognition rate per gesture"
    chart.y_axis.title = "Rate (%)"
    chart.height = 8
    chart.width = 12
    chart.legend = None
    vals = Reference(ws2, min_col=2, min_row=3, max_row=3 + len(GESTES))
    cats = Reference(ws2, min_col=1, min_row=4, max_row=3 + len(GESTES))
    chart.add_data(vals, titles_from_data=True)
    chart.set_categories(cats)
    ws2.add_chart(chart, "D3")

    wb.save(XLSX_FILENAME)
    print(f"  Excel file (matrix + chart): {XLSX_FILENAME}")


# ======================================================================
# Main program
# ======================================================================

def main():
    print("=" * 55)
    print(" RELIABILITY BENCHMARK - Nicla Vision solution")
    print("=" * 55)

    essais = acquerir_essais()
    if not essais:
        print("No trial recorded.")
        return

    matrice = construire_matrice(essais)
    taux, corrects, total = afficher_matrice(matrice, essais)

    exporter_csv(essais)
    exporter_excel(matrice, essais, taux, corrects, total)


if __name__ == "__main__":
    main()