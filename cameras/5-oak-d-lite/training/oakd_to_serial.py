import depthai as dai
import numpy as np
import cv2
import serial
import json
import time

# ----------------------------------------------------------------
# Parameters to adapt
# ----------------------------------------------------------------
BLOB_PATH = "best.blob"
LABELS = ["Forward", "Left", "Right", "Stop"]
INPUT_SIZE = 320
CONF_THRESHOLD = 0.5

COM_ROBOT = "COM22"
BAUDRATE_ROBOT = 115200

CONFIRM_COUNT = 5
SEND_INTERVAL = 0.15
TIMEOUT_STOP = 0.4

LABEL_TO_CMD = {
    "Forward": "forward",
    "Stop": "stop",
    "Left": "turn_left",
    "Right": "turn_right",
}


def decoder_yolo(output_tensor, conf_threshold=CONF_THRESHOLD):
    """Decodes the raw YOLOv8 output (1, 8, 2100) -> label, score, box (cx,cy,w,h normalized)."""
    data = output_tensor.reshape(8, -1).T  # -> (2100, 8)
    scores_classes = data[:, 4:8]
    class_ids = np.argmax(scores_classes, axis=1)
    scores = scores_classes[np.arange(len(class_ids)), class_ids]

    meilleur_idx = np.argmax(scores)
    if scores[meilleur_idx] < conf_threshold:
        return "none", 0.0, None

    boite = data[meilleur_idx, 0:4]  # cx, cy, w, h (in pixels, INPUT_SIZE scale)
    return LABELS[class_ids[meilleur_idx]], float(scores[meilleur_idx]), boite


def demarrer_robot(ser_robot):
    time.sleep(0.3)
    ser_robot.write(b'\x03'); time.sleep(0.2)
    ser_robot.write(b'\x02'); time.sleep(0.2)
    ser_robot.write(b'\x04')
    time.sleep(1.0)
    while ser_robot.in_waiting:
        ser_robot.readline()


def main():
    ser_robot = serial.Serial(COM_ROBOT, BAUDRATE_ROBOT, timeout=0)
    demarrer_robot(ser_robot)

    dernier_label = None
    compteur_confirm = 0
    label_valide = "none"
    dernier_envoi = 0.0
    derniere_detection_valide = time.monotonic()

    with dai.Pipeline() as pipeline:
        cam = pipeline.create(dai.node.Camera).build()
        camOut = cam.requestOutput((INPUT_SIZE, INPUT_SIZE), type=dai.ImgFrame.Type.BGR888p)

        nn = pipeline.create(dai.node.NeuralNetwork)
        nn.setBlobPath(BLOB_PATH)
        camOut.link(nn.input)

        previewQueue = camOut.createOutputQueue()
        nnQueue = nn.out.createOutputQueue()

        pipeline.start()
        print("OAK-D Lite control started. Close the window or press Ctrl+C to stop.")

        label_affiche, score_affiche, boite_affichee = "none", 0.0, None

        while pipeline.isRunning():
            inNn = nnQueue.get()
            output = inNn.getTensor("output0")

            label, score, boite = decoder_yolo(output)
            label_affiche, score_affiche, boite_affichee = label, score, boite

            # ---- Control logic (identical to before) ----
            if label == dernier_label:
                compteur_confirm += 1
            else:
                dernier_label = label
                compteur_confirm = 1

            if compteur_confirm >= CONFIRM_COUNT:
                label_valide = label

            maintenant = time.monotonic()
            cmd = LABEL_TO_CMD.get(label_valide, "stop")

            if label_valide != "none":
                derniere_detection_valide = maintenant

            if maintenant - derniere_detection_valide > TIMEOUT_STOP:
                cmd = "stop"

            if maintenant - dernier_envoi > SEND_INTERVAL:
                message = json.dumps({"cmd": cmd}) + "\n"
                ser_robot.write(message.encode())
                dernier_envoi = maintenant
                print(f"[OAK-D] {label_valide} ({score:.2f}) -> {cmd}")

            while ser_robot.in_waiting:
                print("[Robot]", ser_robot.readline())

            # ---- Visual display ----
            if previewQueue.has():
                inFrame = previewQueue.get()
                frame = inFrame.getCvFrame()

                if boite_affichee is not None:
                    cx, cy, w, h = boite_affichee
                    x1 = int(cx - w / 2)
                    y1 = int(cy - h / 2)
                    x2 = int(cx + w / 2)
                    y2 = int(cy + h / 2)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

                texte = f"{label_affiche} ({score_affiche:.2f})"
                cv2.putText(frame, texte, (10, 25), cv2.FONT_HERSHEY_SIMPLEX,
                            0.8, (0, 255, 0), 2)

                cv2.imshow("OAK-D Lite - control", frame)

            if cv2.waitKey(1) == ord('q'):
                break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
