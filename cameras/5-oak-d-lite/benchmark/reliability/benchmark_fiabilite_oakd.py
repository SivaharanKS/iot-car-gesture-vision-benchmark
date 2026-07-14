import time
import csv
import depthai as dai
import cv2
import numpy as np
import matplotlib.pyplot as plt
from oakd_common import BLOB_PATH, INPUT_SIZE, decoder_yolo

# ----------------------------------------------------------------
N_PAR_GESTE = 20  # nombre d'essais vises pour chaque geste

GESTES = ["Forward", "Stop", "Left", "Right"]
TOUCHE_GESTE = {
    ord('1'): "Forward",
    ord('2'): "Stop",
    ord('3'): "Left",
    ord('4'): "Right",
}
# ----------------------------------------------------------------


def acquerir_essais():
    essais = []  # (voulu, detecte)
    compteur = {g: 0 for g in GESTES}
    dernier_label = "none"
    dernier_score = 0.0

    with dai.Pipeline() as pipeline:
        cam = pipeline.create(dai.node.Camera).build()
        camOut = cam.requestOutput((INPUT_SIZE, INPUT_SIZE), type=dai.ImgFrame.Type.BGR888p)

        nn = pipeline.create(dai.node.NeuralNetwork)
        nn.setBlobPath(BLOB_PATH)
        camOut.link(nn.input)

        previewQueue = camOut.createOutputQueue()
        nnQueue = nn.out.createOutputQueue()

        pipeline.start()
        print("Fais un geste, puis appuie sur 1=Forward 2=Stop 3=Left 4=Right pour valider l'essai.")
        print("(Appuie sur 'q' pour quitter a tout moment)")

        while pipeline.isRunning():
            if nnQueue.has():
                resultat = nnQueue.get()
                output = resultat.getTensor("output0")
                dernier_label, dernier_score = decoder_yolo(output)

            if previewQueue.has():
                frame_msg = previewQueue.get()
                frame = frame_msg.getCvFrame()

                texte = f"Detecte : {dernier_label} ({dernier_score:.2f})"
                cv2.putText(frame, texte, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

                y = 50
                for g in GESTES:
                    cv2.putText(frame, f"{g}: {compteur[g]}/{N_PAR_GESTE}", (10, y),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                    y += 20

                cv2.imshow("OAK-D Lite - benchmark fiabilite", frame)

            touche = cv2.waitKey(1) & 0xFF
            if touche == ord('q'):
                break
            if touche in TOUCHE_GESTE:
                voulu = TOUCHE_GESTE[touche]
                essais.append((voulu, dernier_label))
                compteur[voulu] += 1
                print(f"Essai enregistre : voulu={voulu}, detecte={dernier_label} "
                      f"({sum(compteur.values())}/{N_PAR_GESTE * len(GESTES)})")

                if all(compteur[g] >= N_PAR_GESTE for g in GESTES):
                    break

    cv2.destroyAllWindows()
    return essais


def construire_matrice_confusion(essais):
    labels_possibles = GESTES + ["none"]
    matrice = {voulu: {det: 0 for det in labels_possibles} for voulu in GESTES}
    for voulu, detecte in essais:
        det = detecte if detecte in labels_possibles else "none"
        matrice[voulu][det] += 1
    return matrice, labels_possibles


def generer_graphique(matrice, labels_possibles):
    data = np.array([[matrice[voulu][det] for det in labels_possibles] for voulu in GESTES])

    fig, ax = plt.subplots(figsize=(7, 6))
    im = ax.imshow(data, cmap="Blues")

    ax.set_xticks(range(len(labels_possibles)))
    ax.set_xticklabels(labels_possibles, rotation=45, ha="right")
    ax.set_yticks(range(len(GESTES)))
    ax.set_yticklabels(GESTES)
    ax.set_xlabel("Geste detecte")
    ax.set_ylabel("Geste voulu")
    ax.set_title("Matrice de confusion - OAK-D Lite")

    for i in range(len(GESTES)):
        for j in range(len(labels_possibles)):
            valeur = data[i, j]
            couleur = "white" if valeur > data.max() / 2 else "black"
            ax.text(j, i, str(valeur), ha="center", va="center", color=couleur)

    fig.colorbar(im, ax=ax, label="Nombre d'essais")
    plt.tight_layout()
    plt.savefig("graphique_fiabilite_oakd.png", dpi=150)
    print("Graphique enregistre : graphique_fiabilite_oakd.png")
    plt.show()


def main():
    essais = acquerir_essais()

    if not essais:
        print("Aucun essai enregistre.")
        return

    matrice, labels_possibles = construire_matrice_confusion(essais)

    print("\nMatrice de confusion :")
    for voulu in GESTES:
        print(voulu, matrice[voulu])

    n_correct = sum(matrice[g][g] for g in GESTES)
    n_total = len(essais)
    taux_reussite = 100.0 * n_correct / n_total
    print(f"\nTaux de reussite global : {n_correct}/{n_total} ({taux_reussite:.1f}%)")

    with open("resultats_fiabilite_oakd.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["voulu"] + labels_possibles)
        for voulu in GESTES:
            writer.writerow([voulu] + [matrice[voulu][det] for det in labels_possibles])
    print("Resultats exportes dans resultats_fiabilite_oakd.csv")

    generer_graphique(matrice, labels_possibles)


if __name__ == "__main__":
    main()