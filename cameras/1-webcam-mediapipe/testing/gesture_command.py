"""
Step 3: Precise gesture recognition and mapping to commands
-------------------------------------------------------------------------
4 recognized gestures:
- Closed fist           -> STOP
- Open hand             -> FORWARD
- Index + thumb raised  -> TURN LEFT
- Index + pinky raised  -> TURN RIGHT
Press 'q' to quit.
"""

import cv2
import mediapipe as mp

mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils

# MediaPipe indices: tip of each finger (thumb, index, middle, ring, pinky)
FINGER_TIPS = [4, 8, 12, 16, 20]


def get_finger_states(hand_landmarks, handedness_label):
    """Returns a tuple of 5 booleans (thumb, index, middle, ring, pinky)."""
    landmarks = hand_landmarks.landmark
    states = []

    # Thumb: horizontal comparison, direction depends on left/right hand
    if handedness_label == "Right":
        thumb_up = landmarks[FINGER_TIPS[0]].x < landmarks[FINGER_TIPS[0] - 1].x
    else:
        thumb_up = landmarks[FINGER_TIPS[0]].x > landmarks[FINGER_TIPS[0] - 1].x
    states.append(thumb_up)

    # The other 4 fingers: vertical comparison (tip above the joint)
    for tip_id in FINGER_TIPS[1:]:
        states.append(landmarks[tip_id].y < landmarks[tip_id - 2].y)

    return tuple(states)  # (thumb, index, middle, ring, pinky)


def classify_gesture(finger_states):
    """Maps a finger pattern to a robot command."""
    thumb, index, middle, ring, pinky = finger_states

    if not thumb and not index and not middle and not ring and not pinky:
        return "FORWARD", "Closed fist"

    if thumb and index and middle and ring and pinky:
        return "STOP", "Open hand"

    if thumb and index and not middle and not ring and not pinky:
        return "TURN LEFT", "Index + thumb"

    if not thumb and index and not middle and not ring and pinky:
        return "TURN RIGHT", "Index + pinky"

    return "NO COMMAND", "Gesture not recognized"


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

            command_text = "No hand detected"
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
                frame, f"Gesture: {gesture_name}", (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2
            )
            cv2.putText(
                frame, f"Command: {command_text}", (20, 80),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2
            )

            cv2.imshow("Gesture Recognition - IOT Car", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
