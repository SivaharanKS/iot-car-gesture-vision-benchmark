"""
Benchmark - Metrique 3 : FIABILITE DE RECONNAISSANCE (solution WebCam + PC)
============================================================================
Construit une matrice de confusion entre le geste VOULU (indique par
l'utilisateur via une touche) et le geste DETECTE par le systeme.

Protocole (mode manuel) :
  - Montre un geste devant la webcam.
  - Appuie sur la touche du geste que tu VOULAIS faire :
        1 = Avancer  (poing ferme)
        2 = Stop     (main ouverte)
        3 = Gauche   (index + pouce)
        4 = Droite   (index + auriculaire)
  - Le script enregistre (voulu, detecte) au moment de l'appui.
  - Objectif : N_PAR_GESTE essais pour chacun des 4 gestes.
  - Touche 'q' pour arreter avant la fin.

Sorties :
  - un CSV avec chaque essai (voulu, detecte, correct) ;
  - un Excel (.xlsx) avec la matrice de confusion (heatmap) et le taux global.
"""

import cv2
import mediapipe as mp
import csv
import time
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# ----------------------------------------------------------------
# Parametres
# ----------------------------------------------------------------
N_PAR_GESTE = 20  # nombre d'essais vises pour chaque geste

TIMESTAMP = time.strftime('%Y%m%d_%H%M%S')
CSV_FILENAME = f"benchmark_fiabilite_webcam_{TIMESTAMP}.csv"
XLSX_FILENAME = f"benchmark_fiabilite_webcam_{TIMESTAMP}.xlsx"

# Les 4 gestes (ordre fixe pour la matrice)
GESTES = ["forward", "stop", "turn_left", "turn_right"]
GESTE_LABEL = {
    "forward": "Avancer",
    "stop": "Stop",
    "turn_left": "Gauche",
    "turn_right": "Droite",
}
# Touche -> geste voulu
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
    return None  # non reconnu


# ======================================================================
# Acquisition des essais
# ======================================================================

def acquerir_essais():
    print("\n=== MESURE DE FIABILITE (matrice de confusion) ===")
    print("Montre un geste, puis appuie sur la touche du geste VOULU :")
    print("   1 = Avancer   2 = Stop   3 = Gauche   4 = Droite")
    print(f"Objectif : {N_PAR_GESTE} essais par geste. Touche 'q' pour arreter.\n")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Erreur : impossible d'ouvrir la webcam.")
        return []

    essais = []  # (voulu, detecte)
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

            # Affichage du geste detecte en direct
            det_txt = GESTE_LABEL.get(detecte, "Non reconnu")
            cv2.putText(frame, f"Detecte : {det_txt}", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

            # Affichage des compteurs
            y = 80
            total = sum(compteur.values())
            for g in GESTES:
                txt = f"{GESTE_LABEL[g]} : {compteur[g]}/{N_PAR_GESTE}"
                couleur = (0, 255, 0) if compteur[g] >= N_PAR_GESTE else (255, 255, 255)
                cv2.putText(frame, txt, (20, y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, couleur, 2)
                y += 30
            cv2.putText(frame, "Touches : 1=Av 2=Stop 3=Gau 4=Dro | q=fin",
                        (20, y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

            cv2.imshow("Benchmark fiabilite - WebCam", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                print("Arret manuel de l'acquisition.")
                break
            if key in TOUCHE_GESTE:
                voulu = TOUCHE_GESTE[key]
                essais.append((voulu, detecte))
                compteur[voulu] += 1
                det_print = GESTE_LABEL.get(detecte, "Non reconnu")
                ok = "OK" if voulu == detecte else "X"
                print(f"  [{ok}] Voulu={GESTE_LABEL[voulu]:8s} "
                      f"Detecte={det_print}  "
                      f"({compteur[voulu]}/{N_PAR_GESTE})")

                # Fin automatique si tous les gestes ont atteint l'objectif
                if all(compteur[g] >= N_PAR_GESTE for g in GESTES):
                    print("\nObjectif atteint pour les 4 gestes.")
                    break

    cap.release()
    cv2.destroyAllWindows()
    return essais


# ======================================================================
# Construction de la matrice de confusion
# ======================================================================

def construire_matrice(essais):
    """Retourne la matrice (dict) : matrice[voulu][detecte] = compte.
    'detecte' peut valoir None (non reconnu)."""
    colonnes = GESTES + [None]  # None = colonne "non detecte"
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
    print(" MATRICE DE CONFUSION")
    print("=" * 55)
    colonnes = GESTES + [None]
    entete = "Voulu \\ Det. | " + " ".join(
        f"{GESTE_LABEL.get(d, 'NonDet'):>7s}" for d in colonnes
    )
    print(entete)
    print("-" * len(entete))
    for v in GESTES:
        ligne = f"{GESTE_LABEL[v]:12s} | "
        ligne += " ".join(f"{matrice[v][d]:>7d}" for d in colonnes)
        print(ligne)

    # Taux de reconnaissance global
    total = len(essais)
    corrects = sum(1 for voulu, detecte in essais if voulu == detecte)
    taux = (corrects / total * 100) if total else 0.0
    print("-" * len(entete))
    print(f"Taux de reconnaissance global : {corrects}/{total} = {taux:.1f} %")
    return taux, corrects, total


# ======================================================================
# Export CSV et Excel
# ======================================================================

def exporter_csv(essais):
    with open(CSV_FILENAME, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["essai", "voulu", "detecte", "correct"])
        for i, (voulu, detecte) in enumerate(essais):
            det = detecte if detecte is not None else "non_detecte"
            correct = 1 if voulu == detecte else 0
            writer.writerow([i + 1, voulu, det, correct])
    print(f"\n  Donnees brutes (CSV) : {CSV_FILENAME}")


def exporter_excel(matrice, essais, taux, corrects, total):
    wb = Workbook()
    entete_fill = PatternFill("solid", start_color="4472C4")
    entete_font = Font(bold=True, color="FFFFFF")
    titre_font = Font(bold=True, size=13)
    diag_fill = PatternFill("solid", start_color="C6EFCE")   # vert (corrects)
    err_fill = PatternFill("solid", start_color="FFC7CE")    # rouge (erreurs)
    bord = Border(*[Side(style="thin")] * 4)

    ws = wb.active
    ws.title = "Matrice de confusion"
    ws["A1"] = "Matrice de confusion - Fiabilite WebCam"
    ws["A1"].font = titre_font

    colonnes = GESTES + [None]
    col_labels = [GESTE_LABEL.get(d, "Non detecte") for d in colonnes]

    # En-tete
    ws.cell(row=3, column=1, value="Voulu \\ Detecte").fill = entete_fill
    ws.cell(row=3, column=1).font = entete_font
    for j, lab in enumerate(col_labels, start=2):
        c = ws.cell(row=3, column=j, value=lab)
        c.fill = entete_fill
        c.font = entete_font
        c.alignment = Alignment(horizontal="center")

    # Lignes de la matrice
    for i, v in enumerate(GESTES, start=4):
        cv_ = ws.cell(row=i, column=1, value=GESTE_LABEL[v])
        cv_.fill = entete_fill
        cv_.font = entete_font
        for j, d in enumerate(colonnes, start=2):
            val = matrice[v][d]
            c = ws.cell(row=i, column=j, value=val)
            c.alignment = Alignment(horizontal="center")
            c.border = bord
            # Coloration : vert sur la diagonale (v == d), rouge si erreur non nulle
            if v == d:
                c.fill = diag_fill
            elif val > 0:
                c.fill = err_fill

    # Taux global
    r = 4 + len(GESTES) + 1
    ws.cell(row=r, column=1, value="Taux de reconnaissance global").font = Font(bold=True)
    ws.cell(row=r, column=2, value=f"{taux:.1f} %")
    ws.cell(row=r + 1, column=1, value="Essais corrects / total")
    ws.cell(row=r + 1, column=2, value=f"{corrects} / {total}")

    ws.column_dimensions["A"].width = 18
    for col in "BCDEF":
        ws.column_dimensions[col].width = 13

    # --- Feuille 2 : taux de reconnaissance par geste (barres) ---
    ws2 = wb.create_sheet("Taux par geste")
    ws2["A1"] = "Taux de reconnaissance par geste"
    ws2["A1"].font = titre_font
    ws2.cell(row=3, column=1, value="Geste").fill = entete_fill
    ws2.cell(row=3, column=1).font = entete_font
    ws2.cell(row=3, column=2, value="Taux (%)").fill = entete_fill
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
    chart.title = "Taux de reconnaissance par geste"
    chart.y_axis.title = "Taux (%)"
    chart.height = 8
    chart.width = 12
    chart.legend = None
    vals = Reference(ws2, min_col=2, min_row=3, max_row=3 + len(GESTES))
    cats = Reference(ws2, min_col=1, min_row=4, max_row=3 + len(GESTES))
    chart.add_data(vals, titles_from_data=True)
    chart.set_categories(cats)
    ws2.add_chart(chart, "D3")

    wb.save(XLSX_FILENAME)
    print(f"  Fichier Excel (matrice + graphique) : {XLSX_FILENAME}")


# ======================================================================
# Programme principal
# ======================================================================

def main():
    print("=" * 55)
    print(" BENCHMARK FIABILITE - Solution WebCam + PC")
    print("=" * 55)

    essais = acquerir_essais()
    if not essais:
        print("Aucun essai enregistre.")
        return

    matrice = construire_matrice(essais)
    taux, corrects, total = afficher_matrice(matrice, essais)

    exporter_csv(essais)
    exporter_excel(matrice, essais, taux, corrects, total)


if __name__ == "__main__":
    main()
