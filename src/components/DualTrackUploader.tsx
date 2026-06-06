import React, { useCallback, useState, useEffect } from 'react';

interface DualTrackUploaderProps {
  onFilesSelect: (vocalFile: File, accompanimentFile: File) => void;
  isLoading?: boolean;
}

export function DualTrackUploader({ onFilesSelect, isLoading = false }: DualTrackUploaderProps) {
  const [vocalFile, setVocalFile] = useState<File | null>(null);
  const [accompanimentFile, setAccompanimentFile] = useState<File | null>(null);

  useEffect(() => {
    if (vocalFile && accompanimentFile && !isLoading) {
      onFilesSelect(vocalFile, accompanimentFile);
    }
  }, [vocalFile, accompanimentFile, isLoading, onFilesSelect]);

  const handleVocalDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    if (isLoading) return;
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith('audio/')) {
      setVocalFile(file);
    }
  }, [isLoading]);

  const handleAccompanimentDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    if (isLoading) return;
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith('audio/')) {
      setAccompanimentFile(file);
    }
  }, [isLoading]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
  }, []);

  const handleVocalInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (isLoading) return;
    const file = e.target.files?.[0];
    if (file) {
      setVocalFile(file);
    }
  }, [isLoading]);

  const handleAccompanimentInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (isLoading) return;
    const file = e.target.files?.[0];
    if (file) {
      setAccompanimentFile(file);
    }
  }, [isLoading]);

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  };

  return (
    <div className="w-full space-y-6">
      <div className="text-center mb-4">
        <h3 className="text-xl font-semibold text-white mb-2">双轨上传</h3>
        <p className="text-gray-400 text-sm">分别上传人声轨和伴奏轨，分别优化后混音</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-gradient-to-br from-primary/40 to-dark/60 rounded-2xl p-6 border-2 border-dashed border-gray-600 hover:border-secondary/50 transition">
          <h4 className="text-secondary font-medium mb-4 flex items-center gap-2">
            <span className="w-8 h-8 bg-secondary/20 rounded-full flex items-center justify-center text-sm">1</span>
            人声轨 (Vocal)
          </h4>
          <div
            className={`border-2 border-dashed border-gray-500 rounded-xl p-8 text-center hover:border-secondary/50 transition cursor-pointer ${isLoading ? 'opacity-50 pointer-events-none' : ''}`}
            onDrop={handleVocalDrop}
            onDragOver={handleDragOver}
          >
            <label className="cursor-pointer">
              {vocalFile ? (
                <div className="space-y-2">
                  <div className="text-green-400">
                    <svg className="w-8 h-8 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                  <p className="text-white font-medium">{vocalFile.name}</p>
                  <p className="text-gray-400 text-sm">{formatSize(vocalFile.size)}</p>
                </div>
              ) : (
                <div className="space-y-2">
                  <svg className="w-10 h-10 mx-auto text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                  </svg>
                  <p className="text-white">拖放人声文件</p>
                  <p className="text-gray-400 text-sm">或点击选择</p>
                </div>
              )}
              <input
                type="file"
                accept="audio/*"
                className="hidden"
                onChange={handleVocalInput}
                disabled={isLoading}
              />
            </label>
          </div>
        </div>

        <div className="bg-gradient-to-br from-purple-500/20 to-dark/60 rounded-2xl p-6 border-2 border-dashed border-gray-600 hover:border-purple-500/50 transition">
          <h4 className="text-purple-400 font-medium mb-4 flex items-center gap-2">
            <span className="w-8 h-8 bg-purple-500/20 rounded-full flex items-center justify-center text-sm">2</span>
            伴奏轨 (Accompaniment)
          </h4>
          <div
            className={`border-2 border-dashed border-gray-500 rounded-xl p-8 text-center hover:border-purple-500/50 transition cursor-pointer ${isLoading ? 'opacity-50 pointer-events-none' : ''}`}
            onDrop={handleAccompanimentDrop}
            onDragOver={handleDragOver}
          >
            <label className="cursor-pointer">
              {accompanimentFile ? (
                <div className="space-y-2">
                  <div className="text-purple-400">
                    <svg className="w-8 h-8 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                  <p className="text-white font-medium">{accompanimentFile.name}</p>
                  <p className="text-gray-400 text-sm">{formatSize(accompanimentFile.size)}</p>
                </div>
              ) : (
                <div className="space-y-2">
                  <svg className="w-10 h-10 mx-auto text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
                  </svg>
                  <p className="text-white">拖放伴奏文件</p>
                  <p className="text-gray-400 text-sm">或点击选择</p>
                </div>
              )}
              <input
                type="file"
                accept="audio/*"
                className="hidden"
                onChange={handleAccompanimentInput}
                disabled={isLoading}
              />
            </label>
          </div>
        </div>
      </div>

      {vocalFile && !accompanimentFile && (
        <div className="text-center text-sm text-gray-400">
          <p>已选择人声轨，请继续选择伴奏轨</p>
        </div>
      )}
      {!vocalFile && accompanimentFile && (
        <div className="text-center text-sm text-gray-400">
          <p>已选择伴奏轨，请继续选择人声轨</p>
        </div>
      )}
      {vocalFile && accompanimentFile && (
        <div className="text-center text-sm text-gray-400">
          <p>文件已就绪，正在上传...</p>
        </div>
      )}
    </div>
  );
}
