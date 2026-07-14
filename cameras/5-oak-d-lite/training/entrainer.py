from ultralytics import YOLO

model = YOLO("yolov8n.pt")
model.train(data="gestures.yaml", epochs=100, imgsz=320, batch=8)