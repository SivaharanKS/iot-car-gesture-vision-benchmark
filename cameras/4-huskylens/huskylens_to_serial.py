"""
huskylens_to_serial.py
=======================
Direct reading of the HuskyLens over its USB port (official huskylib.py
library), mapping the recognized gesture (learned ID) to a JSON command,
and sending that command to the robot over a second serial port.

Architecture:
    HuskyLens --(USB, direct serial port)--> PC --(USB)--> RP2040 Robot

Prerequisites:
    - pip install pyserial pypng
    - The huskylib.py file (downloaded from
      https://github.com/HuskyLens/HUSKYLENSPython/tree/master/HUSKYLENS)
      must be located in the same folder as this script.
    - The HuskyLens must have been trained in "Object Classification" mode
      with the following 5 classes (same IDs as the mapping below):
          ID 1 = Forward  (closed fist)
          ID 2 = Stop     (open hand)
          ID 3 = Left     (index + thumb)
          ID 4 = Right    (index + pinky)
          ID 5 = Neutral  (no hand / rest position)
"""

import time
import json
import serial
from huskylib import HuskyLensLibrary

# ----------------------------------------------------------------
# Parameters to adapt
# ----------------------------------------------------------------
COM_HUSKY = "COM25"   # HuskyLens serial port
COM_ROBOT = "COM22"   # RP2040 robot serial port
BAUDRATE_ROBOT = 115200

SEND_INTERVAL = 0.15   # periodic resend of the active command (seconds),
                       # the robot stops automatically after 0.4s of silence
CONFIRM_COUNT = 5      # number of identical consecutive detections required
                       # before validating a gesture change (anti-false-positive)

ID_TO_COMMAND = {
    1: "forward",
    2: "stop",
    3: "turn_left",
    4: "turn_right",
    # 5 (neutral) and any unknown ID -> no direct mapping, treated as "stop"
}

GESTE_LABEL = {
    1: "Forward",
    2: "Stop",
    3: "Left",
    4: "Right",
    5: "Neutral",
}


def lire_id_geste(hl):
    """Queries the HuskyLens and returns the ID of the detected gesture,
    or None if nothing is detected.

    Note: the learned() method of huskylib.py directly returns a
    single Block object (not a list as the official documentation
    suggests) -- a behavior documented in issue #18 of the
    HUSKYLENSPython repository (https://github.com/HuskyLens/HUSKYLENSPython/issues/18).
    """
    try:
        objet = hl.learned()
    except Exception:
        return None
    if not objet:
        return None
    return getattr(objet, "ID", None)


def main():
    print("Connecting to the HuskyLens...")
    try:
        hl = HuskyLensLibrary("SERIAL", COM_HUSKY)
        print(hl.knock())
        hl.algorthim("ALGORITHM_OBJECT_CLASSIFICATION")
    except Exception as e:
        print(f"Connection error to the HuskyLens ({COM_HUSKY}): {e}")
        return

    print("Connecting to the robot...")
    try:
        ser_robot = serial.Serial(COM_ROBOT, BAUDRATE_ROBOT, timeout=0)
    except serial.SerialException as e:
        print(f"Connection error to the robot ({COM_ROBOT}): {e}")
        return

    # Software restart of the robot (exit REPL / raw REPL then relaunch
    # code.py), essential to make sure the robot is actually running
    # code.py and is not stuck at the interactive prompt (>>>).
    time.sleep(0.3)
    ser_robot.write(b'\x03')
    time.sleep(0.2)
    ser_robot.write(b'\x02')
    time.sleep(0.2)
    ser_robot.write(b'\x04')
    print("Restarting the robot...")

    boot_deadline = time.monotonic() + 3.0
    while time.monotonic() < boot_deadline:
        if ser_robot.in_waiting:
            boot_line = ser_robot.readline().decode(errors="ignore").strip()
            if boot_line:
                print(f"[Boot] {boot_line}")
        time.sleep(0.02)

    print("System ready. Ctrl+C to stop.\n")

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

            # --- Confirmation-based filtering (anti-false-positive) ---
            if detected_id == candidate_id:
                candidate_count += 1
            else:
                candidate_id = detected_id
                candidate_count = 1

            if candidate_count >= CONFIRM_COUNT:
                stable_id = candidate_id

            # --- Determining the command to send ---
            cmd = ID_TO_COMMAND.get(stable_id, "stop")

            now = time.monotonic()
            if now - last_send_time >= SEND_INTERVAL:
                message = json.dumps({"cmd": cmd}) + "\n"
                ser_robot.write(message.encode())
                last_send_time = now

                if stable_id != last_print_id:
                    label = GESTE_LABEL.get(stable_id, "Unknown")
                    print(f"[HuskyLens] Stable gesture: {label} (ID={stable_id}) -> {cmd}")
                    last_print_id = stable_id

            # --- Displaying the messages returned by the robot (status) ---
            # Allows checking that the robot is correctly receiving commands and
            # running its control_loop (odometry, current mode, etc.)
            while ser_robot.in_waiting:
                robot_line = ser_robot.readline().decode(errors="ignore").strip()
                if robot_line:
                    now_print = time.monotonic()
                    if now_print - last_status_print_time > STATUS_PRINT_INTERVAL:
                        print(f"  [Robot] {robot_line}")
                        last_status_print_time = now_print

            time.sleep(0.02)

    except KeyboardInterrupt:
        print("\nStop requested by the user.")
    finally:
        ser_robot.close()


if __name__ == "__main__":
    main()
