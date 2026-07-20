"""
Benchmark - Metric 3: RECOGNITION RELIABILITY (WebCam + PC solution)
============================================================================
Builds a confusion matrix between the INTENDED gesture (indicated by the
user via a key press) and the gesture DETECTED by the system.

Protocol (manual mode):
  - Perform a gesture in front of the webcam.
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

import cv2
import mediapipe as mp
import csv
import time
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# ----------------------------------------------------------------
# Parameters
# ----------------------------------------------------------------
N_PAR_GESTE = 20  # target number of trials for each gesture

TIMESTAMP = time.strftime('%Y%m%d_%H%M%S')
CSV_FILENAME = f"benchmark_fiabilite_webcam_{TIMESTAMP}.csv"
XLSX_FILENAME = f"benchmark_fiabilite_webcam_{TIMESTAMP}.xlsx"

# The 4 gestures (fixed order for the matrix)
GESTES = ["forward", "stop", "turn_left", "turn_right"]
GESTE_LABEL = {
    "forward": "Forward",
    "stop": "Stop",
    "turn_left": "Left",
    "turn_right": "Right",
}
# Key -> intended gesture
TOUCHE_GESTE = {
    ord('1'): "forward",
    ord('2'): "stop",
    ord('3'): "turn_left",
    ord('4'): "turn_right",
}

mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils
FINGER_TIPS = [4, 8, 12, 16, 20]


def get_finger_states(hand_landmarks, handedness_label):
    landmarks = hand_landmarks.landmark
    states = []
    if handedness_label == "Right":
        thumb_up = landmarks[FINGER_TIPS[0]].x < landmarks[FINGER_TIPS[0] - 1].x
    else:
        thumb_up = landmarks[FINGER_TIPS[0]].x > landmarks[FINGER_TIPS[0] - 1].x
    states.append(thumb_up)
    for tip_id in FINGER_TIPS[1:]:
        states.append(landmarks[tip_id].y < landmarks[tip_id - 2].y)
    return tuple(states)


def classify_gesture(finger_states):
    thumb, index, middle, ring, pinky = finger_states
    if not thumb and not index and not middle and not ring and not pinky:
        return "forward"
    if thumb and index and middle and ring and pinky:
        return "stop"
    if thumb and index and not middle and not ring and not pinky:
        return "turn_left"
    if not thumb and index and not middle and not ring and pinky:
        return "turn_right"
    return None  # not recognized


# ======================================================================
# Trial acquisition
# ======================================================================

def acquerir_essais():
    print("\n=== RELIABILITY MEASUREMENT (confusion matrix) ===")
    print("Perform a gesture, then press the key for the INTENDED gesture:")
    print("   1 = Forward   2 = Stop   3 = Left   4 = Right")
    print(f"Target: {N_PAR_GESTE} trials per gesture. Press 'q' to stop.\n")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: unable to open the webcam.")
        return []

    essais = []  # (intended, detected)
    compteur = {g: 0 for g in GESTES}

    with mp_hands.Hands(
        max_num_hands=1,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.7,
    ) as hands:
        while True:
            ret, frame = cap.read()
            if not ret:
                continue

            frame = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(rgb_frame)

            detecte = None
            if results.multi_hand_landmarks and results.multi_handedness:
                for hand_landmarks, handedness in zip(
                    results.multi_hand_landmarks, results.multi_handedness
                ):
                    mp_draw.draw_landmarks(
                        frame, hand_landmarks, mp_hands.HAND_CONNECTIONS
                    )
                    label = handedness.classification[0].label
                    finger_states = get_finger_states(hand_landmarks, label)
                    detecte = classify_gesture(finger_states)

            # Live display of the detected gesture
            det_txt = GESTE_LABEL.get(detecte, "Not recognized")
            cv2.putText(frame, f"Detected: {det_txt}", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

            # Displaying the counters
            y = 80
            total = sum(compteur.values())
            for g in GESTES:
                txt = f"{GESTE_LABEL[g]}: {compteur[g]}/{N_PAR_GESTE}"
                couleur = (0, 255, 0) if compteur[g] >= N_PAR_GESTE else (255, 255, 255)
                cv2.putText(frame, txt, (20, y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, couleur, 2)
                y += 30
            cv2.putText(frame, "Keys: 1=Fwd 2=Stop 3=Left 4=Right | q=quit",
                        (20, y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

            cv2.imshow("Reliability Benchmark - WebCam", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                print("Manual stop of the acquisition.")
                break
            if key in TOUCHE_GESTE:
                voulu = TOUCHE_GESTE[key]
                essais.append((voulu, detecte))
                compteur[voulu] += 1
                det_print = GESTE_LABEL.get(detecte, "Not recognized")
                ok = "OK" if voulu == detecte else "X"
                print(f"  [{ok}] Intended={GESTE_LABEL[voulu]:8s} "
                      f"Detected={det_print}  "
                      f"({compteur[voulu]}/{N_PAR_GESTE})")

                # Automatic stop once all gestures have reached the target
                if all(compteur[g] >= N_PAR_GESTE for g in GESTES):
                    print("\nTarget reached for all 4 gestures.")
                    break

    cap.release()
    cv2.destroyAllWindows()
    return essais


# ======================================================================
# Building the confusion matrix
# ======================================================================

def construire_matrice(essais):
    """Returns the matrix (dict): matrice[intended][detected] = count.
    'detected' can be None (not recognized)."""
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
    print(" CONFUSION MATRIX")
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

    # Overall recognition rate
    total = len(essais)
    corrects = sum(1 for voulu, detecte in essais if voulu == detecte)
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
    diag_fill = PatternFill("solid", start_color="C6EFCE")   # green (correct)
    err_fill = PatternFill("solid", start_color="FFC7CE")    # red (errors)
    bord = Border(*[Side(style="thin")] * 4)

    ws = wb.active
    ws.title = "Confusion matrix"
    ws["A1"] = "Confusion matrix - WebCam reliability"
    ws["A1"].font = titre_font

    colonnes = GESTES + [None]
    col_labels = [GESTE_LABEL.get(d, "Not detected") for d in colonnes]

    # Header
    ws.cell(row=3, column=1, value="Intended \\ Detected").fill = entete_fill
    ws.cell(row=3, column=1).font = entete_font
    for j, lab in enumerate(col_labels, start=2):
        c = ws.cell(row=3, column=j, value=lab)
        c.fill = entete_fill
        c.font = entete_font
        c.alignment = Alignment(horizontal="center")

    # Matrix rows
    for i, v in enumerate(GESTES, start=4):
        cv_ = ws.cell(row=i, column=1, value=GESTE_LABEL[v])
        cv_.fill = entete_fill
        cv_.font = entete_font
        for j, d in enumerate(colonnes, start=2):
            val = matrice[v][d]
            c = ws.cell(row=i, column=j, value=val)
            c.alignment = Alignment(horizontal="center")
            c.border = bord
            # Coloring: green on the diagonal (v == d), red if a nonzero error
            if v == d:
                c.fill = diag_fill
            elif val > 0:
                c.fill = err_fill

    # Overall rate
    r = 4 + len(GESTES) + 1
    ws.cell(row=r, column=1, value="Overall recognition rate").font = Font(bold=True)
    ws.cell(row=r, column=2, value=f"{taux:.1f} %")
    ws.cell(row=r + 1, column=1, value="Correct trials / total")
    ws.cell(row=r + 1, column=2, value=f"{corrects} / {total}")

    ws.column_dimensions["A"].width = 18
    for col in "BCDEF":
        ws.column_dimensions[col].width = 13

    # --- Sheet 2: recognition rate per gesture (bar chart) ---
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
    print(" RELIABILITY BENCHMARK - WebCam + PC solution")
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