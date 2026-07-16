"""
Step 4: Sending gesture commands to the robot over a serial (USB) link
--------------------------------------------------------------------------
Detects the 4 hand gestures and continuously sends a JSON command
to the robot for as long as the gesture is detected.

The dashboard (trajectory, angle, timeline) runs in a SEPARATE PROCESS
to avoid a known conflict between OpenCV (webcam) and matplotlib/Tkinter
when they share the same process (crash "Fatal Python error: GIL").

Press 'q' (in the webcam window) to quit.
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

# Folder where the session files (CSV + Excel) are saved
# (automatically set to the folder containing this script)
CSV_DIR = os.path.dirname(os.path.abspath(__file__))

# ----------------------------------------------------------------
# TO ADAPT: name of the robot's serial port (see Device Manager)
# Examples: "COM5" on Windows, "/dev/ttyACM0" on Linux
# ----------------------------------------------------------------
SERIAL_PORT = "COM22"
BAUDRATE = 115200

# Minimum interval between two resends of the same command (seconds)
SEND_INTERVAL = 0.15

# Distance below which a point is marked as an obstacle on the map (cm)
OBSTACLE_THRESHOLD_CM = 15

# Colors associated with each mode for the gesture timeline
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
        return "forward", "Closed fist"

    if thumb and index and middle and ring and pinky:
        return "stop", "Open hand"

    if thumb and index and not middle and not ring and not pinky:
        return "turn_left", "Index + thumb"

    if not thumb and index and not middle and not ring and pinky:
        return "turn_right", "Index + pinky"

    return None, "Gesture not recognized"


def build_json_command(gesture_cmd):
    """Builds the JSON message expected by code.py on the robot."""
    if gesture_cmd == "forward":
        return {"cmd": "forward"}
    if gesture_cmd == "stop":
        return {"cmd": "stop"}
    if gesture_cmd == "turn_left":
        return {"cmd": "turn_left"}
    if gesture_cmd == "turn_right":
        return {"cmd": "turn_right"}
    return None


# Expected format: "x=0.123 y=-0.045 angle=12.3 mode=forward dist=27.4"
# (the dist= field is optional, for compatibility with an older firmware)
STATUS_PATTERN = re.compile(
    r"x=(-?[\d.]+)\s+y=(-?[\d.]+)\s+angle=(-?[\d.]+)\s+mode=(\w+)(?:\s+dist=(-?[\d.]+))?"
)


def parse_status_line(line):
    """Extracts (x, y, angle, mode, distance_cm) from a robot status line,
    or None if not recognized. distance_cm is None if absent from the line."""
    match = STATUS_PATTERN.search(line)
    if not match:
        return None
    x_str, y_str, angle_str, mode_str, dist_str = match.groups()
    dist_cm = float(dist_str) if dist_str is not None else None
    return float(x_str), float(y_str), float(angle_str), mode_str, dist_cm


# ======================================================================
# DASHBOARD PROCESS (matplotlib / Tkinter) - completely independent
# from the main process (OpenCV / webcam / serial).
# ======================================================================

def dashboard_process(data_queue):
    """Function executed in a separate process. Receives data from the
    robot via data_queue and displays a real-time dashboard (3 panels)."""
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt
    import math as _math

    plt.ion()
    fig = plt.figure(figsize=(6, 9))
    fig.canvas.manager.set_window_title("Dashboard - IOT Car Robot")
    gs = fig.add_gridspec(3, 1, height_ratios=[3, 1.2, 0.6], hspace=0.4)

    # --- Panel 1: trajectory, orientation, obstacles ---
    ax_traj = fig.add_subplot(gs[0])
    ax_traj.set_title("Robot trajectory (odometry)")
    ax_traj.set_xlabel("x (m)")
    ax_traj.set_ylabel("y (m)")
    ax_traj.grid(True)
    ax_traj.set_aspect("equal", adjustable="datalim")

    trajectory_line, = ax_traj.plot([], [], "-b", linewidth=1.5, label="Trajectory")
    current_point, = ax_traj.plot([], [], "ro", markersize=9, label="Current position")
    obstacle_points, = ax_traj.plot(
        [], [], "kx", markersize=10, markeredgewidth=2.5, label="Obstacle detected"
    )
    status_text = ax_traj.text(
        0.02, 0.98, "Waiting for data...",
        transform=ax_traj.transAxes, va="top", fontsize=9,
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.85),
    )
    ax_traj.legend(loc="lower right", fontsize=8)

    # --- Panel 2: angle over time ---
    ax_angle = fig.add_subplot(gs[1])
    ax_angle.set_title("Angle (degrees) over time")
    ax_angle.set_xlabel("time (s)")
    ax_angle.set_ylabel("angle (deg)")
    ax_angle.grid(True)
    angle_line, = ax_angle.plot([], [], "-m", linewidth=1.2)

    # --- Panel 3: gesture/mode timeline ---
    ax_timeline = fig.add_subplot(gs[2])
    ax_timeline.set_title("Mode history", fontsize=9)
    ax_timeline.set_xlabel("time (s)")
    ax_timeline.set_yticks([])
    ax_timeline.set_ylim(0, 1)

    heading_arrow = [None]  # list so it can be mutated from the inner function

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
        ax_timeline.set_title("Mode history", fontsize=9)
        ax_timeline.set_xlabel("time (s)")
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

        # We drain the queue without blocking
        while True:
            try:
                item = data_queue.get_nowait()
            except queue_module.Empty:
                break

            if item is None:  # stop signal sent by the main process
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
                f"Mode: {last_mode}\n"
                f"Angle: {last_angle:.1f} deg\n"
                f"x={traj_x[-1]:.3f} y={traj_y[-1]:.3f}\n"
                f"Distance: {dist_text}"
            )

            angle_line.set_data(angle_times, angle_values)
            ax_angle.relim()
            ax_angle.autoscale_view()

            redraw_timeline(mode_history)

        # plt.pause() processes Tkinter events AND acts as a timing delay.
        # Works even if got_update is False (keeps the window responsive).
        try:
            plt.pause(0.1)
        except Exception:
            # The window may have been closed manually by the user
            return


# ======================================================================
# MAIN PROCESS (webcam, gesture detection, serial link)
# ======================================================================

def main():
    # Connect to the robot's serial port
    try:
        ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=0)
        print(f"Connected to the robot on {SERIAL_PORT}")
    except serial.SerialException as e:
        print(f"Serial connection error: {e}")
        print("Check the port name (SERIAL_PORT) and make sure nothing else "
              "is already using this port (e.g. Thonny, Mu Editor).")
        return

    # The robot may have been left stuck at the interactive prompt (REPL, ">>>")
    # following a previous Thonny/Mu session. We force a software restart
    # (equivalent to Ctrl+D) so it exits the REPL and relaunches code.py cleanly.
    time.sleep(0.3)
    ser.write(b'\x03')   # Ctrl-C: interrupts any code currently running
    time.sleep(0.2)
    ser.write(b'\x02')   # Ctrl-B: exits raw REPL (left by Thonny) if needed
    time.sleep(0.2)
    ser.write(b'\x04')   # Ctrl-D: triggers the software restart (relaunches code.py)
    print("Restarting the robot...")

    # We display everything received during the restart live,
    # instead of discarding it, to check that code.py starts correctly.
    boot_deadline = time.monotonic() + 3.0
    while time.monotonic() < boot_deadline:
        if ser.in_waiting:
            boot_line = ser.readline().decode(errors="ignore").strip()
            if boot_line:
                print(f"[Boot] {boot_line}")
        time.sleep(0.02)

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: unable to open the webcam.")
        ser.close()
        return

    last_sent_cmd = None
    last_send_time = time.monotonic()
    last_print_time = time.monotonic()
    PRINT_INTERVAL = 0.5  # only display robot messages at most 2 times/second
    session_start = time.monotonic()

    # Launching the dashboard in a separate process
    data_queue = mp_proc.Queue()
    dash_proc = mp_proc.Process(target=dashboard_process, args=(data_queue,), daemon=True)
    dash_proc.start()
    print("Dashboard launched in a separate process.")

    # Collecting the session data (written to CSV/Excel at the end,
    # once the total duration is known, to name the file)
    rows_data = []
    last_speed_point = None  # (x, y, t_rel) of the previous point, to compute speed

    try:
        with mp_hands.Hands(
            max_num_hands=1,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7,
        ) as hands:

            while True:
                ret, frame = cap.read()
                if not ret:
                    print("Error: unable to read the webcam frame. Stopping.")
                    break

                frame = cv2.flip(frame, 1)
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = hands.process(rgb_frame)

                gesture_cmd = None
                gesture_name = "No hand detected"

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

                # If no hand is detected, the effective command is "stop"
                effective_cmd = gesture_cmd if gesture_cmd is not None else "stop"
                now = time.monotonic()

                # We resend the current command regularly as long as it is held
                # (continuous movement), and immediately if it just changed (responsiveness).
                if effective_cmd != last_sent_cmd or (now - last_send_time) > SEND_INTERVAL:
                    payload = build_json_command(effective_cmd)
                    if payload is not None:
                        message = json.dumps(payload) + "\n"
                        try:
                            ser.write(message.encode())
                            last_sent_cmd = effective_cmd
                            last_send_time = now
                        except serial.SerialException as e:
                            print(f"Serial send error (robot disconnected?): {e}")

                # We read incoming messages. We ignore echoes of our own commands
                # (lines starting with '{"cmd"') and only display genuine
                # robot status messages (x=... y=... angle=... mode=... dist=...).
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

                            # Sending to the dashboard process (non-blocking)
                            data_queue.put((p_x, p_y, p_angle, p_mode, p_dist, t_rel))

                            # Computing the instantaneous speed from the previous point
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
                    frame, f"Gesture: {gesture_name}", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2
                )
                cv2.putText(
                    frame, f"Command: {effective_cmd}", (20, 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2
                )
                cv2.imshow("Gesture-Based Robot Control", frame)

                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

    except Exception as e:
        print(f"Unexpected error: {e}")

    finally:
        cap.release()
        cv2.destroyAllWindows()
        ser.close()

        session_duration_s = time.monotonic() - session_start

        # Building the file name: date (without time) + program duration
        date_str = time.strftime("%Y%m%d")
        minutes = int(session_duration_s // 60)
        seconds = int(session_duration_s % 60)
        duration_str = f"{minutes}m{seconds}s"
        base_name = f"session_{date_str}_{duration_str}"

        os.makedirs(CSV_DIR, exist_ok=True)

        # Avoids overwriting an existing file with exactly the same name
        csv_path = os.path.join(CSV_DIR, base_name + ".csv")
        xlsx_path = os.path.join(CSV_DIR, base_name + ".xlsx")
        png_path = os.path.join(CSV_DIR, base_name + ".png")
        suffix = 2
        while os.path.exists(csv_path):
            csv_path = os.path.join(CSV_DIR, f"{base_name}_{suffix}.csv")
            xlsx_path = os.path.join(CSV_DIR, f"{base_name}_{suffix}.xlsx")
            png_path = os.path.join(CSV_DIR, f"{base_name}_{suffix}.png")
            suffix += 1

        # Writing the CSV (raw data, columns separated by category)
        with open(csv_path, "w", newline="", encoding="utf-8") as csv_file:
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(
                ["time_s", "x_m", "y_m", "angle_deg", "mode", "distance_cm", "speed_m_s"]
            )
            for t_rel, p_x, p_y, p_angle, p_mode, p_dist, speed in rows_data:
                csv_writer.writerow([
                    f"{t_rel:.2f}", p_x, p_y, p_angle, p_mode,
                    p_dist if p_dist is not None else "", f"{speed:.3f}",
                ])

        # Asking the dashboard process to save an image of its charts,
        # then to close cleanly
        data_queue.put(("SAVE", png_path))
        data_queue.put(None)
        dash_proc.join(timeout=5)
        if dash_proc.is_alive():
            dash_proc.terminate()

        # Building the Excel file: data in columns + chart image
        try:
            wb = Workbook()
            ws_data = wb.active
            ws_data.title = "Data"
            ws_data.append(
                ["Time (s)", "X (m)", "Y (m)", "Angle (deg)", "Mode",
                 "Distance (cm)", "Speed (m/s)"]
            )
            for t_rel, p_x, p_y, p_angle, p_mode, p_dist, speed in rows_data:
                ws_data.append([
                    round(t_rel, 2), p_x, p_y, p_angle, p_mode,
                    p_dist if p_dist is not None else None, round(speed, 3),
                ])

            ws_graphs = wb.create_sheet("Charts")
            if os.path.exists(png_path):
                img = XLImage(png_path)
                ws_graphs.add_image(img, "A1")

            wb.save(xlsx_path)
            print(f"Excel file generated: {xlsx_path}")
        except Exception as e:
            print(f"Error while generating the Excel file: {e}")

        print(f"Resources released cleanly.")
        print(f"CSV saved to: {csv_path}")


if __name__ == "__main__":
    main()