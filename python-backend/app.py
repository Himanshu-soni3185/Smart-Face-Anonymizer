import cv2
import os
import uuid
import time
import threading
import urllib.request
from flask import Flask, request, jsonify, send_file, Response
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

# Max file size: 100 MB
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

# --- YuNet ONNX Face Detector (OpenCV built-in, no extra packages) ---
YUNET_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
YUNET_PATH = os.path.join(MODEL_DIR, "face_detection_yunet_2023mar.onnx")

def download_model():
    """Download YuNet ONNX model if not already cached (~350 KB)."""
    if not os.path.exists(YUNET_PATH):
        print("Downloading YuNet face detection model (~350 KB)...")
        urllib.request.urlretrieve(YUNET_URL, YUNET_PATH)
    print("YuNet model ready!")

download_model()

# score_threshold 0.6 = good balance; raise to 0.7 to cut false positives
face_detector = cv2.FaceDetectorYN.create(
    YUNET_PATH,
    "",           # config string (empty for ONNX)
    (320, 320),   # will be overridden per-frame via setInputSize
    score_threshold=0.6,
    nms_threshold=0.3,
    top_k=5000,
)
face_detector_lock = threading.Lock()
# In-memory job progress store  {job_id: {"progress": 0..100, "status": "processing"|"done"|"error"}}
job_store = {}


# ──────────────────────────────────────────────────────────
# Face detection helper  (YuNet)
# ──────────────────────────────────────────────────────────
def detect_faces_yunet(frame):
    """
    Detect faces with YuNet ONNX.
    Returns list of (x, y, w, h) in frame coordinates.
    """
    h, w = frame.shape[:2]
    with face_detector_lock:
        face_detector.setInputSize((w, h))
        _, detections = face_detector.detect(frame)

    if detections is None:
        return []

    faces = []
    for det in detections:
        x, y, fw, fh = int(det[0]), int(det[1]), int(det[2]), int(det[3])
        x  = max(0, x)
        y  = max(0, y)
        fw = min(fw, w - x)
        fh = min(fh, h - y)
        if fw > 0 and fh > 0:
            faces.append((x, y, fw, fh))
    return faces


def apply_blur(image, faces):
    """Apply strong smooth Gaussian blur — classic TV/news style anonymization."""
    for (x, y, w, h) in faces:
        if w < 1 or h < 1:
            continue
        face_roi = image[y:y+h, x:x+w]
        # Kernel size scales with face size for consistent heavy blur
        # Minimum 51px, always odd
        k = max(51, (min(w, h) // 2) | 1)
        blurred = cv2.GaussianBlur(face_roi, (k, k), 0)
        # Second pass for extra strength
        blurred = cv2.GaussianBlur(blurred, (k, k), 0)
        image[y:y+h, x:x+w] = blurred
    return image


# ──────────────────────────────────────────────────────────
# Image processing
# ──────────────────────────────────────────────────────────
def blur_image(image_path, output_path):
    image = cv2.imread(image_path)
    if image is None:
        return False, "Could not read image"

    # ★ Downscale large images before inference (speeds up DNN dramatically)
    h, w = image.shape[:2]
    scale = 1.0
    MAX_DIM = 1280
    if max(h, w) > MAX_DIM:
        scale = MAX_DIM / max(h, w)
        small = cv2.resize(image, (int(w * scale), int(h * scale)))
    else:
        small = image

    faces_small = detect_faces_yunet(small)
    # Scale boxes back to original resolution
    if scale != 1.0:
        faces = [(int(x/scale), int(y/scale), int(fw/scale), int(fh/scale))
                 for (x, y, fw, fh) in faces_small]
    else:
        faces = faces_small

    print(f"Detected {len(faces)} face(s) in image")
    image = apply_blur(image, faces)

    # ★ Save as JPEG (much faster than PNG, good enough for anonymized output)
    out_jpg = os.path.splitext(output_path)[0] + ".jpg"
    encode_params = [cv2.IMWRITE_JPEG_QUALITY, 88]
    cv2.imwrite(out_jpg, image, encode_params)
    return True, out_jpg


# ──────────────────────────────────────────────────────────
# Video processing  (background thread)
# ──────────────────────────────────────────────────────────
def blur_video_task(video_path, output_path, job_id, skip_frames=2):
    """
    Process video in a background thread.
    skip_frames=2 → run face detection every 2nd frame, reuse boxes for skipped frames.
    skip_frames=1 → detect every frame (slowest, most accurate).
    """
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            job_store[job_id] = {"status": "error", "message": "Could not open video"}
            return

        width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps    = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1

        # ★ Scale down for DNN while writing at original resolution
        MAX_DIM = 640
        scale = 1.0
        if max(width, height) > MAX_DIM:
            scale = MAX_DIM / max(width, height)

        # ★ Use mp4v codec → standard .mp4, smaller file, faster encode than VP80
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

        frame_idx = 0
        last_faces = []

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # Detect only on every Nth frame
            if frame_idx % skip_frames == 0:
                if scale != 1.0:
                    small = cv2.resize(frame, (int(width*scale), int(height*scale)))
                    faces_small = detect_faces_yunet(small)
                    last_faces = [(int(x/scale), int(y/scale), int(fw/scale), int(fh/scale))
                                  for (x, y, fw, fh) in faces_small]
                else:
                    last_faces = detect_faces_yunet(frame)

            frame = apply_blur(frame, last_faces)
            out.write(frame)
            frame_idx += 1

            # Update progress
            job_store[job_id]["progress"] = int(frame_idx / total * 95)

        cap.release()
        out.release()
        print(f"Video done: {frame_idx} frames → {output_path}")
        job_store[job_id] = {"status": "done", "progress": 100, "output": output_path}

    except Exception as e:
        job_store[job_id] = {"status": "error", "message": str(e)}
    finally:
        # Clean up input
        try:
            os.remove(video_path)
        except Exception:
            pass


# ──────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────
@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})


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

    input_path = os.path.join(UPLOAD_FOLDER, f"{unique_id}_input{ext}")
    file.save(input_path)

    image_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}
    video_exts = {'.mp4', '.avi', '.mov', '.mkv', '.webm'}

    if ext in image_exts:
        output_path = os.path.join(OUTPUT_FOLDER, f"{unique_id}_output.jpg")
        success, res = blur_image(input_path, output_path)
        try:
            os.remove(input_path)
        except Exception:
            pass
        if not success:
            return jsonify({'error': res}), 500
        # ★ Schedule file cleanup after 5 minutes
        def _cleanup(path, delay=300):
            time.sleep(delay)
            try: os.remove(path)
            except Exception: pass
        threading.Thread(target=_cleanup, args=(res,), daemon=True).start()
        return send_file(res, mimetype='image/jpeg', as_attachment=True,
                         download_name=f"anonymized_{os.path.splitext(filename)[0]}.jpg")

    elif ext in video_exts:
        job_id = unique_id
        output_path = os.path.join(OUTPUT_FOLDER, f"{unique_id}_output.mp4")
        job_store[job_id] = {"status": "processing", "progress": 0}
        t = threading.Thread(
            target=blur_video_task,
            args=(input_path, output_path, job_id),
            daemon=True
        )
        t.start()
        return jsonify({"job_id": job_id}), 202

    else:
        try: os.remove(input_path)
        except Exception: pass
        return jsonify({'error': 'Unsupported file type'}), 400


@app.route('/progress/<job_id>', methods=['GET'])
def get_progress(job_id):
    """Server-Sent Events stream for video progress."""
    def generate():
        while True:
            info = job_store.get(job_id, {"status": "unknown", "progress": 0})
            import json
            data = json.dumps(info)
            yield f"data: {data}\n\n"
            if info.get("status") in ("done", "error", "unknown"):
                break
            time.sleep(0.5)

    return Response(generate(), mimetype='text/event-stream',
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route('/download/<job_id>', methods=['GET'])
def download_result(job_id):
    info = job_store.get(job_id)
    if not info or info.get("status") != "done":
        return jsonify({"error": "Job not ready or not found"}), 404

    output_path = info.get("output")
    if not output_path or not os.path.exists(output_path):
        return jsonify({"error": "Output file missing"}), 404

    # Schedule cleanup after download
    def _cleanup(path, delay=120):
        time.sleep(delay)
        try: os.remove(path)
        except Exception: pass
    threading.Thread(target=_cleanup, args=(output_path,), daemon=True).start()
    del job_store[job_id]

    return send_file(output_path, mimetype='video/mp4', as_attachment=True,
                     download_name=f"anonymized_video.mp4")


if __name__ == '__main__':
    # Use threaded=True for concurrent requests (images + video)
    app.run(debug=False, port=5000, threaded=True)
