import React, { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Header } from '../components/Header';
import { uploadTrainingAudio } from '../services/backendApi';

interface UploadingFile {
  name: string;
  progress: number;
  status: 'checking' | 'uploading' | 'success' | 'error' | 'cached';
  error?: string;
}

// 计算文件 SHA256 哈希
async function calculateFileHash(file: File): Promise<string> {
  const buffer = await file.arrayBuffer();
  const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

export default function TrainingUploadPage() {
  const navigate = useNavigate();
  const [isUploading, setIsUploading] = useState(false);
  const [uploadingFiles, setUploadingFiles] = useState<UploadingFile[]>([]);
  const [uploadedFiles, setUploadedFiles] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const handleFileSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setIsUploading(true);
    setError(null);

    // 初始化上传文件列表
    const initialFiles: UploadingFile[] = Array.from(files).map(file => ({
      name: file.name,
      progress: 0,
      status: 'checking' as const,
    }));
    setUploadingFiles(initialFiles);

    const newUploadedFiles: string[] = [];

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      
      try {
        // 计算哈希
        setUploadingFiles(prev => {
          const updated = [...prev];
          updated[i] = { ...updated[i], status: 'checking' };
          return updated;
        });
        
        const fileHash = await calculateFileHash(file);
        
        // 上传（带哈希检测）
        setUploadingFiles(prev => {
          const updated = [...prev];
          updated[i] = { ...updated[i], status: 'uploading' };
          return updated;
        });
        
        const result = await uploadTrainingAudio(file, (loaded, total) => {
          const progress = total > 0 ? (loaded / total) * 100 : 0;
          setUploadingFiles(prev => {
            const updated = [...prev];
            updated[i] = { ...updated[i], progress };
            return updated;
          });
        }, fileHash);

        newUploadedFiles.push(file.name);
        setUploadingFiles(prev => {
          const updated = [...prev];
          updated[i] = { 
            ...updated[i], 
            status: result.cached ? 'cached' : 'success', 
            progress: 100 
          };
          return updated;
        });
      } catch (err) {
        console.error('上传失败:', err);
        const errorMsg = err instanceof Error ? err.message : '未知错误';
        setUploadingFiles(prev => {
          const updated = [...prev];
          updated[i] = { ...updated[i], status: 'error', error: errorMsg };
          return updated;
        });
        setError(`文件 "${file.name}" 上传失败: ${errorMsg}`);
      }
    }

    setUploadedFiles(prev => [...prev, ...newUploadedFiles]);
    setIsUploading(false);
    e.target.value = '';
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      const input = document.createElement('input');
      input.type = 'file';
      input.multiple = true;
      input.accept = 'audio/*';
      input.onchange = (ev) => handleFileSelect(ev as unknown as React.ChangeEvent<HTMLInputElement>);
      // @ts-ignore
      input.files = files;
      input.dispatchEvent(new Event('change'));
    }
  }, [handleFileSelect]);

  return (
    <div className="min-h-screen bg-dark">
      <Header />

      {/* 返回首页按钮 */}
      <div className="container mx-auto px-4 max-w-7xl mt-4">
        <button
          onClick={() => navigate('/')}
          className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
          <span>返回首页</span>
        </button>
      </div>

      <div className="container mx-auto px-4 py-8 max-w-4xl">
        <div className="text-center mb-12">
          <h1 className="text-3xl md:text-4xl font-bold text-white mb-4">
            AI 训练素材上传
          </h1>
          <p className="text-gray-400 text-lg">
            上传 AI 生成的音乐文件，帮助我们改进检测算法
          </p>
        </div>

        {/* Upload Area */}
        <div
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
          className="relative border-2 border-dashed border-purple-400/30 rounded-2xl p-12
                     bg-primary/30 hover:bg-primary/50 hover:border-purple-400/50
                     transition-all duration-300 cursor-pointer"
        >
          <input
            type="file"
            accept="audio/*"
            multiple
            onChange={handleFileSelect}
            disabled={isUploading}
            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
          />

          <div className="text-center">
            <div className="w-20 h-20 bg-gradient-to-br from-purple-500/20 to-pink-500/20 rounded-2xl
                            flex items-center justify-center mx-auto mb-6">
              <svg className="w-10 h-10 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
            </div>

            {isUploading ? (
              <div className="w-full max-w-md mx-auto">
                <div className="text-purple-400 text-lg font-medium mb-4">
                  正在上传 {uploadingFiles.filter(f => f.status === 'uploading').length} 个文件...
                </div>
                <div className="space-y-3 max-h-48 overflow-y-auto">
                  {uploadingFiles.map((file, index) => (
                    <div key={index} className="flex items-center gap-3">
                      <div className="flex-1">
                        <div className="flex justify-between text-sm mb-1">
                          <span className="text-gray-300 truncate max-w-[200px]">{file.name}</span>
                          <span className={
                            file.status === 'success' ? 'text-green-400' :
                            file.status === 'error' ? 'text-red-400' :
                            'text-purple-400'
                          }>
                            {file.status === 'success' ? '完成' :
                             file.status === 'cached' ? '已存在' :
                             file.status === 'error' ? '失败' :
                             file.status === 'checking' ? '检测中...' :
                             `${Math.round(file.progress)}%`}
                          </span>
                        </div>
                        <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
                          <div
                            className={`h-full transition-all duration-300 ${
                              file.status === 'success' ? 'bg-green-500' :
                              file.status === 'cached' ? 'bg-blue-500' :
                              file.status === 'error' ? 'bg-red-500' :
                              file.status === 'checking' ? 'bg-yellow-500' :
                              'bg-gradient-to-r from-purple-500 to-pink-500'
                            }`}
                            style={{ width: `${file.progress}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <>
                <p className="text-white text-lg font-medium mb-2">
                  点击或拖拽音频文件到此处上传
                </p>
                <p className="text-gray-500 text-sm">
                  支持多选上传 WAV、MP3、FLAC 等常见音频格式
                </p>
              </>
            )}
          </div>
        </div>

        {/* Error Message */}
        {error && (
          <div className="mt-6 p-4 bg-red-500/10 border border-red-500/30 rounded-xl">
            <div className="flex items-center gap-2 text-red-400">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>{error}</span>
            </div>
          </div>
        )}

        {/* Uploaded Files List */}
        {uploadedFiles.length > 0 && (
          <div className="mt-8">
            <h3 className="text-white font-semibold text-lg mb-4">已上传文件</h3>
            <div className="space-y-2">
              {uploadedFiles.map((filename, index) => (
                <div
                  key={index}
                  className="flex items-center gap-3 p-3 bg-green-500/10 border border-green-500/30 rounded-lg"
                >
                  <svg className="w-5 h-5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  <span className="text-gray-300">{filename}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Info Section */}
        <div className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="p-6 bg-white/5 rounded-xl">
            <div className="w-10 h-10 bg-purple-500/20 rounded-lg flex items-center justify-center mb-4">
              <svg className="w-5 h-5 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <h4 className="text-white font-medium mb-2">独立存储</h4>
            <p className="text-gray-400 text-sm">训练素材将保存在独立的目录中，与修复功能分开管理</p>
          </div>

          <div className="p-6 bg-white/5 rounded-xl">
            <div className="w-10 h-10 bg-purple-500/20 rounded-lg flex items-center justify-center mb-4">
              <svg className="w-5 h-5 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.384-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
              </svg>
            </div>
            <h4 className="text-white font-medium mb-2">算法改进</h4>
            <p className="text-gray-400 text-sm">上传的素材将用于训练和优化 AI 音乐检测算法</p>
          </div>

          <div className="p-6 bg-white/5 rounded-xl">
            <div className="w-10 h-10 bg-purple-500/20 rounded-lg flex items-center justify-center mb-4">
              <svg className="w-5 h-5 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
            </div>
            <h4 className="text-white font-medium mb-2">隐私保护</h4>
            <p className="text-gray-400 text-sm">上传的素材仅用于算法训练，不会用于其他用途</p>
          </div>
        </div>
      </div>
    </div>
  );
}
