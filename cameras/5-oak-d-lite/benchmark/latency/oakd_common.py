import depthai as dai
import numpy as np

BLOB_PATH = "best.blob"
LABELS = ["Forward", "Left", "Right", "Stop"]
INPUT_SIZE = 320
CONF_THRESHOLD = 0.5


def decoder_yolo(output_tensor, conf_threshold=CONF_THRESHOLD):
    data = output_tensor.reshape(8, -1).T
    scores_classes = data[:, 4:8]
    class_ids = np.argmax(scores_classes, axis=1)
    scores = scores_classes[np.arange(len(class_ids)), class_ids]

    meilleur_idx = np.argmax(scores)
    if scores[meilleur_idx] < conf_threshold:
        return "none", 0.0

    return LABELS[class_ids[meilleur_idx]], float(scores[meilleur_idx])


def creer_pipeline():
    pipeline = dai.Pipeline()
    cam = pipeline.create(dai.node.Camera).build()
    camOut = cam.requestOutput((INPUT_SIZE, INPUT_SIZE), type=dai.ImgFrame.Type.BGR888p)

    nn = pipeline.create(dai.node.NeuralNetwork)
    nn.setBlobPath(BLOB_PATH)
    camOut.link(nn.input)

    nnQueue = nn.out.createOutputQueue()
    return pipeline, nnQueue

def creer_pipeline_avec_preview():
    """Variante qui expose aussi le flux image (pour associer timestamps)."""
    pipeline = dai.Pipeline()
    cam = pipeline.create(dai.node.Camera).build()
    camOut = cam.requestOutput((INPUT_SIZE, INPUT_SIZE), type=dai.ImgFrame.Type.BGR888p)

    nn = pipeline.create(dai.node.NeuralNetwork)
    nn.setBlobPath(BLOB_PATH)
    camOut.link(nn.input)

    previewQueue = camOut.createOutputQueue()
    nnQueue = nn.out.createOutputQueue()
    return pipeline, previewQueue, nnQueue