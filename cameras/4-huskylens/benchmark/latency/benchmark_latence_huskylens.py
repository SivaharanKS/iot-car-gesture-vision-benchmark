"""
Benchmark - Metrique 1 : LATENCE (solution HuskyLens)
=======================================================
Mesure la latence decomposee en deux segments, adaptee a l'architecture
HuskyLens (traitement entierement embarque dans la camera) :

  - Segment A (requete HuskyLens) : temps de reponse a une sollicitation
    serie aupres de la HuskyLens (hl.learned()), mesure sur le PC. Ce
    segment remplace le segment "vision" de la solution WebCam, la
    HuskyLens ayant deja determine le geste en interne.
  - Segment B+C (communication) : aller-retour serie PC -> robot -> ACK
    (ping/pong), strictement identique au mecanisme utilise pour la
    solution WebCam (code.py cote robot n'a pas ete modifie).

Prerequis cote robot : code.py doit repondre {"pong": N} a la reception
de {"ping": N} (deja en place, inchange depuis la solution WebCam).

Deux phases successives :
  Phase 1 : N mesures du segment A (requetes HuskyLens)
  Phase 2 : N mesures du segment B+C (automatique, ping/pong)

Les premieres mesures (warm-up) sont ignorees dans les statistiques.

Sorties :
  - un CSV avec toutes les mesures brutes ;
  - un Excel (.xlsx) avec les donnees separees par segment, les statistiques
    (moyenne, mediane, ecart-type, min, max) et des graphiques.
"""

import time
import json
import csv
import serial
import statistics
from huskylib import HuskyLensLibrary
from openpyxl import Workbook
from openpyxl.chart import LineChart, BarChart, Reference
from openpyxl.styles import Font, PatternFill, Alignment

# ----------------------------------------------------------------
# Parametres a adapter
# ----------------------------------------------------------------
COM_HUSKY = "COM25"   # port serie de la HuskyLens
COM_ROBOT = "COM22"   # port serie du robot RP2040
BAUDRATE_ROBOT = 115200

N_HUSKY = 100        # nombre de mesures pour le segment A (requetes HuskyLens)
N_PINGPONG = 100     # nombre de mesures pour le segment B+C (communication)
PING_TIMEOUT = 1.0   # delai max d'attente d'un pong (secondes)

# Nombre de premieres mesures a IGNORER (echauffement / warm-up)
WARMUP_HUSKY = 15
WARMUP_PINGPONG = 5

TIMESTAMP = time.strftime('%Y%m%d_%H%M%S')
CSV_FILENAME = f"benchmark_latence_huskylens_{TIMESTAMP}.csv"
XLSX_FILENAME = f"benchmark_latence_huskylens_{TIMESTAMP}.xlsx"


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
# PHASE 1 : Segment A (requete HuskyLens)
# ======================================================================

def mesurer_segment_huskylens():
    print("\n=== PHASE 1 : Segment A (requete HuskyLens) ===")
    print(f"Objectif : {N_HUSKY} mesures (dont {WARMUP_HUSKY} de warm-up ignorees).")
    print("Garde un geste stable devant la camera pendant cette phase.\n")

    try:
        hl = HuskyLensLibrary("SERIAL", COM_HUSKY)
        print(hl.knock())
        hl.algorthim("ALGORITHM_OBJECT_CLASSIFICATION")
    except Exception as e:
        print(f"Erreur de connexion a la HuskyLens ({COM_HUSKY}) : {e}")
        return []

    mesures_ms = []

    while len(mesures_ms) < N_HUSKY:
        t_debut = time.perf_counter()
        try:
            hl.learned()
        except Exception:
            continue
        t_fin = time.perf_counter()

        latence_ms = (t_fin - t_debut) * 1000.0
        mesures_ms.append(latence_ms)

        idx = len(mesures_ms)
        phase_txt = "WARM-UP" if idx <= WARMUP_HUSKY else "MESURE"
        if idx % 10 == 0 or idx <= WARMUP_HUSKY:
            print(f"  {phase_txt} {idx}/{N_HUSKY} : {latence_ms:.2f} ms")

    return mesures_ms


# ======================================================================
# PHASE 2 : Segment B+C (communication) - ping/pong serie
# (identique au mecanisme utilise pour la solution WebCam)
# ======================================================================

def mesurer_segment_communication():
    print("\n=== PHASE 2 : Segment B+C (communication serie) ===")
    print(f"Objectif : {N_PINGPONG} mesures ping/pong (automatique).\n")

    try:
        ser = serial.Serial(COM_ROBOT, BAUDRATE_ROBOT, timeout=0)
        print(f"Connecte au robot sur {COM_ROBOT}")
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

def exporter_csv(mesures_husky, mesures_comm):
    with open(CSV_FILENAME, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["segment", "mesure_num", "warmup", "latence_ms"])
        for i, v in enumerate(mesures_husky):
            warmup = 1 if i < WARMUP_HUSKY else 0
            writer.writerow(["huskylens_A", i, warmup, f"{v:.3f}"])
        for i, v in enumerate(mesures_comm):
            warmup = 1 if i < WARMUP_PINGPONG else 0
            writer.writerow(["communication_BC", i, warmup, f"{v:.3f}"])
    print(f"\n  Donnees brutes (CSV) : {CSV_FILENAME}")


def exporter_excel(husky_utiles, comm_utiles, stats_a, stats_bc):
    wb = Workbook()

    entete_fill = PatternFill("solid", start_color="4472C4")
    entete_font = Font(bold=True, color="FFFFFF")
    titre_font = Font(bold=True, size=13)

    ws = wb.active
    ws.title = "Donnees"
    ws["A1"] = "Mesures de latence HuskyLens (apres warm-up)"
    ws["A1"].font = titre_font

    ws["A3"] = "Mesure"
    ws["B3"] = "Segment A - HuskyLens (ms)"
    ws["D3"] = "Mesure"
    ws["E3"] = "Segment B+C - comm (ms)"
    for cell in ("A3", "B3", "D3", "E3"):
        ws[cell].fill = entete_fill
        ws[cell].font = entete_font
        ws[cell].alignment = Alignment(horizontal="center")

    for i, v in enumerate(husky_utiles):
        ws.cell(row=4 + i, column=1, value=i + 1)
        ws.cell(row=4 + i, column=2, value=round(v, 3))
    for i, v in enumerate(comm_utiles):
        ws.cell(row=4 + i, column=4, value=i + 1)
        ws.cell(row=4 + i, column=5, value=round(v, 3))

    ws.column_dimensions["A"].width = 10
    ws.column_dimensions["B"].width = 24
    ws.column_dimensions["D"].width = 10
    ws.column_dimensions["E"].width = 22

    ws_stats = wb.create_sheet("Statistiques")
    ws_stats["A1"] = "Statistiques de latence HuskyLens"
    ws_stats["A1"].font = titre_font

    entetes = ["Metrique", "Segment A - HuskyLens (ms)", "Segment B+C - comm (ms)"]
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

    r_total = 4 + len(lignes) + 1
    ws_stats.cell(row=r_total, column=1, value="Latence totale (moyennes)").font = Font(bold=True)
    ws_stats.cell(row=r_total, column=2, value="=B5+C5")

    for col in ("A", "B", "C"):
        ws_stats.column_dimensions[col].width = 28

    chart1 = LineChart()
    chart1.title = "Segment A (HuskyLens) - latence par mesure"
    chart1.x_axis.title = "Mesure"
    chart1.y_axis.title = "Latence (ms)"
    chart1.height = 8
    chart1.width = 16
    chart1.style = 12
    data_ref = Reference(ws, min_col=2, max_col=2, min_row=3, max_row=3 + len(husky_utiles))
    chart1.add_data(data_ref, titles_from_data=True)
    cats1 = Reference(ws, min_col=1, min_row=4, max_row=3 + len(husky_utiles))
    chart1.set_categories(cats1)
    chart1.series[0].graphicalProperties.line.width = 15000
    ws.add_chart(chart1, "G3")

    chart2 = LineChart()
    chart2.title = "Segment B+C (communication) - latence par mesure"
    chart2.x_axis.title = "Mesure"
    chart2.y_axis.title = "Latence (ms)"
    chart2.height = 8
    chart2.width = 16
    chart2.style = 12
    data_ref2 = Reference(ws, min_col=5, max_col=5, min_row=3, max_row=3 + len(comm_utiles))
    chart2.add_data(data_ref2, titles_from_data=True)
    cats2 = Reference(ws, min_col=4, min_row=4, max_row=3 + len(comm_utiles))
    chart2.set_categories(cats2)
    chart2.series[0].graphicalProperties.line.width = 15000
    ws.add_chart(chart2, "G20")

    chart3 = BarChart()
    chart3.type = "col"
    chart3.title = "Comparaison des latences moyennes"
    chart3.y_axis.title = "Latence (ms)"
    chart3.height = 8
    chart3.width = 12
    chart3.legend = None
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
    print(" BENCHMARK LATENCE - Solution HuskyLens")
    print("=" * 55)

    mesures_husky = mesurer_segment_huskylens()
    mesures_comm = mesurer_segment_communication()

    husky_utiles = mesures_husky[WARMUP_HUSKY:] if len(mesures_husky) > WARMUP_HUSKY else mesures_husky
    comm_utiles = mesures_comm[WARMUP_PINGPONG:] if len(mesures_comm) > WARMUP_PINGPONG else mesures_comm

    stats_a = calculer_stats(husky_utiles)
    stats_bc = calculer_stats(comm_utiles)

    print("\n" + "=" * 55)
    print(" RESULTATS (warm-up exclu)")
    print("=" * 55)
    afficher_stats("Segment A (HuskyLens)", stats_a)
    print()
    afficher_stats("Segment B+C (communication)", stats_bc)

    if stats_a and stats_bc:
        total_moy = stats_a["moyenne"] + stats_bc["moyenne"]
        total_med = stats_a["mediane"] + stats_bc["mediane"]
        print(f"\n  Latence logicielle totale (moyennes) : {total_moy:.2f} ms")
        print(f"  Latence logicielle totale (medianes) : {total_med:.2f} ms")
        print("  (delai de confirmation anti faux-positif et delai mecanique")
        print("   final non inclus)")

    exporter_csv(mesures_husky, mesures_comm)
    if stats_a and stats_bc:
        exporter_excel(husky_utiles, comm_utiles, stats_a, stats_bc)


if __name__ == "__main__":
    main()
