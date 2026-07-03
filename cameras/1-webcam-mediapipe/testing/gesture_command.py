"""
Etape 3 : Reconnaissance de gestes precis et mapping vers des commandes
-------------------------------------------------------------------------
4 gestes reconnus :
- Poing ferme          -> STOP
- Main ouverte          -> AVANCER
- Index + pouce leves   -> TOURNER A GAUCHE
- Index + auriculaire   -> TOURNER A DROITE
Appuie sur 'q' pour quitter.
"""

import cv2
import mediapipe as mp

mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils

# Indices MediaPipe : tip de chaque doigt (pouce, index, majeur, annulaire, auriculaire)
FINGER_TIPS = [4, 8, 12, 16, 20]


def get_finger_states(hand_landmarks, handedness_label):
    """Retourne un tuple de 5 booleens (pouce, index, majeur, annulaire, auriculaire)."""
    landmarks = hand_landmarks.landmark
    states = []

    # Pouce : comparaison horizontale, sens depend de la main gauche/droite
    if handedness_label == "Right":
        thumb_up = landmarks[FINGER_TIPS[0]].x < landmarks[FINGER_TIPS[0] - 1].x
    else:
        thumb_up = landmarks[FINGER_TIPS[0]].x > landmarks[FINGER_TIPS[0] - 1].x
    states.append(thumb_up)

    # Les 4 autres doigts : comparaison verticale (tip au-dessus de l'articulation)
    for tip_id in FINGER_TIPS[1:]:
        states.append(landmarks[tip_id].y < landmarks[tip_id - 2].y)

    return tuple(states)  # (pouce, index, majeur, annulaire, auriculaire)


def classify_gesture(finger_states):
    """Associe un pattern de doigts a une commande robot."""
    thumb, index, middle, ring, pinky = finger_states

    if not thumb and not index and not middle and not ring and not pinky:
        return "AVANCER", "Poing ferme"

    if thumb and index and middle and ring and pinky:
        return "STOP", "Main ouverte"

    if thumb and index and not middle and not ring and not pinky:
        return "TOURNER A GAUCHE", "Index + pouce"

    if not thumb and index and not middle and not ring and pinky:
        return "TOURNER A DROITE", "Index + auriculaire"

    return "AUCUNE COMMANDE", "Geste non reconnu"


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

            command_text = "Aucune main detectee"
            gesture_name = ""

            if results.multi_hand_landmarks and results.multi_handedness:
                for hand_landmarks, handedness in zip(
                    results.multi_hand_landmarks, results.multi_handedness
                ):
                    mp_draw.draw_landmarks(
                        frame, hand_landmarks, mp_hands.HAND_CONNECTIONS
                    )

                    label = handedness.classification[0].label
                    finger_states = get_finger_states(hand_landmarks, label)
                    command_text, gesture_name = classify_gesture(finger_states)

            cv2.putText(
                frame, f"Geste : {gesture_name}", (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2
            )
            cv2.putText(
                frame, f"Commande : {command_text}", (20, 80),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2
            )

            cv2.imshow("Reconnaissance de gestes - IOT Car", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
