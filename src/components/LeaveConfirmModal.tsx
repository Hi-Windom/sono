import React from 'react';

interface TaskInfo {
  name: string;
  step?: string;
  progress?: number;
}

interface LeaveConfirmModalProps {
  isOpen: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  title: string;
  tasks: TaskInfo[];
}

export function LeaveConfirmModal({
  isOpen,
  onConfirm,
  onCancel,
  title,
  tasks,
}: LeaveConfirmModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onCancel}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        className="relative bg-[#0D1117] border border-white/10 rounded-2xl p-6 max-w-md w-full mx-4 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-red-500/20 to-orange-500/20 flex items-center justify-center">
              <svg className="w-5 h-5 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
              </svg>
            </div>
            <div>
              <h2 className="text-white font-bold text-lg">{title}</h2>
              <p className="text-gray-500 text-xs">离开将中断当前正在进行的任务</p>
            </div>
          </div>
          <button
            onClick={onCancel}
            className="p-1.5 hover:bg-white/10 rounded-lg text-gray-400 hover:text-white transition"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {tasks.length > 0 && (
          <div className="mb-5 space-y-2">
            <div className="text-xs text-gray-400 font-medium mb-2">进行中的任务</div>
            {tasks.map((task, idx) => (
              <div key={idx} className="bg-white/5 border border-white/10 rounded-lg p-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-white text-sm font-medium">{task.name}</span>
                  {task.progress !== undefined && (
                    <span className="text-cyan-400 text-xs">{Math.round(task.progress * 100)}%</span>
                  )}
                </div>
                {task.step && (
                  <div className="flex items-center gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
                    <span className="text-gray-400 text-xs">{task.step}</span>
                  </div>
                )}
                {task.progress !== undefined && (
                  <div className="mt-2 w-full h-1 bg-gray-700 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-cyan-500 to-cyan-400 transition-all duration-200 rounded-full"
                      style={{ width: `${Math.round(task.progress * 100)}%` }}
                    />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        <div className="flex gap-3">
          <button
            onClick={onCancel}
            className="flex-1 py-2.5 bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/30 rounded-lg text-cyan-400 text-sm font-medium transition"
          >
            取消
          </button>
          <button
            onClick={onConfirm}
            className="flex-1 py-2.5 bg-red-500/20 hover:bg-red-500/30 border border-red-500/30 rounded-lg text-red-400 text-sm font-medium transition"
          >
            确认离开
          </button>
        </div>
      </div>
    </div>
  );
}