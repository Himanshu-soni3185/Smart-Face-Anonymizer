"use client";

import { useState, useRef, useEffect } from "react";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND;
const MAX_FILE_MB = 100;

export default function Home() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [stage, setStage] = useState("idle"); // idle | uploading | processing | done | error
  const [uploadPct, setUploadPct] = useState(0);
  const [processPct, setProcessPct] = useState(0);
  const [resultUrl, setResultUrl] = useState(null);
  const [resultMime, setResultMime] = useState(null);
  const [error, setError] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [facesFound, setFacesFound] = useState(null);

  const fileInputRef = useRef(null);
  const sseRef = useRef(null);

  // Cleanup SSE on unmount
  useEffect(() => () => sseRef.current?.close(), []);

  // ── Drag & Drop ──────────────────────────────────────────
  const handleDrag = (e) => {
    e.preventDefault(); e.stopPropagation();
    setDragActive(e.type === "dragenter" || e.type === "dragover");
  };

  const handleDrop = (e) => {
    e.preventDefault(); e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files?.[0]) handleFileChange(e.dataTransfer.files[0]);
  };

  const handleFileChange = (selected) => {
    if (selected.size > MAX_FILE_MB * 1024 * 1024) {
      setError(`File too large. Maximum size is ${MAX_FILE_MB} MB.`);
      return;
    }
    // Reset state
    setFile(selected);
    setResultUrl(null);
    setResultMime(null);
    setError(null);
    setStage("idle");
    setUploadPct(0);
    setProcessPct(0);
    setFacesFound(null);
    sseRef.current?.close();

    const url = URL.createObjectURL(selected);
    setPreview({ url, type: selected.type.startsWith("video/") ? "video" : "image" });
  };

  // ── Upload with XHR for progress ─────────────────────────
  const uploadWithProgress = (formData) =>
    new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${BACKEND}/process`);

      xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable) setUploadPct(Math.round((e.loaded / e.total) * 100));
      });

      xhr.onload = () => {
        if (xhr.status === 200) {
          // Image: direct blob response
          resolve({ type: "image", blob: xhr.response, mime: xhr.getResponseHeader("Content-Type") });
        } else if (xhr.status === 202) {
          // Video: response is a Blob (responseType="blob"), must read as text first
          const reader = new FileReader();
          reader.onload = () => {
            try {
              const data = JSON.parse(reader.result);
              resolve({ type: "video_job", job_id: data.job_id });
            } catch {
              reject(new Error("Invalid server response for video job"));
            }
          };
          reader.readAsText(xhr.response);
        } else {
          // Error: also a Blob — read as text to get the error message
          const reader = new FileReader();
          reader.onload = () => {
            try {
              const err = JSON.parse(reader.result);
              reject(new Error(err.error || "Processing failed"));
            } catch {
              reject(new Error(`Server error (${xhr.status})`));
            }
          };
          reader.readAsText(xhr.response);
        }
      };

      xhr.onerror = () => reject(new Error("Network error. Is the backend running?"));
      xhr.responseType = "blob"; // works for both blob and text (202 JSON)
      xhr.send(formData);
    });

  // ── SSE progress listener for video ──────────────────────
  const trackVideoJob = (jobId) => {
    setStage("processing");
    setProcessPct(0);

    const sse = new EventSource(`${BACKEND}/progress/${jobId}`);
    sseRef.current = sse;

    sse.onmessage = async (e) => {
      const info = JSON.parse(e.data);
      setProcessPct(info.progress ?? 0);

      if (info.status === "done") {
        sse.close();
        setProcessPct(100);
        // Download the result
        const res = await fetch(`${BACKEND}/download/${jobId}`);
        if (!res.ok) { setError("Download failed"); setStage("error"); return; }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        setResultUrl(url);
        setResultMime("video/mp4");
        setStage("done");
      } else if (info.status === "error") {
        sse.close();
        setError(info.message || "Video processing failed");
        setStage("error");
      }
    };

    sse.onerror = () => {
      sse.close();
      setError("Lost connection to server during video processing");
      setStage("error");
    };
  };

  // ── Main action ──────────────────────────────────────────
  const processFile = async () => {
    if (!file) return;
    setStage("uploading");
    setError(null);
    setResultUrl(null);
    setFacesFound(null);
    setUploadPct(0);
    setProcessPct(0);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const result = await uploadWithProgress(formData);

      if (result.type === "image") {
        // Convert blob responseType back properly
        const blob = result.blob instanceof Blob ? result.blob : new Blob([result.blob]);
        const url = URL.createObjectURL(blob);
        setResultUrl(url);
        setResultMime(result.mime || "image/jpeg");
        setStage("done");
      } else if (result.type === "video_job") {
        trackVideoJob(result.job_id);
      }
    } catch (err) {
      setError(err.message);
      setStage("error");
    }
  };

  // ── Derived UI helpers ───────────────────────────────────
  const isVideo = file?.type?.startsWith("video/");
  const isProcessing = stage === "uploading" || stage === "processing";

  const progressLabel = stage === "uploading"
    ? `Uploading… ${uploadPct}%`
    : stage === "processing"
      ? `Anonymizing… ${processPct}%`
      : null;

  const progressValue = stage === "uploading" ? uploadPct : processPct;

  const downloadExt = isVideo ? "mp4" : "jpg";
  const downloadName = `anonymized_${file ? file.name.replace(/\.[^/.]+$/, "") : "file"}.${downloadExt}`;

  return (
    <main className="min-h-screen p-8 md:p-16 flex flex-col items-center justify-center font-sans">
      <div className="w-full max-w-4xl glass-container p-8 md:p-12">
        {/* Header */}
        <div className="text-center mb-10">
          <h1 className="text-4xl md:text-5xl font-extrabold mb-4 text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-purple-500">
            Smart Face Anonymizer
          </h1>
          <p className="text-lg text-gray-400">
            Instantly detect and blur faces in images &amp; videos — 100% private.
          </p>
        </div>

        <div className="flex flex-col md:flex-row gap-8">
          {/* ── Upload Panel ─────────────────────────────── */}
          <div className="flex-1 flex flex-col gap-4">
            <div
              className={`upload-zone p-10 flex flex-col items-center justify-center cursor-pointer text-center h-64 ${dragActive ? "drag-active" : ""}`}
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                accept="image/*,video/*"
                onChange={(e) => e.target.files?.[0] && handleFileChange(e.target.files[0])}
              />
              <svg className="w-16 h-16 text-blue-500 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
              <p className="text-lg font-semibold text-white mb-1">
                {file ? file.name : "Drag & drop your file here"}
              </p>
              {file && (
                <p className="text-xs text-gray-500 mt-1">
                  {(file.size / (1024 * 1024)).toFixed(1)} MB · {file.type || "unknown type"}
                </p>
              )}
              {!file && (
                <p className="text-sm text-gray-400 mt-1">Click to browse · up to {MAX_FILE_MB} MB</p>
              )}
            </div>

            {/* Progress bar */}
            {isProcessing && (
              <div className="progress-wrap">
                <div className="progress-label">
                  <span>{progressLabel}</span>
                </div>
                <div className="progress-track">
                  <div className="progress-fill" style={{ width: `${progressValue}%` }} />
                </div>
              </div>
            )}

            <button
              onClick={processFile}
              disabled={!file || isProcessing}
              className="primary-btn py-3 px-8 text-lg w-full flex items-center justify-center gap-3"
            >
              {isProcessing ? (
                <>
                  <div className="scan-container"><div className="scan-line" /></div>
                  <span className="pulse-text">{progressLabel}</span>
                </>
              ) : (
                <>
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  Anonymize Faces
                </>
              )}
            </button>

            {error && (
              <div className="p-4 bg-red-500/20 border border-red-500/50 rounded-xl text-red-200 text-sm">
                ⚠️ {error}
              </div>
            )}

            {/* Tips */}
            <div className="tips-box">
              <p className="tips-title">⚡ Performance Tips</p>
              <ul className="tips-list">
                <li>Images are processed instantly</li>
                <li>Videos are processed frame-by-frame in the background</li>
                <li>Smaller files = faster results</li>
              </ul>
            </div>
          </div>

          {/* ── Preview Panel ─────────────────────────────── */}
          <div className="flex-1 flex flex-col gap-4">
            <div className="glass-container flex-1 min-h-[300px] flex items-center justify-center overflow-hidden bg-black/20 p-2 relative">
              {!preview && !resultUrl && (
                <p className="text-gray-500 text-center px-4">Upload a file to see the preview here</p>
              )}

              {preview && !resultUrl && (
                preview.type === "image"
                  ? <img src={preview.url} alt="Preview" className="max-h-full max-w-full object-contain rounded-lg" />
                  : <video src={preview.url} className="max-h-full max-w-full object-contain rounded-lg" controls />
              )}

              {resultUrl && (
                <>
                  <div className="result-badge">✅ Faces Anonymized</div>
                  {resultMime?.startsWith("video") ? (
                    <video src={resultUrl} className="max-h-full max-w-full object-contain rounded-lg" controls autoPlay loop />
                  ) : (
                    <img src={resultUrl} alt="Result" className="max-h-full max-w-full object-contain rounded-lg" />
                  )}
                </>
              )}

              {/* Overlay spinner while processing video */}
              {stage === "processing" && (
                <div className="processing-overlay">
                  <div className="spinner" />
                  <p className="text-white text-sm mt-3 font-semibold">{processPct}% complete</p>
                </div>
              )}
            </div>

            {resultUrl && (
              <a
                href={resultUrl}
                download={downloadName}
                className="primary-btn py-3 px-8 text-center text-lg w-full block text-white no-underline"
              >
                ⬇ Download Result
              </a>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
