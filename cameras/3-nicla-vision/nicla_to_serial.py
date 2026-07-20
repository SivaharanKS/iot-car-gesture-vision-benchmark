import serial
import json
import time

COM_NICLA = "COM31"
COM_ROBOT = "COM22"
BAUDRATE_ROBOT = 115200

CONFIRM_COUNT = 5   # number of identical consecutive detections before validation
SEND_INTERVAL = 0.15
TIMEOUT_STOP = 0.4

LABEL_TO_CMD = {
    "Forward": "forward",
    "Stop": "stop",
    "Left": "turn_left",
    "Right": "turn_right",
}


def demarrer_robot(ser_robot):
    time.sleep(0.3)
    ser_robot.write(b'\x03'); time.sleep(0.2)
    ser_robot.write(b'\x02'); time.sleep(0.2)
    ser_robot.write(b'\x04')
    time.sleep(1.0)
    while ser_robot.in_waiting:
        ser_robot.readline()


def main():
    ser_nicla = serial.Serial(COM_NICLA, 115200, timeout=1)
    ser_robot = serial.Serial(COM_ROBOT, BAUDRATE_ROBOT, timeout=0)
    demarrer_robot(ser_robot)

    dernier_label = None
    compteur_confirm = 0
    label_valide = "none"
    dernier_envoi = 0.0
    derniere_detection_valide = time.monotonic()

    print("Nicla Vision control started. Ctrl+C to stop.")
    while True:
        ligne = ser_nicla.readline().decode(errors="ignore").strip()
        if ligne.startswith("DETECTED:"):
            label = ligne.split(":")[1]

            # temporal filtering (anti-false-positive)
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

            # safety: stop if nothing valid for more than TIMEOUT_STOP
            if maintenant - derniere_detection_valide > TIMEOUT_STOP:
                cmd = "stop"

            if maintenant - dernier_envoi > SEND_INTERVAL:
                message = json.dumps({"cmd": cmd}) + "\n"
                ser_robot.write(message.encode())
                dernier_envoi = maintenant
                print(f"[Nicla] {label_valide} -> {cmd}")

        while ser_robot.in_waiting:
            print("[Robot]", ser_robot.readline())


if __name__ == "__main__":
    main()
