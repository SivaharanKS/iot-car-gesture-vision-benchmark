import time
import csv
import statistics
import serial
import depthai as dai
import cv2
import numpy as np
import matplotlib.pyplot as plt
from oakd_common import BLOB_PATH, LABELS, INPUT_SIZE, decoder_yolo
import json

# ----------------------------------------------------------------
N_MESURES = 100
COM_ROBOT = "COM22"
BAUDRATE_ROBOT = 115200
PING_TIMEOUT = 1.0
# ----------------------------------------------------------------


def mesurer_segment_a():
    """Segment A : latence de traitement (mesure cote PC, capture -> resultat recu)."""
    mesures_ms = []
    frames_en_attente = {}  # sequence_num -> time.perf_counter() a la reception de la frame

    demarrage = False

    with dai.Pipeline() as pipeline:
        cam = pipeline.create(dai.node.Camera).build()
        camOut = cam.requestOutput((INPUT_SIZE, INPUT_SIZE), type=dai.ImgFrame.Type.BGR888p)

        nn = pipeline.create(dai.node.NeuralNetwork)
        nn.setBlobPath(BLOB_PATH)
        camOut.link(nn.input)

        previewQueue = camOut.createOutputQueue()
        nnQueue = nn.out.createOutputQueue()

        pipeline.start()
        print("Positionne-toi devant la camera, puis appuie sur 's' pour demarrer la mesure.")
        print("(Appuie sur 'q' pour quitter a tout moment)")

        dernier_label, dernier_score = "none", 0.0

        while pipeline.isRunning():
            if previewQueue.has():
                frame_msg = previewQueue.get()
                frames_en_attente[frame_msg.getSequenceNum()] = time.perf_counter()
                frame = frame_msg.getCvFrame()

                texte = f"{dernier_label} ({dernier_score:.2f})"
                couleur = (0, 255, 0) if demarrage else (0, 165, 255)
                cv2.putText(frame, texte, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.8, couleur, 2)
                statut = "MESURE EN COURS" if demarrage else "Appuie sur 's' pour demarrer"
                cv2.putText(frame, f"{statut} ({len(mesures_ms)}/{N_MESURES})",
                            (10, INPUT_SIZE - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, couleur, 1)
                cv2.imshow("OAK-D Lite - benchmark latence", frame)

            if nnQueue.has():
                resultat = nnQueue.get()
                seq = resultat.getSequenceNum()
                output = resultat.getTensor("output0")
                dernier_label, dernier_score = decoder_yolo(output)

                if seq in frames_en_attente:
                    t_capture = frames_en_attente.pop(seq)
                    t_reception = time.perf_counter()
                    latence_ms = (t_reception - t_capture) * 1000.0

                    if demarrage and len(mesures_ms) < N_MESURES:
                        mesures_ms.append(latence_ms)

                if len(frames_en_attente) > 50:
                    plus_ancien = min(frames_en_attente.keys())
                    frames_en_attente.pop(plus_ancien)

            touche = cv2.waitKey(1)
            if touche == ord('s') and not demarrage:
                demarrage = True
                print("Mesure demarree...")
            elif touche == ord('q'):
                break

            if demarrage and len(mesures_ms) >= N_MESURES:
                break

    cv2.destroyAllWindows()
    return mesures_ms


def mesurer_segment_bc():
    ser = serial.Serial(COM_ROBOT, BAUDRATE_ROBOT, timeout=0)

    # Redemarrage logiciel du robot (identique aux autres solutions)
    time.sleep(0.3)
    ser.write(b'\x03'); time.sleep(0.2)
    ser.write(b'\x02'); time.sleep(0.2)
    ser.write(b'\x04')
    boot_deadline = time.monotonic() + 6.0
    while time.monotonic() < boot_deadline:
        if ser.in_waiting:
            ser.readline()
        time.sleep(0.02)
    time.sleep(0.5)
    while ser.in_waiting:
        ser.readline()

    mesures_ms = []
    for i in range(N_MESURES):
        message = json.dumps({"ping": i}) + "\n"
        while ser.in_waiting:
            ser.readline()  # purge le buffer avant d'envoyer

        t_envoi = time.perf_counter()
        ser.write(message.encode())
        deadline = time.perf_counter() + PING_TIMEOUT

        while time.perf_counter() < deadline:
            if ser.in_waiting:
                line = ser.readline().decode(errors="ignore").strip()
                if line.startswith("b'") and line.endswith("'"):
                    line = line[2:-1]
                if '"pong"' in line:
                    try:
                        data = json.loads(line)
                    except Exception:
                        continue
                    if data.get("pong") == i:
                        mesures_ms.append((time.perf_counter() - t_envoi) * 1000.0)
                        break
            time.sleep(0.001)

    ser.close()
    return mesures_ms


def calculer_stats(mesures):
    if not mesures:
        return {"moyenne": 0, "mediane": 0, "ecart_type": 0, "min": 0, "max": 0}
    return {
        "moyenne": statistics.mean(mesures),
        "mediane": statistics.median(mesures),
        "ecart_type": statistics.stdev(mesures) if len(mesures) > 1 else 0,
        "min": min(mesures),
        "max": max(mesures),
    }


def generer_graphique(mesures_a, mesures_bc, stats_a, stats_bc):
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # Histogramme Segment A
    axes[0].hist(mesures_a, bins=20, color="#4C72B0", edgecolor="black")
    axes[0].axvline(stats_a["moyenne"], color="red", linestyle="--", label=f"Moyenne = {stats_a['moyenne']:.2f} ms")
    axes[0].set_title("Segment A - OAK-D Lite (traitement)")
    axes[0].set_xlabel("Latence (ms)")
    axes[0].set_ylabel("Nombre de mesures")
    axes[0].legend()

    # Barres comparatives des deux segments
    labels = ["Segment A\n(OAK-D Lite)", "Segment B+C\n(communication)"]
    moyennes = [stats_a["moyenne"], stats_bc["moyenne"]]
    ecarts = [stats_a["ecart_type"], stats_bc["ecart_type"]]
    axes[1].bar(labels, moyennes, yerr=ecarts, capsize=8, color=["#4C72B0", "#DD8452"])
    axes[1].set_title("Comparaison des segments de latence")
    axes[1].set_ylabel("Latence moyenne (ms)")

    plt.tight_layout()
    plt.savefig("graphique_latence_oakd.png", dpi=150)
    print("Graphique enregistre : graphique_latence_oakd.png")
    plt.show()


def main():
    mesures_a = mesurer_segment_a()
    stats_a = calculer_stats(mesures_a)
    print("Segment A (OAK-D Lite) :", stats_a, f"-- {len(mesures_a)} mesures")

    mesures_bc = mesurer_segment_bc()
    stats_bc = calculer_stats(mesures_bc)
    print("Segment B+C (communication) :", stats_bc, f"-- {len(mesures_bc)} mesures")

    with open("resultats_latence_oakd.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["segment", "moyenne_ms", "mediane_ms", "ecart_type_ms", "min_ms", "max_ms", "n"])
        writer.writerow(["Segment A (OAK-D Lite)", stats_a["moyenne"], stats_a["mediane"],
                          stats_a["ecart_type"], stats_a["min"], stats_a["max"], len(mesures_a)])
        writer.writerow(["Segment B+C (communication)", stats_bc["moyenne"], stats_bc["mediane"],
                          stats_bc["ecart_type"], stats_bc["min"], stats_bc["max"], len(mesures_bc)])
    print("Resultats exportes dans resultats_latence_oakd.csv")

    if mesures_a:
        generer_graphique(mesures_a, mesures_bc, stats_a, stats_bc)


if __name__ == "__main__":
    main()