import cv2
import os
import uuid
import urllib.request
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'outputs'
MODEL_DIR = 'models'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER

# --- OpenCV DNN Face Detector (much more accurate than Haar) ---
PROTOTXT_URL = "https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/face_detector/deploy.prototxt"
MODEL_URL = "https://raw.githubusercontent.com/opencv/opencv_3rdparty/dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel"
PROTOTXT_PATH = os.path.join(MODEL_DIR, "deploy.prototxt")
MODEL_PATH = os.path.join(MODEL_DIR, "res10_300x300_ssd_iter_140000.caffemodel")

def download_model():
    """Download the DNN face detection model if not present."""
    if not os.path.exists(PROTOTXT_PATH):
        print("Downloading face detection prototxt...")
        urllib.request.urlretrieve(PROTOTXT_URL, PROTOTXT_PATH)
    if not os.path.exists(MODEL_PATH):
        print("Downloading face detection model (5MB)...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    print("Face detection model ready!")

download_model()
face_net = cv2.dnn.readNetFromCaffe(PROTOTXT_PATH, MODEL_PATH)

CONFIDENCE_THRESHOLD = 0.35  # Lower threshold = catches more faces


def detect_faces_dnn(frame):
    """Detect faces using OpenCV DNN SSD model. Returns list of (x, y, w, h)."""
    h, w = frame.shape[:2]
    blob = cv2.dnn.blobFromImage(frame, 1.0, (300, 300), (104.0, 177.0, 123.0))
    face_net.setInput(blob)
    detections = face_net.forward()

    faces = []
    for i in range(detections.shape[2]):
        confidence = detections[0, 0, i, 2]
        if confidence > CONFIDENCE_THRESHOLD:
            box = detections[0, 0, i, 3:7] * [w, h, w, h]
            x1, y1, x2, y2 = box.astype("int")
            # Clamp to image boundaries
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(w, x2)
            y2 = min(h, y2)
            if x2 > x1 and y2 > y1:
                faces.append((x1, y1, x2 - x1, y2 - y1))
    return faces


def blur_image(image_path, output_path):
    image = cv2.imread(image_path)
    if image is None:
        return False, "Could not read image"

    faces = detect_faces_dnn(image)
    print(f"Detected {len(faces)} face(s) in image")

    for (x, y, w, h) in faces:
        face = image[y:y+h, x:x+w]
        blurred = cv2.GaussianBlur(face, (99, 99), 30)
        image[y:y+h, x:x+w] = blurred

    cv2.imwrite(output_path, image)
    return True, output_path


def blur_video(video_path, output_path):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return False, "Could not open video"

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if fps == 0 or fps != fps:
        fps = 30.0

    fourcc = cv2.VideoWriter_fourcc(*'vp80')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    frame_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1
        faces = detect_faces_dnn(frame)

        for (x, y, w, h) in faces:
            face = frame[y:y+h, x:x+w]
            blurred = cv2.GaussianBlur(face, (99, 99), 30)
            frame[y:y+h, x:x+w] = blurred

        out.write(frame)

        if frame_count % 30 == 0:
            print(f"Processing frame {frame_count}/{total_frames}...")

    cap.release()
    out.release()
    print(f"Video processing complete! {frame_count} frames processed.")
    return True, output_path


@app.route('/process', methods=['POST'])
def process_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    filename = secure_filename(file.filename)
    unique_id = str(uuid.uuid4())
    ext = os.path.splitext(filename)[1].lower()

    input_filename = f"{unique_id}_input{ext}"
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], input_filename)
    file.save(input_path)

    output_filename = f"{unique_id}_output{ext}"
    output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)

    success = False
    error_msg = ""

    image_exts = ['.jpg', '.jpeg', '.png', '.bmp']
    video_exts = ['.mp4', '.avi', '.mov', '.mkv']

    if ext in image_exts:
        success, res = blur_image(input_path, output_path)
        if not success: error_msg = res
    elif ext in video_exts:
        # Save output as webm for better web compatibility
        output_filename = f"{unique_id}_output.webm"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
        success, res = blur_video(input_path, output_path)
        if not success: error_msg = res
    else:
        return jsonify({'error': 'Unsupported file type'}), 400

    if not success:
        return jsonify({'error': error_msg}), 500

    return send_file(output_path, as_attachment=True)


if __name__ == '__main__':
    app.run(debug=True, port=5000)
