"""
Benchmark - Metrique 3 : FIABILITE DE RECONNAISSANCE (solution HuskyLens)
============================================================================
Construit une matrice de confusion entre le geste VOULU (indique par
l'utilisateur via une touche) et le geste DETECTE par la HuskyLens.
Adapte de la version webcam~: la HuskyLens n'ayant pas de fenetre PC
(elle dispose de son propre ecran), la lecture de touche se fait en
console de facon non bloquante (module msvcrt, Windows), pendant
l'interrogation continue de la camera.

Protocole (mode manuel) :
  - Montre un geste devant la HuskyLens (regarde son ecran integre).
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

import msvcrt
import csv
import time
from huskylib import HuskyLensLibrary
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# ----------------------------------------------------------------
# Parametres
# ----------------------------------------------------------------
COM_HUSKY = "COM25"  # port serie de la HuskyLens

N_PAR_GESTE = 20  # nombre d'essais vises pour chaque geste
ID_NEUTRE = 5     # ID de la classe neutre (non retenu comme geste valide)

TIMESTAMP = time.strftime('%Y%m%d_%H%M%S')
CSV_FILENAME = f"benchmark_fiabilite_huskylens_{TIMESTAMP}.csv"
XLSX_FILENAME = f"benchmark_fiabilite_huskylens_{TIMESTAMP}.xlsx"

# Les 4 gestes (ordre fixe pour la matrice), memes noms que la solution WebCam
GESTES = ["forward", "stop", "turn_left", "turn_right"]
GESTE_LABEL = {
    "forward": "Avancer",
    "stop": "Stop",
    "turn_left": "Gauche",
    "turn_right": "Droite",
}
ID_TO_GESTE = {
    1: "forward",
    2: "stop",
    3: "turn_left",
    4: "turn_right",
}
# Touche -> geste voulu
TOUCHE_GESTE = {
    b'1': "forward",
    b'2': "stop",
    b'3': "turn_left",
    b'4': "turn_right",
}


def lire_id_geste(hl):
    """Interroge la HuskyLens et renvoie l'ID detecte, ou None."""
    try:
        objet = hl.learned()
    except Exception:
        return None
    if not objet:
        return None
    return getattr(objet, "ID", None)


# ======================================================================
# Acquisition des essais
# ======================================================================

def acquerir_essais():
    print("\n=== MESURE DE FIABILITE (matrice de confusion) - HuskyLens ===")
    print("Montre un geste, puis appuie sur la touche du geste VOULU :")
    print("   1 = Avancer   2 = Stop   3 = Gauche   4 = Droite")
    print(f"Objectif : {N_PAR_GESTE} essais par geste. Touche 'q' pour arreter.\n")

    try:
        hl = HuskyLensLibrary("SERIAL", COM_HUSKY)
        print(hl.knock())
        hl.algorthim("ALGORITHM_OBJECT_CLASSIFICATION")
    except Exception as e:
        print(f"Erreur de connexion a la HuskyLens ({COM_HUSKY}) : {e}")
        return []

    essais = []  # (voulu, detecte)
    compteur = {g: 0 for g in GESTES}
    dernier_affiche = None
    dernier_affichage_temps = 0.0
    AFFICHAGE_INTERVAL = 0.5

    while True:
        detected_id = lire_id_geste(hl)
        detecte = ID_TO_GESTE.get(detected_id) if detected_id != ID_NEUTRE else None

        # Affichage limite du geste detecte en direct (console)
        now = time.monotonic()
        if detecte != dernier_affiche or (now - dernier_affichage_temps) > AFFICHAGE_INTERVAL:
            det_txt = GESTE_LABEL.get(detecte, "Non reconnu")
            compteurs_txt = " | ".join(
                f"{GESTE_LABEL[g]}:{compteur[g]}/{N_PAR_GESTE}" for g in GESTES
            )
            print(f"\rDetecte : {det_txt:10s} || {compteurs_txt}", end="", flush=True)
            dernier_affiche = detecte
            dernier_affichage_temps = now

        # Lecture non bloquante du clavier (Windows)
        if msvcrt.kbhit():
            touche = msvcrt.getch()
            if touche == b'q':
                print("\nArret manuel de l'acquisition.")
                break
            if touche in TOUCHE_GESTE:
                voulu = TOUCHE_GESTE[touche]
                essais.append((voulu, detecte))
                compteur[voulu] += 1
                det_print = GESTE_LABEL.get(detecte, "Non reconnu")
                ok = "OK" if voulu == detecte else "X"
                print(f"\n  [{ok}] Voulu={GESTE_LABEL[voulu]:8s} "
                      f"Detecte={det_print}  "
                      f"({compteur[voulu]}/{N_PAR_GESTE})")

                if all(compteur[g] >= N_PAR_GESTE for g in GESTES):
                    print("\nObjectif atteint pour les 4 gestes.")
                    break

    return essais


# ======================================================================
# Construction de la matrice de confusion
# (logique identique a la solution WebCam)
# ======================================================================

def construire_matrice(essais):
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
    print(" MATRICE DE CONFUSION - HuskyLens")
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

    total = len(essais)
    corrects = sum(1 for voulu, detecte in essais if voulu == detecte)
    taux = (corrects / total * 100) if total else 0.0
    print("-" * len(entete))
    print(f"Taux de reconnaissance global : {corrects}/{total} = {taux:.1f} %")
    return taux, corrects, total


# ======================================================================
# Export CSV et Excel (identique a la solution WebCam)
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
    diag_fill = PatternFill("solid", start_color="C6EFCE")
    err_fill = PatternFill("solid", start_color="FFC7CE")
    bord = Border(*[Side(style="thin")] * 4)

    ws = wb.active
    ws.title = "Matrice de confusion"
    ws["A1"] = "Matrice de confusion - Fiabilite HuskyLens"
    ws["A1"].font = titre_font

    colonnes = GESTES + [None]
    col_labels = [GESTE_LABEL.get(d, "Non detecte") for d in colonnes]

    ws.cell(row=3, column=1, value="Voulu \\ Detecte").fill = entete_fill
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
    ws.cell(row=r, column=1, value="Taux de reconnaissance global").font = Font(bold=True)
    ws.cell(row=r, column=2, value=f"{taux:.1f} %")
    ws.cell(row=r + 1, column=1, value="Essais corrects / total")
    ws.cell(row=r + 1, column=2, value=f"{corrects} / {total}")

    ws.column_dimensions["A"].width = 18
    for col in "BCDEF":
        ws.column_dimensions[col].width = 13

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
    print(" BENCHMARK FIABILITE - Solution HuskyLens")
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
