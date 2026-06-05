"use client";

import { useState, useRef } from "react";

export default function Home() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [resultUrl, setResultUrl] = useState(null);
  const [error, setError] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  
  const fileInputRef = useRef(null);

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileChange(e.dataTransfer.files[0]);
    }
  };

  const handleChange = (e) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      handleFileChange(e.target.files[0]);
    }
  };

  const handleFileChange = (selectedFile) => {
    setFile(selectedFile);
    setResultUrl(null);
    setError(null);
    
    // Create preview
    const objectUrl = URL.createObjectURL(selectedFile);
    setPreview({
      url: objectUrl,
      type: selectedFile.type.startsWith('video/') ? 'video' : 'image'
    });
  };

  const triggerSelect = () => {
    fileInputRef.current.click();
  };

  const processFile = async () => {
    if (!file) return;
    
    setIsProcessing(true);
    setError(null);
    setResultUrl(null);
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      const response = await fetch(process.env.NEXT_PUBLIC_BACKEND+'/process', {
        method: 'POST',
        body: formData,
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to process file');
      }
      
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      setResultUrl(url);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <main className="min-h-screen p-8 md:p-16 flex flex-col items-center justify-center font-sans">
      <div className="w-full max-w-4xl glass-container p-8 md:p-12">
        <div className="text-center mb-10">
          <h1 className="text-4xl md:text-5xl font-extrabold mb-4 text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-purple-500">
            Smart Face Anonymizer
          </h1>
          <p className="text-lg text-gray-400">
            Instantly detect and blur faces in your images and videos. 100% private and secure.
          </p>
        </div>

        <div className="flex flex-col md:flex-row gap-8">
          {/* Upload Section */}
          <div className="flex-1">
            <div 
              className={`upload-zone p-10 flex flex-col items-center justify-center cursor-pointer text-center h-64 ${dragActive ? 'drag-active' : ''}`}
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
              onClick={triggerSelect}
            >
              <input 
                ref={fileInputRef}
                type="file" 
                className="hidden" 
                accept="image/*,video/*" 
                onChange={handleChange}
              />
              <svg className="w-16 h-16 text-blue-500 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
              <p className="text-lg font-semibold text-white mb-2">
                {file ? file.name : "Drag & drop your file here"}
              </p>
              <p className="text-sm text-gray-400">
                or click to browse files (Images & Videos)
              </p>
            </div>

            <div className="mt-6 flex justify-center">
              <button 
                onClick={processFile}
                disabled={!file || isProcessing}
                className="primary-btn py-3 px-8 text-lg w-full flex items-center justify-center gap-3"
              >
                {isProcessing ? (
                  <>
                    <div className="scan-container">
                      <div className="scan-line"></div>
                    </div>
                    <span className="pulse-text">Scanning & Anonymizing...</span>
                  </>
                ) : (
                  <>
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                    Anonymize Faces
                  </>
                )}
              </button>
            </div>

            {error && (
              <div className="mt-4 p-4 bg-red-500/20 border border-red-500/50 rounded-xl text-red-200 text-sm">
                Error: {error}
              </div>
            )}
          </div>

          {/* Preview Section */}
          <div className="flex-1 flex flex-col gap-4">
            <div className="glass-container flex-1 min-h-[300px] flex items-center justify-center overflow-hidden bg-black/20 p-2 relative">
              {!preview && !resultUrl && (
                <p className="text-gray-500 text-center px-4">Upload a file to see the preview here</p>
              )}
              
              {preview && !resultUrl && (
                preview.type === 'image' ? (
                  <img src={preview.url} alt="Preview" className="max-h-full max-w-full object-contain rounded-lg" />
                ) : (
                  <video src={preview.url} className="max-h-full max-w-full object-contain rounded-lg" controls />
                )
              )}
              
              {resultUrl && (
                <>
                  <div className="absolute top-4 left-4 bg-green-500/80 text-white text-xs px-3 py-1 rounded-full font-semibold z-10 backdrop-blur-sm">
                    Result Ready
                  </div>
                  {file?.type.startsWith('video/') ? (
                    <video src={resultUrl} className="max-h-full max-w-full object-contain rounded-lg" controls autoPlay loop />
                  ) : (
                    <img src={resultUrl} alt="Result" className="max-h-full max-w-full object-contain rounded-lg" />
                  )}
                </>
              )}
            </div>

            {resultUrl && (
              <a 
                href={resultUrl} 
                download={`anonymized_${file.name}`}
                className="primary-btn py-3 px-8 text-center text-lg w-full block text-white no-underline"
              >
                Download Result
              </a>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
