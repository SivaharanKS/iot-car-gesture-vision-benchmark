"""
huskylens_training.py
===========================
Helps train the 5 gesture classes on the HuskyLens, in "Object
Classification" mode, directly from the PC (more convenient than the
camera's physical buttons).

Position your gesture in front of the HuskyLens (look at its built-in
screen to see what it sees). For each gesture, training is done in
several BATCHES (2 batches of 15 captures by default, one capture per
second), with a pause between each batch (press Enter to continue).
This leaves time to reposition yourself or take a breath between two
capture series. Each call to learn() adds a sample, it does not
replace the previous ones -- DFRobot recommends more than 30 photos
per class for good accuracy.

Order of the classes to train:
    ID 1 = Forward  (closed fist)
    ID 2 = Stop     (open hand)
    ID 3 = Left     (index + thumb)
    ID 4 = Right    (index + pinky)
    ID 5 = Neutral  (no hand / rest position)

Prerequisites: pip install pyserial pypng, and the huskylib.py file in
the same folder as this script.
"""

import time
from huskylib import HuskyLensLibrary

COM_HUSKY = "COM25"  # HuskyLens serial port

N_PAR_GESTE = 100        # total number of captures (samples) per gesture
N_LOTS = 2              # number of batches per gesture (with a pause between each)
N_PAR_LOT = N_PAR_GESTE // N_LOTS  # captures per batch (50 if 100/2)
DELAI_ENTRE_CAPTURES = 1.0   # seconds between two captures (within the same batch)

GESTES = [
    (1, "Forward (closed fist)"),
    (2, "Stop (open hand)"),
    (3, "Left (index + thumb)"),
    (4, "Right (index + pinky)"),
    (5, "Neutral (no hand / rest)"),
]


def lot_apprentissage(hl, gesture_id, numero_lot):
    """Performs N_PAR_LOT successive captures (one batch), one per second."""
    reussies = 0
    for i in range(N_PAR_LOT):
        resultat = hl.learn(gesture_id)
        if resultat:
            reussies += 1
        print(f"    Batch {numero_lot}: capture {i + 1}/{N_PAR_LOT} "
              f"({reussies} successful)")
        time.sleep(DELAI_ENTRE_CAPTURES)
    return reussies


def rafale_apprentissage(hl, gesture_id, label):
    """Performs the full training of one gesture, in several batches
    separated by a pause (press Enter to continue)."""
    print(f"  Training '{label}' in {N_LOTS} batches of {N_PAR_LOT} captures.")
    total_reussies = 0
    for lot in range(1, N_LOTS + 1):
        input(f"  Ready for batch {lot}/{N_LOTS}? Press Enter to start "
              f"({N_PAR_LOT} captures, 1 per second)...")
        total_reussies += lot_apprentissage(hl, gesture_id, lot)
        if lot < N_LOTS:
            print("  Pause. Reposition yourself if needed before the next batch.\n")
    print(f"  Training of '{label}' complete: "
          f"{total_reussies}/{N_PAR_GESTE} successful captures in total.\n")


def main():
    print("Connecting to the HuskyLens...")
    try:
        hl = HuskyLensLibrary("SERIAL", COM_HUSKY)
        print(hl.knock())
    except Exception as e:
        print(f"Connection error to the HuskyLens ({COM_HUSKY}): {e}")
        return

    hl.algorthim("ALGORITHM_OBJECT_CLASSIFICATION")
    print("'Object Classification' algorithm enabled.\n")

    reponse = input(
        "Do you want to reset the already-learned classes before starting? (y/n): "
    )
    if reponse.strip().lower() == "y":
        hl.forget()
        print("Previous classes erased.\n")

    for gesture_id, label in GESTES:
        input(f"Position the '{label}' gesture in front of the camera, "
              f"then press Enter to start the burst (ID={gesture_id})...")
        rafale_apprentissage(hl, gesture_id, label)

    print("Training of the 5 classes complete "
          f"({N_PAR_GESTE} samples per gesture).")
    print("You can now run huskylens_to_serial.py to control the robot.")


if __name__ == "__main__":
    main()
