"""
Benchmark - Metric 3: RECOGNITION RELIABILITY (HuskyLens solution)
============================================================================
Builds a confusion matrix between the INTENDED gesture (indicated by the
user via a key press) and the gesture DETECTED by the HuskyLens.
Adapted from the webcam version: since the HuskyLens has no PC window
(it has its own built-in screen), key presses are read from the console
in a non-blocking way (msvcrt module, Windows), while the camera is
continuously queried.

Protocol (manual mode):
  - Perform a gesture in front of the HuskyLens (look at its built-in screen).
  - Press the key for the gesture you INTENDED to make:
        1 = Forward  (closed fist)
        2 = Stop     (open hand)
        3 = Left     (index + thumb)
        4 = Right    (index + pinky)
  - The script records (intended, detected) at the moment of the key press.
  - Target: N_PAR_GESTE trials for each of the 4 gestures.
  - Press 'q' to stop before the end.

Outputs:
  - a CSV with each trial (intended, detected, correct);
  - an Excel (.xlsx) with the confusion matrix (heatmap) and the overall rate.
"""

import msvcrt
import csv
import time
from huskylib import HuskyLensLibrary
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# ----------------------------------------------------------------
# Parameters
# ----------------------------------------------------------------
COM_HUSKY = "COM25"  # HuskyLens serial port

N_PAR_GESTE = 20  # target number of trials for each gesture
ID_NEUTRE = 5     # ID of the neutral class (not counted as a valid gesture)

TIMESTAMP = time.strftime('%Y%m%d_%H%M%S')
CSV_FILENAME = f"benchmark_fiabilite_huskylens_{TIMESTAMP}.csv"
XLSX_FILENAME = f"benchmark_fiabilite_huskylens_{TIMESTAMP}.xlsx"

# The 4 gestures (fixed order for the matrix), same names as the WebCam solution
GESTES = ["forward", "stop", "turn_left", "turn_right"]
GESTE_LABEL = {
    "forward": "Forward",
    "stop": "Stop",
    "turn_left": "Left",
    "turn_right": "Right",
}
ID_TO_GESTE = {
    1: "forward",
    2: "stop",
    3: "turn_left",
    4: "turn_right",
}
# Key -> intended gesture
TOUCHE_GESTE = {
    b'1': "forward",
    b'2': "stop",
    b'3': "turn_left",
    b'4': "turn_right",
}


def lire_id_geste(hl):
    """Queries the HuskyLens and returns the detected ID, or None."""
    try:
        objet = hl.learned()
    except Exception:
        return None
    if not objet:
        return None
    return getattr(objet, "ID", None)


# ======================================================================
# Trial acquisition
# ======================================================================

def acquerir_essais():
    print("\n=== RELIABILITY MEASUREMENT (confusion matrix) - HuskyLens ===")
    print("Perform a gesture, then press the key for the INTENDED gesture:")
    print("   1 = Forward   2 = Stop   3 = Left   4 = Right")
    print(f"Target: {N_PAR_GESTE} trials per gesture. Press 'q' to stop.\n")

    try:
        hl = HuskyLensLibrary("SERIAL", COM_HUSKY)
        print(hl.knock())
        hl.algorthim("ALGORITHM_OBJECT_CLASSIFICATION")
    except Exception as e:
        print(f"Connection error to the HuskyLens ({COM_HUSKY}): {e}")
        return []

    essais = []  # (intended, detected)
    compteur = {g: 0 for g in GESTES}
    dernier_affiche = None
    dernier_affichage_temps = 0.0
    AFFICHAGE_INTERVAL = 0.5

    while True:
        detected_id = lire_id_geste(hl)
        detecte = ID_TO_GESTE.get(detected_id) if detected_id != ID_NEUTRE else None

        # Rate-limited live display of the detected gesture (console)
        now = time.monotonic()
        if detecte != dernier_affiche or (now - dernier_affichage_temps) > AFFICHAGE_INTERVAL:
            det_txt = GESTE_LABEL.get(detecte, "Not recognized")
            compteurs_txt = " | ".join(
                f"{GESTE_LABEL[g]}:{compteur[g]}/{N_PAR_GESTE}" for g in GESTES
            )
            print(f"\rDetected: {det_txt:10s} || {compteurs_txt}", end="", flush=True)
            dernier_affiche = detecte
            dernier_affichage_temps = now

        # Non-blocking keyboard read (Windows)
        if msvcrt.kbhit():
            touche = msvcrt.getch()
            if touche == b'q':
                print("\nManual stop of the acquisition.")
                break
            if touche in TOUCHE_GESTE:
                voulu = TOUCHE_GESTE[touche]
                essais.append((voulu, detecte))
                compteur[voulu] += 1
                det_print = GESTE_LABEL.get(detecte, "Not recognized")
                ok = "OK" if voulu == detecte else "X"
                print(f"\n  [{ok}] Intended={GESTE_LABEL[voulu]:8s} "
                      f"Detected={det_print}  "
                      f"({compteur[voulu]}/{N_PAR_GESTE})")

                if all(compteur[g] >= N_PAR_GESTE for g in GESTES):
                    print("\nTarget reached for all 4 gestures.")
                    break

    return essais


# ======================================================================
# Building the confusion matrix
# (logic identical to the WebCam solution)
# ======================================================================

def construire_matrice(essais):
    colonnes = GESTES + [None]  # None = "not detected" column
    matrice = {v: {d: 0 for d in colonnes} for v in GESTES}
    for voulu, detecte in essais:
        if voulu in matrice:
            if detecte in matrice[voulu]:
                matrice[voulu][detecte] += 1
            else:
                matrice[voulu][None] += 1
    return matrice


def afficher_matrice(matrice, essais):
    print("\n" + "=" * 55)
    print(" CONFUSION MATRIX - HuskyLens")
    print("=" * 55)
    colonnes = GESTES + [None]
    entete = "Intended \\ Det. | " + " ".join(
        f"{GESTE_LABEL.get(d, 'NotDet'):>7s}" for d in colonnes
    )
    print(entete)
    print("-" * len(entete))
    for v in GESTES:
        ligne = f"{GESTE_LABEL[v]:12s} | "
        ligne += " ".join(f"{matrice[v][d]:>7d}" for d in colonnes)
        print(ligne)

    total = len(essais)
    corrects = sum(1 for voulu, detecte in essais if voulu == detecte)
    taux = (corrects / total * 100) if total else 0.0
    print("-" * len(entete))
    print(f"Overall recognition rate: {corrects}/{total} = {taux:.1f} %")
    return taux, corrects, total


# ======================================================================
# CSV and Excel export (identical to the WebCam solution)
# ======================================================================

def exporter_csv(essais):
    with open(CSV_FILENAME, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["trial", "intended", "detected", "correct"])
        for i, (voulu, detecte) in enumerate(essais):
            det = detecte if detecte is not None else "not_detected"
            correct = 1 if voulu == detecte else 0
            writer.writerow([i + 1, voulu, det, correct])
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
    ws["A1"] = "Confusion matrix - HuskyLens reliability"
    ws["A1"].font = titre_font

    colonnes = GESTES + [None]
    col_labels = [GESTE_LABEL.get(d, "Not detected") for d in colonnes]

    ws.cell(row=3, column=1, value="Intended \\ Detected").fill = entete_fill
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
    print(" RELIABILITY BENCHMARK - HuskyLens solution")
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
