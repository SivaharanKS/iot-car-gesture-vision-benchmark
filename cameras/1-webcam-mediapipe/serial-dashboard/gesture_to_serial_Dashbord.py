"""
Step 4: Sending gesture commands to the robot over a serial (USB) link
--------------------------------------------------------------------------
Detects the 4 hand gestures and continuously sends a JSON command
to the robot for as long as the gesture is detected.
Press 'q' to quit.
"""

import cv2
import mediapipe as mp
import serial
import json
import time
import re
import matplotlib.pyplot as plt

# ----------------------------------------------------------------
# TO ADAPT: name of the robot's serial port (see Device Manager)
# Examples: "COM5" on Windows, "/dev/ttyACM0" on Linux
# ----------------------------------------------------------------
SERIAL_PORT = "COM22"
BAUDRATE = 115200

# Minimum interval between two resends of the same command (seconds)
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


# Expected format: "x=0.123 y=-0.045 angle=12.3 mode=forward"
STATUS_PATTERN = re.compile(
    r"x=(-?[\d.]+)\s+y=(-?[\d.]+)\s+angle=(-?[\d.]+)\s+mode=(\w+)"
)


def parse_status_line(line):
    """Extracts (x, y, angle, mode) from a robot status line, or None if not recognized."""
    match = STATUS_PATTERN.search(line)
    if not match:
        return None
    x_str, y_str, angle_str, mode_str = match.groups()
    return float(x_str), float(y_str), float(angle_str), mode_str


def setup_dashboard():
    """Creates the dashboard window (live trajectory) and returns the relevant objects."""
    plt.ion()
    fig, ax = plt.subplots(figsize=(5, 5))
    fig.canvas.manager.set_window_title("Dashboard - Robot Trajectory")
    ax.set_title("Robot trajectory (odometry)")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.grid(True)
    ax.set_aspect("equal", adjustable="datalim")

    trajectory_line, = ax.plot([], [], "-b", linewidth=1.5, label="Trajectory")
    current_point, = ax.plot([], [], "ro", markersize=9, label="Current position")
    status_text = ax.text(
        0.02, 0.98, "Waiting for data...",
        transform=ax.transAxes, va="top", fontsize=10,
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.85),
    )
    ax.legend(loc="lower right")
    fig.tight_layout()

    return fig, ax, trajectory_line, current_point, status_text


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

    # Setting up the dashboard (live trajectory)
    fig, ax, trajectory_line, current_point, status_text = setup_dashboard()
    traj_x, traj_y = [], []
    last_status = (0.0, 0.0, 0.0, "stop")
    last_plot_update = time.monotonic()
    PLOT_INTERVAL = 0.1  # refreshes the chart at most 10 times/second

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
                # robot status messages (x=... y=... angle=... mode=...).
                while ser.in_waiting:
                    try:
                        robot_line = ser.readline().decode(errors="ignore").strip()
                    except Exception:
                        break
                    if robot_line and not robot_line.startswith('{"cmd"'):
                        parsed = parse_status_line(robot_line)
                        if parsed is not None:
                            last_status = parsed
                            traj_x.append(parsed[0])
                            traj_y.append(parsed[1])

                        now_print = time.monotonic()
                        if now_print - last_print_time > PRINT_INTERVAL:
                            print(f"[Robot] {robot_line}")
                            last_print_time = now_print

                # Refreshing the dashboard (live trajectory), at a limited rate
                now_plot = time.monotonic()
                if traj_x and (now_plot - last_plot_update) > PLOT_INTERVAL:
                    trajectory_line.set_data(traj_x, traj_y)
                    current_point.set_data([traj_x[-1]], [traj_y[-1]])
                    ax.relim()
                    ax.autoscale_view()
                    _, _, last_angle, last_mode = last_status
                    status_text.set_text(
                        f"Mode: {last_mode}\n"
                        f"Angle: {last_angle:.1f}\u00b0\n"
                        f"x={traj_x[-1]:.3f} y={traj_y[-1]:.3f}"
                    )
                    fig.canvas.draw_idle()
                    fig.canvas.flush_events()
                    last_plot_update = now_plot

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
        plt.close(fig)
        ser.close()
        print("Resources released cleanly.")


if __name__ == "__main__":
    main()
