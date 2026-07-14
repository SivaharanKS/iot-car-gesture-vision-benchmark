import json
import os
import shutil
from PIL import Image

# ----------------------------------------------------------------
DOSSIER_EXPORT = "."                    # dossier contenant info.labels, training/, testing/
DOSSIER_SORTIE = "dataset_yolo"         # dossier de sortie pret pour Ultralytics
# ----------------------------------------------------------------

with open(os.path.join(DOSSIER_EXPORT, "info.labels"), "r", encoding="utf-8") as f:
    data = json.load(f)

# 1) Recuperer la liste des classes (triee, pour un ordre stable)
classes = sorted({
    bb["label"]
    for entry in data["files"]
    for bb in entry.get("boundingBoxes", [])
})
class_to_id = {nom: i for i, nom in enumerate(classes)}
print("Classes detectees :", class_to_id)

# 2) Preparer les dossiers de sortie
for split in ["train", "val"]:
    os.makedirs(os.path.join(DOSSIER_SORTIE, "images", split), exist_ok=True)
    os.makedirs(os.path.join(DOSSIER_SORTIE, "labels", split), exist_ok=True)

CATEGORIE_VERS_SPLIT = {"training": "train", "testing": "val"}

# 3) Convertir chaque image + ses boites
compteur = {"train": 0, "val": 0}

for entry in data["files"]:
    chemin_image = os.path.join(DOSSIER_EXPORT, entry["path"])
    if not os.path.exists(chemin_image):
        print("Introuvable, ignore :", chemin_image)
        continue

    split = CATEGORIE_VERS_SPLIT.get(entry["category"])
    if split is None:
        continue

    nom_fichier = os.path.basename(entry["path"])
    nom_base, _ = os.path.splitext(nom_fichier)

    # Copier l'image
    dest_image = os.path.join(DOSSIER_SORTIE, "images", split, nom_fichier)
    shutil.copy2(chemin_image, dest_image)

    # Recuperer les dimensions reelles de l'image
    with Image.open(chemin_image) as img:
        largeur_img, hauteur_img = img.size

    # Convertir chaque bounding box au format YOLO (normalise, centre)
    lignes = []
    for bb in entry.get("boundingBoxes", []):
        class_id = class_to_id[bb["label"]]
        x_centre = (bb["x"] + bb["width"] / 2) / largeur_img
        y_centre = (bb["y"] + bb["height"] / 2) / hauteur_img
        w_norm = bb["width"] / largeur_img
        h_norm = bb["height"] / hauteur_img
        lignes.append(f"{class_id} {x_centre:.6f} {y_centre:.6f} {w_norm:.6f} {h_norm:.6f}")

    dest_label = os.path.join(DOSSIER_SORTIE, "labels", split, nom_base + ".txt")
    with open(dest_label, "w") as f:
        f.write("\n".join(lignes))

    compteur[split] += 1

print("Conversion terminee :", compteur)

# 4) Generer le fichier de config gestures.yaml
yaml_content = "path: ./dataset_yolo\ntrain: images/train\nval: images/val\n\nnames:\n"
for nom, i in sorted(class_to_id.items(), key=lambda kv: kv[1]):
    yaml_content += f"  {i}: {nom}\n"

with open("gestures.yaml", "w") as f:
    f.write(yaml_content)

print("Fichier gestures.yaml genere.")