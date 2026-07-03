"""
Etape 1 : Test de la webcam
----------------------------
Ce script verifie simplement que ta webcam est bien detectee
et affiche le flux video en direct.
Appuie sur 'q' pour quitter.
"""

import cv2

def main():
    # 0 = webcam par defaut. Si tu as plusieurs cameras, essaie 1, 2...
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("Erreur : impossible d'ouvrir la webcam.")
        return

    print("Webcam ouverte avec succes. Appuie sur 'q' pour quitter.")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Erreur : impossible de lire l'image.")
            break

        # Miroir horizontal pour un affichage plus naturel
        frame = cv2.flip(frame, 1)

        cv2.imshow("Test Webcam - IOT Car", frame)

        # Quitter avec la touche 'q'
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
