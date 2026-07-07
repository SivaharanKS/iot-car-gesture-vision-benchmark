"""
huskylens_to_serial.py
=======================
Lecture directe de la HuskyLens via son port USB (bibliotheque officielle
huskylib.py), mapping du geste reconnu (ID appris) vers une commande JSON,
et envoi de cette commande au robot sur un second port serie.

Architecture :
    HuskyLens --(USB, port serie direct)--> PC --(USB)--> Robot RP2040

Prerequis :
    - pip install pyserial pypng
    - Le fichier huskylib.py (telecharge depuis
      https://github.com/HuskyLens/HUSKYLENSPython/tree/master/HUSKYLENS)
      doit se trouver dans le meme dossier que ce script.
    - La HuskyLens doit avoir ete entrainee en mode "Object Classification"
      avec les 5 classes suivantes (memes IDs que le mapping ci-dessous) :
          ID 1 = Avancer  (poing ferme)
          ID 2 = Stop     (main ouverte)
          ID 3 = Gauche   (index + pouce)
          ID 4 = Droite   (index + auriculaire)
          ID 5 = Neutre   (main absente / position de repos)
"""

import time
import json
import serial
from huskylib import HuskyLensLibrary

# ----------------------------------------------------------------
# Parametres a adapter
# ----------------------------------------------------------------
COM_HUSKY = "COM25"   # port serie de la HuskyLens
COM_ROBOT = "COM22"   # port serie du robot RP2040
BAUDRATE_ROBOT = 115200

SEND_INTERVAL = 0.15   # renvoi periodique de la commande active (secondes),
                       # le robot s'arrete automatiquement apres 0.4s de silence
CONFIRM_COUNT = 5      # nombre de detections consecutives identiques requises
                       # avant de valider un changement de geste (anti faux-positif)

ID_TO_COMMAND = {
    1: "forward",
    2: "stop",
    3: "turn_left",
    4: "turn_right",
    # 5 (neutre) et tout ID inconnu -> pas de mapping direct, traite comme "stop"
}

GESTE_LABEL = {
    1: "Avancer",
    2: "Stop",
    3: "Gauche",
    4: "Droite",
    5: "Neutre",
}


def lire_id_geste(hl):
    """Interroge la HuskyLens et renvoie l'ID du geste detecte,
    ou None si rien n'est detecte.

    Note : la methode learned() de huskylib.py renvoie directement un
    seul objet Block (et non une liste comme le suggere la documentation
    officielle) -- comportement documente dans l'issue #18 du depot
    HUSKYLENSPython (https://github.com/HuskyLens/HUSKYLENSPython/issues/18).
    """
    try:
        objet = hl.learned()
    except Exception:
        return None
    if not objet:
        return None
    return getattr(objet, "ID", None)


def main():
    print("Connexion a la HuskyLens...")
    try:
        hl = HuskyLensLibrary("SERIAL", COM_HUSKY)
        print(hl.knock())
        hl.algorthim("ALGORITHM_OBJECT_CLASSIFICATION")
    except Exception as e:
        print(f"Erreur de connexion a la HuskyLens ({COM_HUSKY}) : {e}")
        return

    print("Connexion au robot...")
    try:
        ser_robot = serial.Serial(COM_ROBOT, BAUDRATE_ROBOT, timeout=0)
    except serial.SerialException as e:
        print(f"Erreur de connexion au robot ({COM_ROBOT}) : {e}")
        return

    # Redemarrage logiciel du robot (sortie REPL / raw REPL puis relance
    # de code.py), indispensable pour etre sur que le robot execute bien
    # code.py et non bloque a l'invite interactive (>>>).
    time.sleep(0.3)
    ser_robot.write(b'\x03')
    time.sleep(0.2)
    ser_robot.write(b'\x02')
    time.sleep(0.2)
    ser_robot.write(b'\x04')
    print("Redemarrage du robot en cours...")

    boot_deadline = time.monotonic() + 3.0
    while time.monotonic() < boot_deadline:
        if ser_robot.in_waiting:
            boot_line = ser_robot.readline().decode(errors="ignore").strip()
            if boot_line:
                print(f"[Boot] {boot_line}")
        time.sleep(0.02)

    print("Systeme pret. Ctrl+C pour arreter.\n")

    candidate_id = None
    candidate_count = 0
    stable_id = None
    last_send_time = 0.0
    last_print_id = None
    last_status_print_time = 0.0
    STATUS_PRINT_INTERVAL = 0.5

    try:
        while True:
            detected_id = lire_id_geste(hl)

            # --- Filtrage par confirmation (anti faux-positif) ---
            if detected_id == candidate_id:
                candidate_count += 1
            else:
                candidate_id = detected_id
                candidate_count = 1

            if candidate_count >= CONFIRM_COUNT:
                stable_id = candidate_id

            # --- Determination de la commande a envoyer ---
            cmd = ID_TO_COMMAND.get(stable_id, "stop")

            now = time.monotonic()
            if now - last_send_time >= SEND_INTERVAL:
                message = json.dumps({"cmd": cmd}) + "\n"
                ser_robot.write(message.encode())
                last_send_time = now

                if stable_id != last_print_id:
                    label = GESTE_LABEL.get(stable_id, "Inconnu")
                    print(f"[HuskyLens] Geste stable : {label} (ID={stable_id}) -> {cmd}")
                    last_print_id = stable_id

            # --- Affichage des messages renvoyes par le robot (statut) ---
            # Permet de verifier que le robot recoit bien les commandes et
            # execute son control_loop (odometrie, mode courant, etc.)
            while ser_robot.in_waiting:
                robot_line = ser_robot.readline().decode(errors="ignore").strip()
                if robot_line:
                    now_print = time.monotonic()
                    if now_print - last_status_print_time > STATUS_PRINT_INTERVAL:
                        print(f"  [Robot] {robot_line}")
                        last_status_print_time = now_print

            time.sleep(0.02)

    except KeyboardInterrupt:
        print("\nArret demande par l'utilisateur.")
    finally:
        ser_robot.close()


if __name__ == "__main__":
    main()