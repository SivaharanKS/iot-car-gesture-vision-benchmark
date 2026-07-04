"""
Etape 4 : Envoi des commandes de gestes au robot via liaison serie (USB)
--------------------------------------------------------------------------
Detecte les 4 gestes de la main et envoie une commande JSON au robot
en continu, tant que le geste est detecte.
Appuie sur 'q' pour quitter.
"""

import cv2
import mediapipe as mp
import serial
import json
import time

# ----------------------------------------------------------------
# A ADAPTER : nom du port serie du robot (voir Gestionnaire de peripheriques)
# Exemples : "COM5" sur Windows, "/dev/ttyACM0" sur Linux
# ----------------------------------------------------------------
SERIAL_PORT = "COM22"
BAUDRATE = 115200

# Intervalle minimum entre deux renvois de la meme commande (secondes)
SEND_INTERVAL = 0.15

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
        return "forward", "Poing ferme"

    if thumb and index and middle and ring and pinky:
        return "stop", "Main ouverte"

    if thumb and index and not middle and not ring and not pinky:
        return "turn_left", "Index + pouce"

    if not thumb and index and not middle and not ring and pinky:
        return "turn_right", "Index + auriculaire"

    return None, "Geste non reconnu"


def build_json_command(gesture_cmd):
    """Construit le message JSON attendu par code.py sur le robot."""
    if gesture_cmd == "forward":
        return {"cmd": "forward"}
    if gesture_cmd == "stop":
        return {"cmd": "stop"}
    if gesture_cmd == "turn_left":
        return {"cmd": "turn_left"}
    if gesture_cmd == "turn_right":
        return {"cmd": "turn_right"}
    return None


def main():
    # Connexion au port serie du robot
    try:
        ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=0)
        print(f"Connecte au robot sur {SERIAL_PORT}")
    except serial.SerialException as e:
        print(f"Erreur de connexion serie : {e}")
        print("Verifie le nom du port (SERIAL_PORT) et que rien d'autre "
              "n'utilise deja ce port (ex : Thonny, Mu Editor).")
        return

    # Le robot peut etre reste bloque sur l'invite interactive (REPL, ">>>")
    # suite a une session Thonny/Mu precedente. On force un redemarrage logiciel
    # (equivalent Ctrl+D) pour qu'il quitte le REPL et relance code.py proprement.
    time.sleep(0.3)
    ser.write(b'\x03')   # Ctrl-C : interrompt un eventuel code en cours
    time.sleep(0.2)
    ser.write(b'\x02')   # Ctrl-B : sort du raw REPL (laisse par Thonny) si necessaire
    time.sleep(0.2)
    ser.write(b'\x04')   # Ctrl-D : provoque le redemarrage logiciel (relance code.py)
    print("Redemarrage du robot en cours...")

    # On affiche en direct tout ce qui est recu pendant le redemarrage,
    # au lieu de le jeter, pour verifier que code.py demarre bien.
    boot_deadline = time.monotonic() + 3.0
    while time.monotonic() < boot_deadline:
        if ser.in_waiting:
            boot_line = ser.readline().decode(errors="ignore").strip()
            if boot_line:
                print(f"[Boot] {boot_line}")
        time.sleep(0.02)

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Erreur : impossible d'ouvrir la webcam.")
        ser.close()
        return

    last_sent_cmd = None
    last_send_time = time.monotonic()
    last_print_time = time.monotonic()
    PRINT_INTERVAL = 0.5  # n'affiche les messages du robot qu'au maximum 2 fois/seconde

    try:
        with mp_hands.Hands(
            max_num_hands=1,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7,
        ) as hands:

            while True:
                ret, frame = cap.read()
                if not ret:
                    print("Erreur : impossible de lire l'image de la webcam. Arret.")
                    break

                frame = cv2.flip(frame, 1)
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = hands.process(rgb_frame)

                gesture_cmd = None
                gesture_name = "Aucune main detectee"

                if results.multi_hand_landmarks and results.multi_handedness:
                    for hand_landmarks, handedness in zip(
                        results.multi_hand_landmarks, results.multi_handedness
                    ):
                        mp_draw.draw_landmarks(
                            frame, hand_landmarks, mp_hands.HAND_CONNECTIONS
                        )
                        label = handedness.classification[0].label
                        finger_states = get_finger_states(hand_landmarks, label)
                        gesture_cmd, gesture_name = classify_gesture(finger_states)

                # Si aucune main n'est detectee, la commande effective est "stop"
                effective_cmd = gesture_cmd if gesture_cmd is not None else "stop"
                now = time.monotonic()

                # On renvoie la commande courante regulierement tant qu'elle est maintenue
                # (mouvement continu), et immediatement si elle vient de changer (reactivite).
                if effective_cmd != last_sent_cmd or (now - last_send_time) > SEND_INTERVAL:
                    payload = build_json_command(effective_cmd)
                    if payload is not None:
                        message = json.dumps(payload) + "\n"
                        try:
                            ser.write(message.encode())
                            last_sent_cmd = effective_cmd
                            last_send_time = now
                        except serial.SerialException as e:
                            print(f"Erreur d'envoi serie (robot deconnecte ?) : {e}")

                # On lit les messages recus. On ignore les echos de nos propres commandes
                # (lignes qui commencent par '{"cmd"') et on n'affiche que les vrais
                # messages de statut du robot (x=... y=... angle=... mode=...).
                while ser.in_waiting:
                    try:
                        robot_line = ser.readline().decode(errors="ignore").strip()
                    except Exception:
                        break
                    if robot_line and not robot_line.startswith('{"cmd"'):
                        now_print = time.monotonic()
                        if now_print - last_print_time > PRINT_INTERVAL:
                            print(f"[Robot] {robot_line}")
                            last_print_time = now_print

                cv2.putText(
                    frame, f"Geste : {gesture_name}", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2
                )
                cv2.putText(
                    frame, f"Commande : {effective_cmd}", (20, 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2
                )
                cv2.imshow("Controle du robot par gestes", frame)

                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

    except Exception as e:
        print(f"Erreur inattendue : {e}")

    finally:
        cap.release()
        cv2.destroyAllWindows()
        ser.close()
        print("Ressources liberees proprement.")


if __name__ == "__main__":
    main()