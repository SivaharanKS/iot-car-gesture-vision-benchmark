"""
Etape 2 : Detection des gestes de la main
-------------------------------------------
Ce script utilise MediaPipe pour detecter une main sur le flux webcam
et affiche les points cles (landmarks) ainsi qu'un exemple simple
de reconnaissance de geste (compter les doigts leves).
Appuie sur 'q' pour quitter.
"""

import cv2
import mediapipe as mp

mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils

# Indices des bouts de doigts (tip) dans le modele MediaPipe
FINGER_TIPS = [4, 8, 12, 16, 20]


def count_fingers(hand_landmarks, handedness_label):
    """Compte le nombre de doigts leves sur une main detectee."""
    landmarks = hand_landmarks.landmark
    fingers_up = 0

    # Pouce : comparaison horizontale (depend de la main gauche/droite)
    if handedness_label == "Right":
        if landmarks[FINGER_TIPS[0]].x < landmarks[FINGER_TIPS[0] - 1].x:
            fingers_up += 1
    else:
        if landmarks[FINGER_TIPS[0]].x > landmarks[FINGER_TIPS[0] - 1].x:
            fingers_up += 1

    # Les 4 autres doigts : comparaison verticale (tip au-dessus de l'articulation)
    for tip_id in FINGER_TIPS[1:]:
        if landmarks[tip_id].y < landmarks[tip_id - 2].y:
            fingers_up += 1

    return fingers_up


def main():
    cap = cv2.VideoCapture(0)

    with mp_hands.Hands(
        max_num_hands=1,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.7,
    ) as hands:

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(rgb_frame)

            gesture_text = "Aucune main detectee"

            if results.multi_hand_landmarks and results.multi_handedness:
                for hand_landmarks, handedness in zip(
                    results.multi_hand_landmarks, results.multi_handedness
                ):
                    mp_draw.draw_landmarks(
                        frame, hand_landmarks, mp_hands.HAND_CONNECTIONS
                    )

                    label = handedness.classification[0].label
                    nb_doigts = count_fingers(hand_landmarks, label)
                    gesture_text = f"Doigts leves : {nb_doigts}"

            cv2.putText(
                frame, gesture_text, (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2
            )

            cv2.imshow("Detection de gestes - IOT Car", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
