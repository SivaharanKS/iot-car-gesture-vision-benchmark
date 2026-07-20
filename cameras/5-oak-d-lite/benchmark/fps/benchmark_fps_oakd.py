import time
import csv
import statistics
import depthai as dai
import cv2
import matplotlib.pyplot as plt
from oakd_common import BLOB_PATH, INPUT_SIZE, decoder_yolo

# ----------------------------------------------------------------
DUREE_MESURE = 30.0
WARMUP_SEC = 3.0
# ----------------------------------------------------------------


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


def mesurer_fps():
    donnees = []
    demarrage = False
    t_start = None
    t_prev = None

    with dai.Pipeline() as pipeline:
        cam = pipeline.create(dai.node.Camera).build()
        camOut = cam.requestOutput((INPUT_SIZE, INPUT_SIZE), type=dai.ImgFrame.Type.BGR888p)

        nn = pipeline.create(dai.node.NeuralNetwork)
        nn.setBlobPath(BLOB_PATH)
        camOut.link(nn.input)

        previewQueue = camOut.createOutputQueue()
        nnQueue = nn.out.createOutputQueue()

        pipeline.start()
        print("Position yourself in front of the camera, then press 's' to start the measurement (30 s).")
        print("(Press 'q' to quit at any time)")

        dernier_label, dernier_score = "none", 0.0
        fps_affiche = 0.0

        while pipeline.isRunning():
            if previewQueue.has():
                frame_msg = previewQueue.get()
                frame = frame_msg.getCvFrame()

                texte = f"{dernier_label} ({dernier_score:.2f})"
                couleur = (0, 255, 0) if demarrage else (0, 165, 255)
                cv2.putText(frame, texte, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.8, couleur, 2)

                if demarrage:
                    t_ecoule = time.perf_counter() - t_start
                    statut = f"MEASURING  {t_ecoule:4.1f}/{DUREE_MESURE:.0f}s   instant. FPS = {fps_affiche:5.1f}"
                else:
                    statut = "Press 's' to start"
                cv2.putText(frame, statut, (10, INPUT_SIZE - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, couleur, 1)
                cv2.imshow("OAK-D Lite - throughput (FPS) benchmark", frame)

            if nnQueue.has():
                resultat = nnQueue.get()
                output = resultat.getTensor("output0")
                dernier_label, dernier_score = decoder_yolo(output)

                if demarrage:
                    t_now = time.perf_counter()
                    dt = t_now - t_prev
                    t_prev = t_now
                    fps_affiche = (1.0 / dt) if dt > 0 else 0.0

                    t_rel = t_now - t_start
                    warmup = 1 if t_rel < WARMUP_SEC else 0
                    detection_active = 1 if dernier_label != "none" else 0
                    donnees.append((t_rel, fps_affiche, detection_active, warmup))

                    if t_rel >= DUREE_MESURE:
                        break

            touche = cv2.waitKey(1)
            if touche == ord('s') and not demarrage:
                demarrage = True
                t_start = time.perf_counter()
                t_prev = t_start
                print("Measurement started...")
            elif touche == ord('q'):
                break

    cv2.destroyAllWindows()
    return donnees


def generer_graphique(donnees_utiles, stats_global):
    t_rel = [d[0] for d in donnees_utiles]
    fps_vals = [d[1] for d in donnees_utiles]

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    axes[0].plot(t_rel, fps_vals, color="#4C72B0", linewidth=0.8)
    axes[0].axhline(stats_global["moyenne"], color="red", linestyle="--",
                     label=f"Mean = {stats_global['moyenne']:.2f} FPS")
    axes[0].set_title("Instantaneous FPS over time - OAK-D Lite")
    axes[0].set_xlabel("Time (s)")
    axes[0].set_ylabel("FPS")
    axes[0].legend()

    axes[1].hist(fps_vals, bins=20, color="#55A868", edgecolor="black")
    axes[1].axvline(stats_global["moyenne"], color="red", linestyle="--",
                     label=f"Mean = {stats_global['moyenne']:.2f} FPS")
    axes[1].set_title("FPS distribution - OAK-D Lite")
    axes[1].set_xlabel("FPS")
    axes[1].set_ylabel("Number of measurements")
    axes[1].legend()

    plt.tight_layout()
    plt.savefig("graphique_fps_oakd.png", dpi=150)
    print("Chart saved: graphique_fps_oakd.png")
    plt.show()


def main():
    donnees = mesurer_fps()
    donnees_utiles = [d for d in donnees if d[3] == 0]

    fps_global = [d[1] for d in donnees_utiles]
    fps_actif = [d[1] for d in donnees_utiles if d[2] == 1]
    fps_none = [d[1] for d in donnees_utiles if d[2] == 0]

    stats_global = calculer_stats(fps_global)
    stats_actif = calculer_stats(fps_actif)
    stats_none = calculer_stats(fps_none)

    print("Global FPS:", stats_global)
    print("FPS (active detection):", stats_actif)
    print("FPS (no detection):", stats_none)

    with open("resultats_fps_oakd.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["category", "n", "mean", "median", "std_dev", "min", "max"])
        for nom, stats in [("Global", stats_global), ("Active detection", stats_actif), ("No detection", stats_none)]:
            if stats:
                writer.writerow([nom, stats["n"], stats["moyenne"], stats["mediane"],
                                  stats["ecart_type"], stats["min"], stats["max"]])
    print("Results exported to resultats_fps_oakd.csv")

    if donnees_utiles:
        generer_graphique(donnees_utiles, stats_global)


if __name__ == "__main__":
    main()
