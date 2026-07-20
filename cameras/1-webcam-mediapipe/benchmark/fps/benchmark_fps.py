"""
Benchmark - Metric 2: THROUGHPUT / FPS (WebCam + PC solution)
===========================================================
Measures the number of frames processed per second by the full pipeline
(webcam capture + MediaPipe processing + gesture classification).

The instantaneous FPS is recorded for each frame (1 / loop duration) and
classified according to whether a hand is detected or not, in order to
distinguish:
  - FPS with a hand   : real gesture-control use case (heavier processing)
  - FPS without a hand: reference (lighter processing)

The measurement lasts DUREE_MESURE seconds. The first few seconds (warm-up
of MediaPipe/TensorFlow) are excluded from the statistics.

Outputs:
  - a CSV with the FPS of each frame;
  - an Excel (.xlsx) with the data, the statistics, and charts.

Press 'q' in the webcam window to stop before the end.
"""

import cv2
import mediapipe as mp
import time
import csv
import statistics
from openpyxl import Workbook
from openpyxl.chart import LineChart, BarChart, Reference
from openpyxl.styles import Font, PatternFill, Alignment

# ----------------------------------------------------------------
# Parameters to adapt
# ----------------------------------------------------------------
DUREE_MESURE = 30.0   # measurement duration in seconds (steady state)
WARMUP_SEC = 3.0      # warm-up duration ignored at the start (seconds)

TIMESTAMP = time.strftime('%Y%m%d_%H%M%S')
CSV_FILENAME = f"benchmark_fps_webcam_{TIMESTAMP}.csv"
XLSX_FILENAME = f"benchmark_fps_webcam_{TIMESTAMP}.xlsx"

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
        return "forward", "Closed fist"
    if thumb and index and middle and ring and pinky:
        return "stop", "Open hand"
    if thumb and index and not middle and not ring and not pinky:
        return "turn_left", "Index + thumb"
    if not thumb and index and not middle and not ring and pinky:
        return "turn_right", "Index + pinky"
    return None, "Gesture not recognized"


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
    print("Alternate between 'hand visible' and 'no hand' to measure both cases.\n")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: unable to open the webcam.")
        return []

    # Each entry: (relative_time_s, instantaneous_fps, hand_present 0/1, warmup 0/1)
    donnees = []

    t_start = time.perf_counter()
    t_prev = t_start

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

            main_presente = 0
            gesture_name = "No hand"
            if results.multi_hand_landmarks and results.multi_handedness:
                main_presente = 1
                for hand_landmarks, handedness in zip(
                    results.multi_hand_landmarks, results.multi_handedness
                ):
                    mp_draw.draw_landmarks(
                        frame, hand_landmarks, mp_hands.HAND_CONNECTIONS
                    )
                    label = handedness.classification[0].label
                    finger_states = get_finger_states(hand_landmarks, label)
                    _, gesture_name = classify_gesture(finger_states)

            # Computing the instantaneous FPS (1 / loop duration)
            t_now = time.perf_counter()
            dt = t_now - t_prev
            t_prev = t_now
            fps = (1.0 / dt) if dt > 0 else 0.0

            t_rel = t_now - t_start
            warmup = 1 if t_rel < WARMUP_SEC else 0
            donnees.append((t_rel, fps, main_presente, warmup))

            # Display
            phase = "WARM-UP" if warmup else "MEASURE"
            cv2.putText(frame, f"{phase}  t={t_rel:.1f}s / {DUREE_MESURE:.0f}s",
                        (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.putText(frame, f"FPS: {fps:.1f}", (20, 75),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            cv2.putText(frame, f"Hand: {'YES' if main_presente else 'no'}",
                        (20, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.imshow("FPS Benchmark - WebCam", frame)

            if t_rel >= DUREE_MESURE:
                break
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("Manual stop of the measurement.")
                break

    cap.release()
    cv2.destroyAllWindows()
    return donnees


# ======================================================================
# CSV and Excel export
# ======================================================================

def exporter_csv(donnees):
    with open(CSV_FILENAME, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["time_s", "fps", "hand_present", "warmup"])
        for t_rel, fps, main, warmup in donnees:
            writer.writerow([f"{t_rel:.3f}", f"{fps:.2f}", main, warmup])
    print(f"\n  Raw data (CSV): {CSV_FILENAME}")


def exporter_excel(donnees_utiles, stats_global, stats_main, stats_sans):
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

    entetes = ["Frame", "Time (s)", "FPS", "Hand present"]
    for col, txt in enumerate(entetes, start=1):
        c = ws.cell(row=3, column=col, value=txt)
        c.fill = entete_fill
        c.font = entete_font
        c.alignment = Alignment(horizontal="center")

    for i, (t_rel, fps, main, _warmup) in enumerate(donnees_utiles):
        ws.cell(row=4 + i, column=1, value=i + 1)
        ws.cell(row=4 + i, column=2, value=round(t_rel, 3))
        ws.cell(row=4 + i, column=3, value=round(fps, 2))
        ws.cell(row=4 + i, column=4, value=main)

    for col, w in (("A", 10), ("B", 12), ("C", 10), ("D", 14)):
        ws.column_dimensions[col].width = w

    n = len(donnees_utiles)

    # --- Sheet 2: Statistics ---
    ws_stats = wb.create_sheet("Statistics")
    ws_stats["A1"] = "Throughput (FPS) statistics"
    ws_stats["A1"].font = titre_font

    entetes_s = ["Metric", "Global", "With hand", "Without hand"]
    for col, txt in enumerate(entetes_s, start=1):
        c = ws_stats.cell(row=3, column=col, value=txt)
        c.fill = entete_fill
        c.font = entete_font
        c.alignment = Alignment(horizontal="center")

    def ligne_stat(nom, cle):
        return (
            nom,
            round(stats_global[cle], 2) if stats_global else None,
            round(stats_main[cle], 2) if stats_main else None,
            round(stats_sans[cle], 2) if stats_sans else None,
        )

    lignes = [
        ligne_stat("Number of frames", "n"),
        ligne_stat("Mean FPS", "moyenne"),
        ligne_stat("Median FPS", "mediane"),
        ligne_stat("Std. deviation", "ecart_type"),
        ligne_stat("Min FPS", "min"),
        ligne_stat("Max FPS", "max"),
    ]
    for r, (nom, g, m, s) in enumerate(lignes, start=4):
        ws_stats.cell(row=r, column=1, value=nom).font = Font(bold=True)
        ws_stats.cell(row=r, column=2, value=g)
        ws_stats.cell(row=r, column=3, value=m)
        ws_stats.cell(row=r, column=4, value=s)

    for col in ("A", "B", "C", "D"):
        ws_stats.column_dimensions[col].width = 18

    # --- Chart 1: instantaneous FPS over time (single curve) ---
    chart1 = LineChart()
    chart1.title = "Throughput (FPS) over the frames"
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

    # --- Chart 2: bar comparison of mean FPS (global / hand / no hand) ---
    chart2 = BarChart()
    chart2.type = "col"
    chart2.title = "Mean FPS depending on hand presence"
    chart2.y_axis.title = "FPS"
    chart2.height = 8
    chart2.width = 12
    chart2.legend = None
    vals = Reference(ws_stats, min_col=2, max_col=4, min_row=5, max_row=5)  # mean FPS row
    cats = Reference(ws_stats, min_col=2, max_col=4, min_row=3, max_row=3)  # headers
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
    print(" THROUGHPUT (FPS) BENCHMARK - WebCam + PC solution")
    print("=" * 55)

    donnees = mesurer_fps()
    if not donnees:
        print("No data measured.")
        return

    # Excluding warm-up
    donnees_utiles = [d for d in donnees if d[3] == 0]

    fps_global = [d[1] for d in donnees_utiles]
    fps_main = [d[1] for d in donnees_utiles if d[2] == 1]
    fps_sans = [d[1] for d in donnees_utiles if d[2] == 0]

    stats_global = calculer_stats(fps_global)
    stats_main = calculer_stats(fps_main)
    stats_sans = calculer_stats(fps_sans)

    print("\n" + "=" * 55)
    print(" RESULTS (warm-up excluded)")
    print("=" * 55)
    afficher_stats("Global FPS", stats_global)
    print()
    afficher_stats("FPS with hand", stats_main)
    print()
    afficher_stats("FPS without hand", stats_sans)

    exporter_csv(donnees)
    if stats_global:
        exporter_excel(donnees_utiles, stats_global, stats_main, stats_sans)


if __name__ == "__main__":
    main()