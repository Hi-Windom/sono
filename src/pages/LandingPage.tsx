import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Header } from '../components/Header';

export default function LandingPage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-dark">
      <Header />

      <div className="container mx-auto px-4 py-16 max-w-6xl">
        {/* Hero Section */}
        <div className="text-center mb-16">
          <h1 className="text-4xl md:text-5xl font-bold text-white mb-4">
            AI 音乐处理工具
          </h1>
          <p className="text-gray-400 text-lg max-w-2xl mx-auto">
            专业的 AI 音乐修复与检测工具，帮助您识别和优化 AI 生成的音乐内容
          </p>
        </div>

        {/* Feature Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 max-w-4xl mx-auto">
          {/* AI 音乐修复 */}
          <div
            onClick={() => navigate('/repair')}
            className="group bg-primary/50 border border-white/10 rounded-2xl p-8 cursor-pointer
                       hover:border-cyan-400/50 hover:bg-primary/70 transition-all duration-300"
          >
            <div className="w-16 h-16 bg-gradient-to-br from-cyan-500/20 to-purple-500/20 rounded-xl
                            flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
              <svg className="w-8 h-8 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2z" />
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-white mb-3">AI 音乐修复</h2>
            <p className="text-gray-400 mb-4">
              使用先进的 AI 算法修复和优化 AI 生成的音乐，提升音质，减少失真
            </p>
            <div className="flex items-center text-cyan-400 group-hover:text-cyan-300">
              <span className="text-sm font-medium">开始修复</span>
              <svg className="w-5 h-5 ml-2 group-hover:translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
              </svg>
            </div>
          </div>

          {/* AI 训练素材上传 */}
          <div
            onClick={() => navigate('/training-upload')}
            className="group bg-primary/50 border border-white/10 rounded-2xl p-8 cursor-pointer
                       hover:border-purple-400/50 hover:bg-primary/70 transition-all duration-300"
          >
            <div className="w-16 h-16 bg-gradient-to-br from-purple-500/20 to-pink-500/20 rounded-xl
                            flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
              <svg className="w-8 h-8 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-white mb-3">AI 训练素材上传</h2>
            <p className="text-gray-400 mb-4">
              上传 AI 生成的音乐作为训练素材，帮助我们改进检测算法
            </p>
            <div className="flex items-center text-purple-400 group-hover:text-purple-300">
              <span className="text-sm font-medium">上传素材</span>
              <svg className="w-5 h-5 ml-2 group-hover:translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
              </svg>
            </div>
          </div>
        </div>

        {/* Stats Section */}
        <div className="mt-16 grid grid-cols-2 md:grid-cols-4 gap-6 max-w-4xl mx-auto">
          <div className="text-center p-4 bg-white/5 rounded-xl">
            <div className="text-3xl font-bold text-cyan-400 mb-1">v1.1</div>
            <div className="text-sm text-gray-400">最新算法版本</div>
          </div>
          <div className="text-center p-4 bg-white/5 rounded-xl">
            <div className="text-3xl font-bold text-purple-400 mb-1">2</div>
            <div className="text-sm text-gray-400">修复算法版本</div>
          </div>
          <div className="text-center p-4 bg-white/5 rounded-xl">
            <div className="text-3xl font-bold text-pink-400 mb-1">2</div>
            <div className="text-sm text-gray-400">检测算法版本</div>
          </div>
          <div className="text-center p-4 bg-white/5 rounded-xl">
            <div className="text-3xl font-bold text-green-400 mb-1">实时</div>
            <div className="text-sm text-gray-400">浏览器处理</div>
          </div>
        </div>
      </div>
    </div>
  );
}
