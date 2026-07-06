"""
Benchmark - Metrique 1 : LATENCE (solution WebCam + PC)
========================================================
Mesure la latence decomposee en deux segments :

  - Segment A (vision)        : de cap.read() a classify_gesture()  [PC seul]
  - Segment B+C (communication): aller-retour serie PC -> robot -> ACK (ping/pong)

Prerequis cote robot : code.py doit repondre {"pong": N} a la reception
de {"ping": N}.

Deux phases successives :
  Phase 1 : N mesures du segment A (fais des gestes devant la webcam)
  Phase 2 : N mesures du segment B+C (automatique, aucun geste requis)

Les premieres mesures (warm-up) sont ignorees dans les statistiques car
MediaPipe/TensorFlow s'initialisent sur les premieres images.

Sorties :
  - un CSV avec toutes les mesures brutes ;
  - un Excel (.xlsx) avec les donnees separees par segment, les statistiques
    (moyenne, mediane, ecart-type, min, max) et des graphiques.
"""

import cv2
import mediapipe as mp
import serial
import json
import time
import csv
import statistics
from openpyxl import Workbook
from openpyxl.chart import LineChart, BarChart, Reference
from openpyxl.styles import Font, PatternFill, Alignment

# ----------------------------------------------------------------
# Parametres a adapter
# ----------------------------------------------------------------
SERIAL_PORT = "COM22"
BAUDRATE = 115200

N_VISION = 100      # nombre de mesures pour le segment A (vision)
N_PINGPONG = 100    # nombre de mesures pour le segment B+C (communication)
PING_TIMEOUT = 1.0  # delai max d'attente d'un pong (secondes)

# Nombre de premieres mesures a IGNORER (echauffement / warm-up).
# MediaPipe et TensorFlow s'initialisent sur les premieres images, ce qui
# provoque des pics de latence non representatifs du regime etabli.
WARMUP_VISION = 15
WARMUP_PINGPONG = 5

TIMESTAMP = time.strftime('%Y%m%d_%H%M%S')
CSV_FILENAME = f"benchmark_latence_webcam_{TIMESTAMP}.csv"
XLSX_FILENAME = f"benchmark_latence_webcam_{TIMESTAMP}.xlsx"

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


def calculer_stats(valeurs_ms):
    """Retourne un dictionnaire de statistiques pour une liste de mesures (ms)."""
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
        print(f"  {nom} : aucune mesure.")
        return
    print(f"  {nom} ({stats['n']} mesures apres warm-up) :")
    print(f"    Moyenne    : {stats['moyenne']:.2f} ms")
    print(f"    Mediane    : {stats['mediane']:.2f} ms")
    print(f"    Ecart-type : {stats['ecart_type']:.2f} ms")
    print(f"    Min        : {stats['min']:.2f} ms")
    print(f"    Max        : {stats['max']:.2f} ms")


# ======================================================================
# PHASE 1 : Segment A (vision)
# ======================================================================

def mesurer_segment_vision():
    print("\n=== PHASE 1 : Segment A (vision) ===")
    print(f"Objectif : {N_VISION} mesures (dont {WARMUP_VISION} de warm-up ignorees).")
    print("Fais des gestes varies devant la webcam.\n")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Erreur : impossible d'ouvrir la webcam.")
        return []

    mesures_ms = []  # toutes les mesures, warm-up inclus

    with mp_hands.Hands(
        max_num_hands=1,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.7,
    ) as hands:
        while len(mesures_ms) < N_VISION:
            t_debut = time.perf_counter()

            ret, frame = cap.read()
            if not ret:
                continue

            frame = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(rgb_frame)

            gesture_cmd = None
            gesture_name = "Aucune main detectee"
            if results.multi_hand_landmarks and results.multi_handedness:
                for hand_landmarks, handedness in zip(
                    results.multi_hand_landmarks, results.multi_handedness
                ):
                    label = handedness.classification[0].label
                    finger_states = get_finger_states(hand_landmarks, label)
                    gesture_cmd, gesture_name = classify_gesture(finger_states)

            t_fin = time.perf_counter()
            latence_ms = (t_fin - t_debut) * 1000.0
            mesures_ms.append(latence_ms)

            idx = len(mesures_ms)
            phase_txt = "WARM-UP" if idx <= WARMUP_VISION else "MESURE"

            if results.multi_hand_landmarks:
                for hand_landmarks in results.multi_hand_landmarks:
                    mp_draw.draw_landmarks(
                        frame, hand_landmarks, mp_hands.HAND_CONNECTIONS
                    )
            cv2.putText(frame, f"{phase_txt} {idx}/{N_VISION}", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            cv2.putText(frame, f"Segment A : {latence_ms:.1f} ms", (20, 80),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            cv2.imshow("Benchmark latence - Segment A (vision)", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("Interruption manuelle de la phase 1.")
                break

    cap.release()
    cv2.destroyAllWindows()
    return mesures_ms


# ======================================================================
# PHASE 2 : Segment B+C (communication) - ping/pong serie
# ======================================================================

def mesurer_segment_communication():
    print("\n=== PHASE 2 : Segment B+C (communication serie) ===")
    print(f"Objectif : {N_PINGPONG} mesures ping/pong "
          f"(dont {WARMUP_PINGPONG} de warm-up ignorees).\n")

    try:
        ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=0)
        print(f"Connecte au robot sur {SERIAL_PORT}")
    except serial.SerialException as e:
        print(f"Erreur de connexion serie : {e}")
        return []

    # Redemarrage logiciel du robot pour repartir sur une base propre
    time.sleep(0.3)
    ser.write(b'\x03')
    time.sleep(0.2)
    ser.write(b'\x02')
    time.sleep(0.2)
    ser.write(b'\x04')
    print("Redemarrage du robot, attente du demarrage de code.py...")

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

        # On vide le buffer des messages de statut accumules juste avant
        # d'envoyer le ping, pour que le pong soit la prochaine reponse utile.
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

                # Le robot envoie ses lignes via print(...encode()), ce qui
                # produit un prefixe b'...' autour du texte. On le retire.
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
            print(f"  {i + 1}/{N_PINGPONG} pings envoyes "
                  f"({len(mesures_ms)} pongs recus, {perdus} perdus)")

        time.sleep(0.02)

    ser.close()
    if perdus:
        print(f"  Attention : {perdus} ping(s) sans reponse (timeout).")
    return mesures_ms


# ======================================================================
# Export CSV et Excel
# ======================================================================

def exporter_csv(mesures_vision, mesures_comm):
    with open(CSV_FILENAME, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["segment", "mesure_num", "warmup", "latence_ms"])
        for i, v in enumerate(mesures_vision):
            warmup = 1 if i < WARMUP_VISION else 0
            writer.writerow(["vision_A", i, warmup, f"{v:.3f}"])
        for i, v in enumerate(mesures_comm):
            warmup = 1 if i < WARMUP_PINGPONG else 0
            writer.writerow(["communication_BC", i, warmup, f"{v:.3f}"])
    print(f"\n  Donnees brutes (CSV) : {CSV_FILENAME}")


def exporter_excel(vision_utiles, comm_utiles, stats_a, stats_bc):
    """Cree un fichier Excel avec donnees separees, statistiques et graphiques."""
    wb = Workbook()

    entete_fill = PatternFill("solid", start_color="4472C4")
    entete_font = Font(bold=True, color="FFFFFF")
    titre_font = Font(bold=True, size=13)

    # --- Feuille 1 : Donnees ---
    ws = wb.active
    ws.title = "Donnees"

    ws["A1"] = "Mesures de latence (apres warm-up)"
    ws["A1"].font = titre_font

    # Deux colonnes de donnees cote a cote : vision (A) et communication (B+C)
    ws["A3"] = "Mesure"
    ws["B3"] = "Segment A - vision (ms)"
    ws["D3"] = "Mesure"
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

    # --- Feuille 2 : Statistiques ---
    ws_stats = wb.create_sheet("Statistiques")
    ws_stats["A1"] = "Statistiques de latence"
    ws_stats["A1"].font = titre_font

    entetes = ["Metrique", "Segment A - vision (ms)", "Segment B+C - comm (ms)"]
    for col, txt in enumerate(entetes, start=1):
        c = ws_stats.cell(row=3, column=col, value=txt)
        c.fill = entete_fill
        c.font = entete_font
        c.alignment = Alignment(horizontal="center")

    lignes = [
        ("Nombre de mesures", stats_a["n"], stats_bc["n"]),
        ("Moyenne", round(stats_a["moyenne"], 2), round(stats_bc["moyenne"], 2)),
        ("Mediane", round(stats_a["mediane"], 2), round(stats_bc["mediane"], 2)),
        ("Ecart-type", round(stats_a["ecart_type"], 2), round(stats_bc["ecart_type"], 2)),
        ("Minimum", round(stats_a["min"], 2), round(stats_bc["min"], 2)),
        ("Maximum", round(stats_a["max"], 2), round(stats_bc["max"], 2)),
    ]
    for r, (nom, va, vbc) in enumerate(lignes, start=4):
        ws_stats.cell(row=r, column=1, value=nom).font = Font(bold=True)
        ws_stats.cell(row=r, column=2, value=va)
        ws_stats.cell(row=r, column=3, value=vbc)

    # Latence totale (moyenne A + moyenne B+C) via formule Excel
    r_total = 4 + len(lignes) + 1
    ws_stats.cell(row=r_total, column=1, value="Latence totale (moyennes)").font = Font(bold=True)
    # ligne "Moyenne" = ligne 5 ; on additionne B5 + C5
    ws_stats.cell(row=r_total, column=2, value="=B5+C5")

    for col in ("A", "B", "C"):
        ws_stats.column_dimensions[col].width = 26

    # --- Graphique 1 : courbe des latences vision au fil des mesures ---
    chart1 = LineChart()
    chart1.title = "Segment A (vision) - latence par mesure"
    chart1.x_axis.title = "Mesure"
    chart1.y_axis.title = "Latence (ms)"
    chart1.height = 8
    chart1.width = 16
    chart1.style = 12
    # Donnees : colonne B, de l'entete (ligne 3) jusqu'a la derniere mesure.
    # UNE seule serie (min_col == max_col), d'ou une courbe continue unique.
    data_ref = Reference(ws, min_col=2, max_col=2, min_row=3,
                         max_row=3 + len(vision_utiles))
    chart1.add_data(data_ref, titles_from_data=True)
    # Categories de l'axe X : les numeros de mesure (colonne A)
    cats1 = Reference(ws, min_col=1, min_row=4, max_row=3 + len(vision_utiles))
    chart1.set_categories(cats1)
    chart1.series[0].graphicalProperties.line.width = 15000  # trait fin lisible
    ws.add_chart(chart1, "G3")

    # --- Graphique 2 : courbe des latences communication ---
    chart2 = LineChart()
    chart2.title = "Segment B+C (communication) - latence par mesure"
    chart2.x_axis.title = "Mesure"
    chart2.y_axis.title = "Latence (ms)"
    chart2.height = 8
    chart2.width = 16
    chart2.style = 12
    data_ref2 = Reference(ws, min_col=5, max_col=5, min_row=3,
                          max_row=3 + len(comm_utiles))
    chart2.add_data(data_ref2, titles_from_data=True)
    cats2 = Reference(ws, min_col=4, min_row=4, max_row=3 + len(comm_utiles))
    chart2.set_categories(cats2)
    chart2.series[0].graphicalProperties.line.width = 15000
    ws.add_chart(chart2, "G20")

    # --- Graphique 3 : barres comparatives des moyennes (dans Statistiques) ---
    chart3 = BarChart()
    chart3.type = "col"
    chart3.title = "Comparaison des latences moyennes"
    chart3.y_axis.title = "Latence (ms)"
    chart3.height = 8
    chart3.width = 12
    chart3.legend = None
    # Ligne "Moyenne" (row=5), colonnes B et C = les deux segments.
    vals = Reference(ws_stats, min_col=2, max_col=3, min_row=5, max_row=5)
    cats = Reference(ws_stats, min_col=2, max_col=3, min_row=3, max_row=3)
    chart3.add_data(vals, from_rows=True)
    chart3.set_categories(cats)
    ws_stats.add_chart(chart3, "E3")

    wb.save(XLSX_FILENAME)
    print(f"  Fichier Excel (donnees + graphiques) : {XLSX_FILENAME}")


# ======================================================================
# Programme principal
# ======================================================================

def main():
    print("=" * 55)
    print(" BENCHMARK LATENCE - Solution WebCam + PC")
    print("=" * 55)

    mesures_vision = mesurer_segment_vision()
    mesures_comm = mesurer_segment_communication()

    # On retire les mesures de warm-up avant de calculer les statistiques
    vision_utiles = mesures_vision[WARMUP_VISION:] if len(mesures_vision) > WARMUP_VISION else mesures_vision
    comm_utiles = mesures_comm[WARMUP_PINGPONG:] if len(mesures_comm) > WARMUP_PINGPONG else mesures_comm

    stats_a = calculer_stats(vision_utiles)
    stats_bc = calculer_stats(comm_utiles)

    print("\n" + "=" * 55)
    print(" RESULTATS (warm-up exclu)")
    print("=" * 55)
    afficher_stats("Segment A (vision)", stats_a)
    print()
    afficher_stats("Segment B+C (communication)", stats_bc)

    if stats_a and stats_bc:
        total_moy = stats_a["moyenne"] + stats_bc["moyenne"]
        total_med = stats_a["mediane"] + stats_bc["mediane"]
        print(f"\n  Latence logicielle totale (moyennes) : {total_moy:.2f} ms")
        print(f"  Latence logicielle totale (medianes) : {total_med:.2f} ms")
        print("  (delai mecanique final non inclus)")

    # Exports
    exporter_csv(mesures_vision, mesures_comm)
    if stats_a and stats_bc:
        exporter_excel(vision_utiles, comm_utiles, stats_a, stats_bc)


if __name__ == "__main__":
    main()