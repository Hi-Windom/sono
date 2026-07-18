import React, { useCallback, useState } from 'react';

interface AudioUploaderProps {
  onFileSelect: (file: File) => void;
  onInvalidFile?: () => void;
  isLoading?: boolean;
  currentFile?: File | null;
}

export function AudioUploader({ onFileSelect, onInvalidFile, isLoading = false }: AudioUploaderProps) {
  const [showInvalidHint, setShowInvalidHint] = useState(false);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    if (isLoading) return;
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith('audio/')) {
      setShowInvalidHint(false);
      onFileSelect(file);
    } else if (file) {
      setShowInvalidHint(true);
      setTimeout(() => setShowInvalidHint(false), 2000);
      onInvalidFile?.();
    }
  }, [onFileSelect, onInvalidFile, isLoading]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
  }, []);

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (isLoading) return;
    const file = e.target.files?.[0];
    if (file) {
      onFileSelect(file);
    }
  }, [onFileSelect, isLoading]);

  return (
    <div className="w-full">
      <div
        className={`bg-gradient-to-r from-primary/60 to-dark/60 rounded-2xl p-12 border-2 border-dashed transition cursor-pointer ${
          showInvalidHint ? 'border-red-500/60 bg-red-500/10' : 'border-gray-600 hover:border-secondary/50'
        } ${isLoading ? 'opacity-50 pointer-events-none' : ''}`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
      >
        <label className="flex flex-col items-center gap-4 cursor-pointer">
          <div className={`w-16 h-16 rounded-2xl flex items-center justify-center transition ${
            showInvalidHint ? 'bg-red-500/20' : 'bg-secondary/20'
          }`}>
            <svg className={`w-8 h-8 transition ${showInvalidHint ? 'text-red-400' : 'text-secondary'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
          </div>
          <div className="text-center">
            <p className={`font-medium text-lg transition ${showInvalidHint ? 'text-red-400' : 'text-white'}`}>
              {showInvalidHint ? '请拖放音频文件' : '拖放音频文件到此处'}
            </p>
            <p className="text-gray-400 mt-1">或点击选择文件</p>
          </div>
          <input
            type="file"
            accept="audio/*"
            className="hidden"
            onChange={handleFileInput}
            disabled={isLoading}
          />
        </label>
      </div>
    </div>
  );
}
