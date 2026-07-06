"""
Etape 4 : Envoi des commandes de gestes au robot via liaison serie (USB)
--------------------------------------------------------------------------
Detecte les 4 gestes de la main et envoie une commande JSON au robot
en continu, tant que le geste est detecte.

Le dashboard (trajectoire, angle, timeline) tourne dans un PROCESSUS SEPARE
pour eviter un conflit connu entre OpenCV (webcam) et matplotlib/Tkinter
lorsqu'ils partagent le meme processus (crash "Fatal Python error: GIL").

Appuie sur 'q' (dans la fenetre webcam) pour quitter.
"""

import cv2
import mediapipe as mp
import serial
import json
import time
import re
import csv
import os
import math
import multiprocessing as mp_proc
import queue as queue_module
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage

# Dossier ou sont enregistres les fichiers de session (CSV + Excel)
CSV_DIR = r"C:\Users\sivah\Documents\E4_SE\STAGE_R_D_TAIWAN\SUJET\sujet 2\Serial communication with dashboard upgrade\CSV file"

# ----------------------------------------------------------------
# A ADAPTER : nom du port serie du robot (voir Gestionnaire de peripheriques)
# Exemples : "COM5" sur Windows, "/dev/ttyACM0" sur Linux
# ----------------------------------------------------------------
SERIAL_PORT = "COM22"
BAUDRATE = 115200

# Intervalle minimum entre deux renvois de la meme commande (secondes)
SEND_INTERVAL = 0.15

# Distance en dessous de laquelle un point est marque comme obstacle sur la carte (cm)
OBSTACLE_THRESHOLD_CM = 15

# Couleurs associees a chaque mode pour la timeline des gestes
MODE_COLORS = {
    "forward": "tab:green",
    "stop": "tab:gray",
    "turn_left": "tab:orange",
    "turn_right": "tab:blue",
}

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


# Format attendu : "x=0.123 y=-0.045 angle=12.3 mode=forward dist=27.4"
# (le champ dist= est optionnel, pour compatibilite avec un ancien firmware)
STATUS_PATTERN = re.compile(
    r"x=(-?[\d.]+)\s+y=(-?[\d.]+)\s+angle=(-?[\d.]+)\s+mode=(\w+)(?:\s+dist=(-?[\d.]+))?"
)


def parse_status_line(line):
    """Extrait (x, y, angle, mode, distance_cm) d'une ligne de statut du robot,
    ou None si non reconnue. distance_cm vaut None si absente de la ligne."""
    match = STATUS_PATTERN.search(line)
    if not match:
        return None
    x_str, y_str, angle_str, mode_str, dist_str = match.groups()
    dist_cm = float(dist_str) if dist_str is not None else None
    return float(x_str), float(y_str), float(angle_str), mode_str, dist_cm


# ======================================================================
# PROCESSUS DASHBOARD (matplotlib / Tkinter) - completement independant
# du processus principal (OpenCV / webcam / serie).
# ======================================================================

def dashboard_process(data_queue):
    """Fonction executee dans un processus separe. Recoit les donnees du
    robot via data_queue et affiche un dashboard temps reel (3 panneaux)."""
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt
    import math as _math

    plt.ion()
    fig = plt.figure(figsize=(6, 9))
    fig.canvas.manager.set_window_title("Dashboard - Robot IOT Car")
    gs = fig.add_gridspec(3, 1, height_ratios=[3, 1.2, 0.6], hspace=0.4)

    # --- Panneau 1 : trajectoire, orientation, obstacles ---
    ax_traj = fig.add_subplot(gs[0])
    ax_traj.set_title("Trajectoire du robot (odometrie)")
    ax_traj.set_xlabel("x (m)")
    ax_traj.set_ylabel("y (m)")
    ax_traj.grid(True)
    ax_traj.set_aspect("equal", adjustable="datalim")

    trajectory_line, = ax_traj.plot([], [], "-b", linewidth=1.5, label="Trajectoire")
    current_point, = ax_traj.plot([], [], "ro", markersize=9, label="Position actuelle")
    obstacle_points, = ax_traj.plot(
        [], [], "kx", markersize=10, markeredgewidth=2.5, label="Obstacle detecte"
    )
    status_text = ax_traj.text(
        0.02, 0.98, "En attente de donnees...",
        transform=ax_traj.transAxes, va="top", fontsize=9,
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.85),
    )
    ax_traj.legend(loc="lower right", fontsize=8)

    # --- Panneau 2 : angle dans le temps ---
    ax_angle = fig.add_subplot(gs[1])
    ax_angle.set_title("Angle (degres) dans le temps")
    ax_angle.set_xlabel("temps (s)")
    ax_angle.set_ylabel("angle (deg)")
    ax_angle.grid(True)
    angle_line, = ax_angle.plot([], [], "-m", linewidth=1.2)

    # --- Panneau 3 : timeline des gestes/modes ---
    ax_timeline = fig.add_subplot(gs[2])
    ax_timeline.set_title("Historique des modes", fontsize=9)
    ax_timeline.set_xlabel("temps (s)")
    ax_timeline.set_yticks([])
    ax_timeline.set_ylim(0, 1)

    heading_arrow = [None]  # liste pour pouvoir muter depuis la fonction interne

    def redraw_heading_arrow(x, y, angle_deg):
        if heading_arrow[0] is not None:
            heading_arrow[0].remove()
        xlim = ax_traj.get_xlim()
        span = max(xlim[1] - xlim[0], 0.05)
        arrow_len = 0.15 * span
        angle_rad = _math.radians(angle_deg)
        x2 = x + arrow_len * _math.cos(angle_rad)
        y2 = y + arrow_len * _math.sin(angle_rad)
        heading_arrow[0] = ax_traj.annotate(
            "", xy=(x2, y2), xytext=(x, y),
            arrowprops=dict(arrowstyle="->", color="darkgreen", lw=2),
        )

    def redraw_timeline(mode_history):
        ax_timeline.cla()
        ax_timeline.set_title("Historique des modes", fontsize=9)
        ax_timeline.set_xlabel("temps (s)")
        ax_timeline.set_yticks([])
        ax_timeline.set_ylim(0, 1)

        if not mode_history:
            return

        segments = []
        seg_start_t, seg_mode = mode_history[0]
        for t, mode in mode_history[1:]:
            if mode != seg_mode:
                segments.append((seg_start_t, t - seg_start_t, seg_mode))
                seg_start_t, seg_mode = t, mode
        segments.append(
            (seg_start_t, mode_history[-1][0] - seg_start_t + 0.1, seg_mode)
        )

        bars = [(start, duration) for start, duration, _ in segments]
        colors = [MODE_COLORS.get(mode, "black") for _, _, mode in segments]
        ax_timeline.broken_barh(bars, (0, 1), facecolors=colors)
        ax_timeline.set_xlim(mode_history[0][0], mode_history[-1][0] + 0.5)

    traj_x, traj_y = [], []
    angle_times, angle_values = [], []
    mode_history = []
    obstacle_x, obstacle_y = [], []
    obstacle_active = False
    last_status = (0.0, 0.0, 0.0, "stop", None)

    while True:
        got_update = False

        # On vide la file d'attente sans bloquer
        while True:
            try:
                item = data_queue.get_nowait()
            except queue_module.Empty:
                break

            if item is None:  # signal d'arret envoye par le processus principal
                plt.close(fig)
                return

            if isinstance(item, tuple) and item and item[0] == "SAVE":
                fig.savefig(item[1], dpi=150, bbox_inches="tight")
                continue

            p_x, p_y, p_angle, p_mode, p_dist, t_rel = item
            last_status = (p_x, p_y, p_angle, p_mode, p_dist)
            traj_x.append(p_x)
            traj_y.append(p_y)
            angle_times.append(t_rel)
            angle_values.append(p_angle)
            mode_history.append((t_rel, p_mode))

            if p_dist is not None and 0 <= p_dist < OBSTACLE_THRESHOLD_CM:
                if not obstacle_active:
                    obstacle_x.append(p_x)
                    obstacle_y.append(p_y)
                    obstacle_active = True
            else:
                obstacle_active = False

            got_update = True

        if got_update and traj_x:
            _, _, last_angle, last_mode, last_dist = last_status

            trajectory_line.set_data(traj_x, traj_y)
            current_point.set_data([traj_x[-1]], [traj_y[-1]])
            ax_traj.relim()
            ax_traj.autoscale_view()
            redraw_heading_arrow(traj_x[-1], traj_y[-1], last_angle)

            if obstacle_x:
                obstacle_points.set_data(obstacle_x, obstacle_y)

            dist_text = f"{last_dist:.1f} cm" if last_dist is not None else "N/A"
            status_text.set_text(
                f"Mode : {last_mode}\n"
                f"Angle : {last_angle:.1f} deg\n"
                f"x={traj_x[-1]:.3f} y={traj_y[-1]:.3f}\n"
                f"Distance : {dist_text}"
            )

            angle_line.set_data(angle_times, angle_values)
            ax_angle.relim()
            ax_angle.autoscale_view()

            redraw_timeline(mode_history)

        # plt.pause() traite les evenements Tkinter ET fait office de temporisation.
        # Fonctionne meme si got_update est False (garde la fenetre reactive).
        try:
            plt.pause(0.1)
        except Exception:
            # La fenetre a pu etre fermee manuellement par l'utilisateur
            return


# ======================================================================
# PROCESSUS PRINCIPAL (webcam, detection de gestes, liaison serie)
# ======================================================================

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
    session_start = time.monotonic()

    # Lancement du dashboard dans un processus separe
    data_queue = mp_proc.Queue()
    dash_proc = mp_proc.Process(target=dashboard_process, args=(data_queue,), daemon=True)
    dash_proc.start()
    print("Dashboard lance dans un processus separe.")

    # Collecte des donnees de la session (ecrites en CSV/Excel a la fin,
    # une fois la duree totale connue pour nommer le fichier)
    rows_data = []
    last_speed_point = None  # (x, y, t_rel) du point precedent, pour calculer la vitesse

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
                # messages de statut du robot (x=... y=... angle=... mode=... dist=...).
                while ser.in_waiting:
                    try:
                        robot_line = ser.readline().decode(errors="ignore").strip()
                    except Exception:
                        break
                    if robot_line and not robot_line.startswith('{"cmd"'):
                        parsed = parse_status_line(robot_line)
                        if parsed is not None:
                            p_x, p_y, p_angle, p_mode, p_dist = parsed
                            t_rel = time.monotonic() - session_start

                            # Envoi au processus dashboard (non bloquant)
                            data_queue.put((p_x, p_y, p_angle, p_mode, p_dist, t_rel))

                            # Calcul de la vitesse instantanee a partir du point precedent
                            if last_speed_point is not None:
                                px_prev, py_prev, t_prev = last_speed_point
                                dt_speed = t_rel - t_prev
                                if dt_speed > 0:
                                    dist_m = math.hypot(p_x - px_prev, p_y - py_prev)
                                    speed = dist_m / dt_speed
                                else:
                                    speed = 0.0
                            else:
                                speed = 0.0
                            last_speed_point = (p_x, p_y, t_rel)

                            rows_data.append(
                                (t_rel, p_x, p_y, p_angle, p_mode, p_dist, speed)
                            )

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

        session_duration_s = time.monotonic() - session_start

        # Construction du nom de fichier : date (sans l'heure) + duree du programme
        date_str = time.strftime("%Y%m%d")
        minutes = int(session_duration_s // 60)
        seconds = int(session_duration_s % 60)
        duration_str = f"{minutes}m{seconds}s"
        base_name = f"session_{date_str}_{duration_str}"

        os.makedirs(CSV_DIR, exist_ok=True)

        # Evite d'ecraser un fichier existant portant exactement le meme nom
        csv_path = os.path.join(CSV_DIR, base_name + ".csv")
        xlsx_path = os.path.join(CSV_DIR, base_name + ".xlsx")
        png_path = os.path.join(CSV_DIR, base_name + ".png")
        suffix = 2
        while os.path.exists(csv_path):
            csv_path = os.path.join(CSV_DIR, f"{base_name}_{suffix}.csv")
            xlsx_path = os.path.join(CSV_DIR, f"{base_name}_{suffix}.xlsx")
            png_path = os.path.join(CSV_DIR, f"{base_name}_{suffix}.png")
            suffix += 1

        # Ecriture du CSV (donnees brutes, colonnes separees par categorie)
        with open(csv_path, "w", newline="", encoding="utf-8") as csv_file:
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(
                ["temps_s", "x_m", "y_m", "angle_deg", "mode", "distance_cm", "vitesse_m_s"]
            )
            for t_rel, p_x, p_y, p_angle, p_mode, p_dist, speed in rows_data:
                csv_writer.writerow([
                    f"{t_rel:.2f}", p_x, p_y, p_angle, p_mode,
                    p_dist if p_dist is not None else "", f"{speed:.3f}",
                ])

        # Demande au processus dashboard de sauvegarder une image de ses graphiques,
        # puis de se fermer proprement
        data_queue.put(("SAVE", png_path))
        data_queue.put(None)
        dash_proc.join(timeout=5)
        if dash_proc.is_alive():
            dash_proc.terminate()

        # Construction du fichier Excel : donnees en colonnes + image des graphiques
        try:
            wb = Workbook()
            ws_data = wb.active
            ws_data.title = "Donnees"
            ws_data.append(
                ["Temps (s)", "X (m)", "Y (m)", "Angle (deg)", "Mode",
                 "Distance (cm)", "Vitesse (m/s)"]
            )
            for t_rel, p_x, p_y, p_angle, p_mode, p_dist, speed in rows_data:
                ws_data.append([
                    round(t_rel, 2), p_x, p_y, p_angle, p_mode,
                    p_dist if p_dist is not None else None, round(speed, 3),
                ])

            ws_graphs = wb.create_sheet("Graphiques")
            if os.path.exists(png_path):
                img = XLImage(png_path)
                ws_graphs.add_image(img, "A1")

            wb.save(xlsx_path)
            print(f"Fichier Excel genere : {xlsx_path}")
        except Exception as e:
            print(f"Erreur lors de la generation du fichier Excel : {e}")

        print(f"Ressources liberees proprement.")
        print(f"CSV enregistre dans : {csv_path}")


if __name__ == "__main__":
    main()