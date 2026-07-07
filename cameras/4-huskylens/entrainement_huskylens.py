"""
entrainement_huskylens.py
===========================
Aide a l'entrainement des 5 classes de gestes sur la HuskyLens, en mode
"Object Classification", directement depuis le PC (plus pratique que les
boutons physiques de la camera).

Positionne ton geste devant la HuskyLens (regarde son ecran integre pour
voir ce qu'elle voit). Pour chaque geste, l'entrainement se fait en
plusieurs LOTS (par defaut 2 lots de 15 captures, une capture par
seconde), avec une pause entre chaque lot (appui sur Entree pour
continuer). Cela laisse le temps de se repositionner ou de souffler
entre deux series de captures. Chaque appel a learn() ajoute un
echantillon, il ne remplace pas les precedents -- DFRobot recommande
plus de 30 photos par classe pour une bonne precision.

Ordre des classes a entrainer :
    ID 1 = Avancer  (poing ferme)
    ID 2 = Stop     (main ouverte)
    ID 3 = Gauche   (index + pouce)
    ID 4 = Droite   (index + auriculaire)
    ID 5 = Neutre   (main absente / position de repos)

Prerequis : pip install pyserial pypng, et le fichier huskylib.py dans
le meme dossier que ce script.
"""

import time
from huskylib import HuskyLensLibrary

COM_HUSKY = "COM25"  # port serie de la HuskyLens

N_PAR_GESTE = 100        # nombre total de captures (echantillons) par geste
N_LOTS = 2              # nombre de lots par geste (avec pause entre chaque)
N_PAR_LOT = N_PAR_GESTE // N_LOTS  # captures par lot (50 si 100/2)
DELAI_ENTRE_CAPTURES = 1.0   # secondes entre deux captures (dans un meme lot)

GESTES = [
    (1, "Avancer (poing ferme)"),
    (2, "Stop (main ouverte)"),
    (3, "Gauche (index + pouce)"),
    (4, "Droite (index + auriculaire)"),
    (5, "Neutre (main absente / repos)"),
]


def lot_apprentissage(hl, gesture_id, numero_lot):
    """Effectue N_PAR_LOT captures successives (un lot), une par seconde."""
    reussies = 0
    for i in range(N_PAR_LOT):
        resultat = hl.learn(gesture_id)
        if resultat:
            reussies += 1
        print(f"    Lot {numero_lot} : capture {i + 1}/{N_PAR_LOT} "
              f"({reussies} reussies)")
        time.sleep(DELAI_ENTRE_CAPTURES)
    return reussies


def rafale_apprentissage(hl, gesture_id, label):
    """Effectue l'entrainement complet d'un geste, en plusieurs lots
    separes par une pause (appui sur Entree pour continuer)."""
    print(f"  Entrainement de '{label}' en {N_LOTS} lots de {N_PAR_LOT} captures.")
    total_reussies = 0
    for lot in range(1, N_LOTS + 1):
        input(f"  Pret pour le lot {lot}/{N_LOTS} ? Appuie sur Entree pour lancer "
              f"({N_PAR_LOT} captures, 1 par seconde)...")
        total_reussies += lot_apprentissage(hl, gesture_id, lot)
        if lot < N_LOTS:
            print("  Pause. Repositionne-toi si besoin avant le prochain lot.\n")
    print(f"  Entrainement de '{label}' termine : "
          f"{total_reussies}/{N_PAR_GESTE} captures reussies au total.\n")


def main():
    print("Connexion a la HuskyLens...")
    try:
        hl = HuskyLensLibrary("SERIAL", COM_HUSKY)
        print(hl.knock())
    except Exception as e:
        print(f"Erreur de connexion a la HuskyLens ({COM_HUSKY}) : {e}")
        return

    hl.algorthim("ALGORITHM_OBJECT_CLASSIFICATION")
    print("Algorithme 'Object Classification' active.\n")

    reponse = input(
        "Veux-tu remettre a zero les classes deja apprises avant de commencer ? (o/n) : "
    )
    if reponse.strip().lower() == "o":
        hl.forget()
        print("Classes precedentes effacees.\n")

    for gesture_id, label in GESTES:
        input(f"Positionne le geste '{label}' devant la camera, "
              f"puis appuie sur Entree pour lancer la rafale (ID={gesture_id})...")
        rafale_apprentissage(hl, gesture_id, label)

    print("Entrainement des 5 classes termine "
          f"({N_PAR_GESTE} echantillons par geste).")
    print("Tu peux maintenant lancer huskylens_to_serial.py pour piloter le robot.")


if __name__ == "__main__":
    main()