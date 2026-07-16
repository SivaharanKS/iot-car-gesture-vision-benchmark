"""
Step 1: Webcam test
----------------------------
This script simply checks that your webcam is properly detected
and displays the live video stream.
Press 'q' to quit.
"""

import cv2

def main():
    # 0 = default webcam. If you have several cameras, try 1, 2...
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("Error: unable to open the webcam.")
        return

    print("Webcam opened successfully. Press 'q' to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: unable to read the frame.")
            break

        # Horizontal mirror for a more natural display
        frame = cv2.flip(frame, 1)

        cv2.imshow("Webcam Test - IOT Car", frame)

        # Quit with the 'q' key
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
