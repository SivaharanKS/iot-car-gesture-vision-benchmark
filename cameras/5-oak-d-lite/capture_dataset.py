import depthai as dai
import cv2
import os
import time

GESTES = {
    ord('1'): "forward",
    ord('2'): "stop",
    ord('3'): "left",
    ord('4'): "right",
}
DOSSIER_SORTIE = "dataset_oakd"

for nom in GESTES.values():
    os.makedirs(os.path.join(DOSSIER_SORTIE, nom), exist_ok=True)

compteurs = {nom: 0 for nom in GESTES.values()}

with dai.Pipeline() as pipeline:
    cam = pipeline.create(dai.node.Camera).build()
    videoQueue = cam.requestOutput((640, 480)).createOutputQueue()

    pipeline.start()
    print("Press 1=forward 2=stop 3=left 4=right to capture, q to quit")

    while pipeline.isRunning():
        videoIn = videoQueue.get()
        frame = videoIn.getCvFrame()

        cv2.imshow("Capture dataset OAK-D Lite", frame)
        touche = cv2.waitKey(1)

        if touche == ord('q'):
            break

        if touche in GESTES:
            nom_geste = GESTES[touche]
            compteurs[nom_geste] += 1
            chemin = os.path.join(DOSSIER_SORTIE, nom_geste, f"{nom_geste}_{compteurs[nom_geste]:03d}.jpg")
            cv2.imwrite(chemin, frame)
            print(f"Capture: {chemin}  (total {nom_geste} = {compteurs[nom_geste]})")
            time.sleep(0.2)

cv2.destroyAllWindows()
print("Done. Summary:", compteurs)
