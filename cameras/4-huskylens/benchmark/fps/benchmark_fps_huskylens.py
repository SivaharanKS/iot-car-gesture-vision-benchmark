"""
Benchmark - Metrique 2 : DEBIT / FPS (solution HuskyLens)
===========================================================
Mesure la frequence a laquelle le PC peut lire un nouveau resultat aupres
de la HuskyLens (boucle de requetes hl.learned()), adaptee de la version
webcam (cap.read() + MediaPipe).

Le FPS instantane est releve a chaque requete (1 / duree de la boucle) et
classe selon qu'un geste actif est detecte (ID 1 a 4) ou non (ID 5/neutre
ou aucune detection), afin de distinguer :
  - FPS avec geste actif : cas d'usage reel du controle gestuel
  - FPS sans geste (neutre)  : reference

La mesure dure DUREE_MESURE secondes. Les premieres secondes (echauffement
de la connexion serie) sont exclues des statistiques.

Sorties :
  - un CSV avec le FPS de chaque requete ;
  - un Excel (.xlsx) avec les donnees, les statistiques et des graphiques.
"""

import time
import csv
import statistics
from huskylib import HuskyLensLibrary
from openpyxl import Workbook
from openpyxl.chart import LineChart, BarChart, Reference
from openpyxl.styles import Font, PatternFill, Alignment

# ----------------------------------------------------------------
# Parametres a adapter
# ----------------------------------------------------------------
COM_HUSKY = "COM25"   # port serie de la HuskyLens

DUREE_MESURE = 30.0   # duree de la mesure en secondes (regime etabli)
WARMUP_SEC = 3.0      # duree d'echauffement ignoree au debut (secondes)

ID_NEUTRE = 5         # ID de la classe neutre (voir entrainement_huskylens.py)

TIMESTAMP = time.strftime('%Y%m%d_%H%M%S')
CSV_FILENAME = f"benchmark_fps_huskylens_{TIMESTAMP}.csv"
XLSX_FILENAME = f"benchmark_fps_huskylens_{TIMESTAMP}.xlsx"


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
    print(f"  {nom} ({stats['n']} requetes) :")
    print(f"    FPS moyen    : {stats['moyenne']:.2f}")
    print(f"    FPS median   : {stats['mediane']:.2f}")
    print(f"    Ecart-type   : {stats['ecart_type']:.2f}")
    print(f"    FPS min      : {stats['min']:.2f}")
    print(f"    FPS max      : {stats['max']:.2f}")


# ======================================================================
# Mesure du FPS
# ======================================================================

def mesurer_fps():
    print("\n=== MESURE DU DEBIT (FPS) - HuskyLens ===")
    print(f"Duree : {DUREE_MESURE:.0f} s (dont {WARMUP_SEC:.0f} s de warm-up ignorees).")
    print("Alterne entre 'geste actif' et 'position neutre' pour mesurer les deux cas.\n")

    try:
        hl = HuskyLensLibrary("SERIAL", COM_HUSKY)
        print(hl.knock())
        hl.algorthim("ALGORITHM_OBJECT_CLASSIFICATION")
    except Exception as e:
        print(f"Erreur de connexion a la HuskyLens ({COM_HUSKY}) : {e}")
        return []

    # Chaque entree : (temps_relatif_s, fps_instantane, geste_actif 0/1, warmup 0/1)
    donnees = []

    t_start = time.perf_counter()
    t_prev = t_start

    while True:
        try:
            objet = hl.learned()
        except Exception:
            objet = None

        detected_id = getattr(objet, "ID", None) if objet else None
        geste_actif = 1 if (detected_id is not None and detected_id != ID_NEUTRE) else 0

        t_now = time.perf_counter()
        dt = t_now - t_prev
        t_prev = t_now
        fps = (1.0 / dt) if dt > 0 else 0.0

        t_rel = t_now - t_start
        warmup = 1 if t_rel < WARMUP_SEC else 0
        donnees.append((t_rel, fps, geste_actif, warmup))

        idx = len(donnees)
        if idx % 50 == 0:
            phase = "WARM-UP" if warmup else "MESURE"
            print(f"  {phase}  t={t_rel:.1f}s / {DUREE_MESURE:.0f}s  "
                  f"FPS={fps:.1f}  Geste actif={'OUI' if geste_actif else 'non'}")

        if t_rel >= DUREE_MESURE:
            break

    return donnees


# ======================================================================
# Export CSV et Excel
# ======================================================================

def exporter_csv(donnees):
    with open(CSV_FILENAME, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["temps_s", "fps", "geste_actif", "warmup"])
        for t_rel, fps, actif, warmup in donnees:
            writer.writerow([f"{t_rel:.3f}", f"{fps:.2f}", actif, warmup])
    print(f"\n  Donnees brutes (CSV) : {CSV_FILENAME}")


def exporter_excel(donnees_utiles, stats_global, stats_actif, stats_neutre):
    wb = Workbook()

    entete_fill = PatternFill("solid", start_color="4472C4")
    entete_font = Font(bold=True, color="FFFFFF")
    titre_font = Font(bold=True, size=13)

    ws = wb.active
    ws.title = "Donnees"
    ws["A1"] = "Mesure du debit (FPS) HuskyLens - regime etabli (warm-up exclu)"
    ws["A1"].font = titre_font

    entetes = ["Requete", "Temps (s)", "FPS", "Geste actif"]
    for col, txt in enumerate(entetes, start=1):
        c = ws.cell(row=3, column=col, value=txt)
        c.fill = entete_fill
        c.font = entete_font
        c.alignment = Alignment(horizontal="center")

    for i, (t_rel, fps, actif, _warmup) in enumerate(donnees_utiles):
        ws.cell(row=4 + i, column=1, value=i + 1)
        ws.cell(row=4 + i, column=2, value=round(t_rel, 3))
        ws.cell(row=4 + i, column=3, value=round(fps, 2))
        ws.cell(row=4 + i, column=4, value=actif)

    for col, w in (("A", 10), ("B", 12), ("C", 10), ("D", 14)):
        ws.column_dimensions[col].width = w

    n = len(donnees_utiles)

    ws_stats = wb.create_sheet("Statistiques")
    ws_stats["A1"] = "Statistiques du debit (FPS) HuskyLens"
    ws_stats["A1"].font = titre_font

    entetes_s = ["Metrique", "Global", "Geste actif", "Neutre"]
    for col, txt in enumerate(entetes_s, start=1):
        c = ws_stats.cell(row=3, column=col, value=txt)
        c.fill = entete_fill
        c.font = entete_font
        c.alignment = Alignment(horizontal="center")

    def ligne_stat(nom, cle):
        return (
            nom,
            round(stats_global[cle], 2) if stats_global else None,
            round(stats_actif[cle], 2) if stats_actif else None,
            round(stats_neutre[cle], 2) if stats_neutre else None,
        )

    lignes = [
        ligne_stat("Nombre de requetes", "n"),
        ligne_stat("FPS moyen", "moyenne"),
        ligne_stat("FPS median", "mediane"),
        ligne_stat("Ecart-type", "ecart_type"),
        ligne_stat("FPS min", "min"),
        ligne_stat("FPS max", "max"),
    ]
    for r, (nom, g, a, ne) in enumerate(lignes, start=4):
        ws_stats.cell(row=r, column=1, value=nom).font = Font(bold=True)
        ws_stats.cell(row=r, column=2, value=g)
        ws_stats.cell(row=r, column=3, value=a)
        ws_stats.cell(row=r, column=4, value=ne)

    for col in ("A", "B", "C", "D"):
        ws_stats.column_dimensions[col].width = 18

    # --- Graphique 1 : FPS instantane au fil du temps (courbe unique) ---
    chart1 = LineChart()
    chart1.title = "Debit (FPS) HuskyLens au fil des requetes"
    chart1.x_axis.title = "Requete"
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

    # --- Graphique 2 : barres comparatives FPS moyen (global / actif / neutre) ---
    chart2 = BarChart()
    chart2.type = "col"
    chart2.title = "FPS moyen selon la presence d'un geste actif"
    chart2.y_axis.title = "FPS"
    chart2.height = 8
    chart2.width = 12
    chart2.legend = None
    vals = Reference(ws_stats, min_col=2, max_col=4, min_row=5, max_row=5)
    cats = Reference(ws_stats, min_col=2, max_col=4, min_row=3, max_row=3)
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
    print(" BENCHMARK DEBIT (FPS) - Solution HuskyLens")
    print("=" * 55)

    donnees = mesurer_fps()
    if not donnees:
        print("Aucune donnee mesuree.")
        return

    donnees_utiles = [d for d in donnees if d[3] == 0]

    fps_global = [d[1] for d in donnees_utiles]
    fps_actif = [d[1] for d in donnees_utiles if d[2] == 1]
    fps_neutre = [d[1] for d in donnees_utiles if d[2] == 0]

    stats_global = calculer_stats(fps_global)
    stats_actif = calculer_stats(fps_actif)
    stats_neutre = calculer_stats(fps_neutre)

    print("\n" + "=" * 55)
    print(" RESULTATS (warm-up exclu)")
    print("=" * 55)
    afficher_stats("FPS global", stats_global)
    print()
    afficher_stats("FPS geste actif", stats_actif)
    print()
    afficher_stats("FPS neutre", stats_neutre)

    exporter_csv(donnees)
    if stats_global:
        exporter_excel(donnees_utiles, stats_global, stats_actif, stats_neutre)


if __name__ == "__main__":
    main()
