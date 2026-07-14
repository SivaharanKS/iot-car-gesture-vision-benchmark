import depthai as dai

BLOB_PATH = "best.blob"
INPUT_SIZE = 320

with dai.Pipeline() as pipeline:
    cam = pipeline.create(dai.node.Camera).build()
    camOut = cam.requestOutput((INPUT_SIZE, INPUT_SIZE), type=dai.ImgFrame.Type.BGR888p)

    nn = pipeline.create(dai.node.NeuralNetwork)
    nn.setBlobPath(BLOB_PATH)
    camOut.link(nn.input)

    nnQueue = nn.out.createOutputQueue()

    pipeline.start()
    inNn = nnQueue.get()

    print("Noms des tenseurs de sortie :", inNn.getAllLayerNames())
    for nom in inNn.getAllLayerNames():
        tensor = inNn.getTensor(nom)
        print(f"  {nom} -> shape={tensor.shape}, dtype={tensor.dtype}")