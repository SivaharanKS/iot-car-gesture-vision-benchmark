"""
Benchmark - Metrique 2 : DEBIT / FPS (solution WebCam + PC)
===========================================================
Mesure le nombre d'images traitees par seconde par le pipeline complet
(capture webcam + traitement MediaPipe + classification du geste).

Le FPS instantane est releve a chaque image (1 / duree de la boucle) et
classe selon qu'une main est detectee ou non, afin de distinguer :
  - FPS avec main   : cas d'usage reel du controle gestuel (traitement lourd)
  - FPS sans main   : reference (traitement plus leger)

La mesure dure DUREE_MESURE secondes. Les premieres secondes (warm-up de
MediaPipe/TensorFlow) sont exclues des statistiques.

Sorties :
  - un CSV avec le FPS de chaque image ;
  - un Excel (.xlsx) avec les donnees, les statistiques et des graphiques.

Appuie sur 'q' dans la fenetre webcam pour arreter avant la fin.
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
# Parametres a adapter
# ----------------------------------------------------------------
DUREE_MESURE = 30.0   # duree de la mesure en secondes (regime etabli)
WARMUP_SEC = 3.0      # duree d'echauffement ignoree au debut (secondes)

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
        return "forward", "Poing ferme"
    if thumb and index and middle and ring and pinky:
        return "stop", "Main ouverte"
    if thumb and index and not middle and not ring and not pinky:
        return "turn_left", "Index + pouce"
    if not thumb and index and not middle and not ring and pinky:
        return "turn_right", "Index + auriculaire"
    return None, "Geste non reconnu"


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
        print(f"  {nom} : aucune mesure.")
        return
    print(f"  {nom} ({stats['n']} images) :")
    print(f"    FPS moyen    : {stats['moyenne']:.2f}")
    print(f"    FPS median   : {stats['mediane']:.2f}")
    print(f"    Ecart-type   : {stats['ecart_type']:.2f}")
    print(f"    FPS min      : {stats['min']:.2f}")
    print(f"    FPS max      : {stats['max']:.2f}")


# ======================================================================
# Mesure du FPS
# ======================================================================

def mesurer_fps():
    print("\n=== MESURE DU DEBIT (FPS) ===")
    print(f"Duree : {DUREE_MESURE:.0f} s (dont {WARMUP_SEC:.0f} s de warm-up ignorees).")
    print("Alterne entre 'main visible' et 'pas de main' pour mesurer les deux cas.\n")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Erreur : impossible d'ouvrir la webcam.")
        return []

    # Chaque entree : (temps_relatif_s, fps_instantane, main_presente 0/1, warmup 0/1)
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
            gesture_name = "Aucune main"
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

            # Calcul du FPS instantane (1 / duree de la boucle)
            t_now = time.perf_counter()
            dt = t_now - t_prev
            t_prev = t_now
            fps = (1.0 / dt) if dt > 0 else 0.0

            t_rel = t_now - t_start
            warmup = 1 if t_rel < WARMUP_SEC else 0
            donnees.append((t_rel, fps, main_presente, warmup))

            # Affichage
            phase = "WARM-UP" if warmup else "MESURE"
            cv2.putText(frame, f"{phase}  t={t_rel:.1f}s / {DUREE_MESURE:.0f}s",
                        (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.putText(frame, f"FPS : {fps:.1f}", (20, 75),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            cv2.putText(frame, f"Main : {'OUI' if main_presente else 'non'}",
                        (20, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.imshow("Benchmark FPS - WebCam", frame)

            if t_rel >= DUREE_MESURE:
                break
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("Arret manuel de la mesure.")
                break

    cap.release()
    cv2.destroyAllWindows()
    return donnees


# ======================================================================
# Export CSV et Excel
# ======================================================================

def exporter_csv(donnees):
    with open(CSV_FILENAME, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["temps_s", "fps", "main_presente", "warmup"])
        for t_rel, fps, main, warmup in donnees:
            writer.writerow([f"{t_rel:.3f}", f"{fps:.2f}", main, warmup])
    print(f"\n  Donnees brutes (CSV) : {CSV_FILENAME}")


def exporter_excel(donnees_utiles, stats_global, stats_main, stats_sans):
    """Cree un fichier Excel avec donnees, statistiques et graphiques."""
    wb = Workbook()

    entete_fill = PatternFill("solid", start_color="4472C4")
    entete_font = Font(bold=True, color="FFFFFF")
    titre_font = Font(bold=True, size=13)

    # --- Feuille 1 : Donnees ---
    ws = wb.active
    ws.title = "Donnees"
    ws["A1"] = "Mesure du debit (FPS) - regime etabli (warm-up exclu)"
    ws["A1"].font = titre_font

    entetes = ["Image", "Temps (s)", "FPS", "Main presente"]
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

    # --- Feuille 2 : Statistiques ---
    ws_stats = wb.create_sheet("Statistiques")
    ws_stats["A1"] = "Statistiques du debit (FPS)"
    ws_stats["A1"].font = titre_font

    entetes_s = ["Metrique", "Global", "Avec main", "Sans main"]
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
        ligne_stat("Nombre d'images", "n"),
        ligne_stat("FPS moyen", "moyenne"),
        ligne_stat("FPS median", "mediane"),
        ligne_stat("Ecart-type", "ecart_type"),
        ligne_stat("FPS min", "min"),
        ligne_stat("FPS max", "max"),
    ]
    for r, (nom, g, m, s) in enumerate(lignes, start=4):
        ws_stats.cell(row=r, column=1, value=nom).font = Font(bold=True)
        ws_stats.cell(row=r, column=2, value=g)
        ws_stats.cell(row=r, column=3, value=m)
        ws_stats.cell(row=r, column=4, value=s)

    for col in ("A", "B", "C", "D"):
        ws_stats.column_dimensions[col].width = 18

    # --- Graphique 1 : FPS instantane au fil du temps (courbe unique) ---
    chart1 = LineChart()
    chart1.title = "Debit (FPS) au fil des images"
    chart1.x_axis.title = "Image"
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

    # --- Graphique 2 : barres comparatives FPS moyen (global / main / sans) ---
    chart2 = BarChart()
    chart2.type = "col"
    chart2.title = "FPS moyen selon la presence d'une main"
    chart2.y_axis.title = "FPS"
    chart2.height = 8
    chart2.width = 12
    chart2.legend = None
    vals = Reference(ws_stats, min_col=2, max_col=4, min_row=5, max_row=5)  # ligne FPS moyen
    cats = Reference(ws_stats, min_col=2, max_col=4, min_row=3, max_row=3)  # entetes
    chart2.add_data(vals, from_rows=True)
    chart2.set_categories(cats)
    ws_stats.add_chart(chart2, "F3")

    wb.save(XLSX_FILENAME)
    print(f"  Fichier Excel (donnees + graphiques) : {XLSX_FILENAME}")


# ======================================================================
# Programme principal
# ======================================================================

def main():
    print("=" * 55)
    print(" BENCHMARK DEBIT (FPS) - Solution WebCam + PC")
    print("=" * 55)

    donnees = mesurer_fps()
    if not donnees:
        print("Aucune donnee mesuree.")
        return

    # Exclusion du warm-up
    donnees_utiles = [d for d in donnees if d[3] == 0]

    fps_global = [d[1] for d in donnees_utiles]
    fps_main = [d[1] for d in donnees_utiles if d[2] == 1]
    fps_sans = [d[1] for d in donnees_utiles if d[2] == 0]

    stats_global = calculer_stats(fps_global)
    stats_main = calculer_stats(fps_main)
    stats_sans = calculer_stats(fps_sans)

    print("\n" + "=" * 55)
    print(" RESULTATS (warm-up exclu)")
    print("=" * 55)
    afficher_stats("FPS global", stats_global)
    print()
    afficher_stats("FPS avec main", stats_main)
    print()
    afficher_stats("FPS sans main", stats_sans)

    exporter_csv(donnees)
    if stats_global:
        exporter_excel(donnees_utiles, stats_global, stats_main, stats_sans)


if __name__ == "__main__":
    main()
