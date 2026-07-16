import depthai as dai
import cv2

with dai.Pipeline() as pipeline:
    cam = pipeline.create(dai.node.Camera).build()
    videoQueue = cam.requestOutput((640, 480)).createOutputQueue()

    pipeline.start()
    print("Pipeline started. Press 'q' to quit.")

    while pipeline.isRunning():
        videoIn = videoQueue.get()
        frame = videoIn.getCvFrame()
        cv2.imshow("OAK-D Lite - test", frame)

        if cv2.waitKey(1) == ord('q'):
            break

cv2.destroyAllWindows()
