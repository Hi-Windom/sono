import React, { useState, useRef, useEffect, useCallback } from 'react';
import { AlgorithmVersion } from '../services/backendApi';

const TAG_CONFIG: Record<string, { label: string; className: string }> = {
  'mobile':      { label: '移动', className: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' },
  'desktop':     { label: '桌面', className: 'bg-blue-500/20 text-blue-400 border border-blue-500/30' },
  'stable':      { label: '稳定', className: 'bg-amber-500/20 text-amber-400 border border-amber-500/30' },
  'recommended': { label: '推荐', className: 'bg-purple-500/20 text-purple-400 border border-purple-500/30' },
  'dual-track':  { label: '双轨', className: 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30' },
  'premium':     { label: '精修', className: 'bg-rose-500/20 text-rose-400 border border-rose-500/30' },
};

const TAG_ORDER = ['recommended', 'premium', 'stable', 'dual-track', 'desktop', 'mobile'];

interface AlgorithmSelectorProps {
  value: string;
  algorithms: AlgorithmVersion[];
  onChange: (version: string) => void;
  disabled?: boolean;
}

export default function AlgorithmSelector({ value, algorithms, onChange, disabled }: AlgorithmSelectorProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const selected = algorithms.find(a => a.name === value);

  const handleClickOutside = useCallback((e: MouseEvent) => {
    if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
      setOpen(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [open, handleClickOutside]);

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && open) setOpen(false);
    };
    if (open) {
      document.addEventListener('keydown', handleKey);
      return () => document.removeEventListener('keydown', handleKey);
    }
  }, [open]);

  useEffect(() => {
    if (open && listRef.current) {
      const selectedEl = listRef.current.querySelector('[data-selected="true"]');
      if (selectedEl) {
        selectedEl.scrollIntoView({ block: 'nearest' });
      }
    }
  }, [open]);

  const handleSelect = (name: string) => {
    onChange(name);
    setOpen(false);
  };

  const sortedTags = (tags: string[] | undefined) => {
    if (!tags) return [];
    return [...tags].sort((a, b) => TAG_ORDER.indexOf(a) - TAG_ORDER.indexOf(b));
  };

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => !disabled && setOpen(!open)}
        disabled={disabled}
        className={`
          flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium
          transition-all duration-200 w-full
          ${open
            ? 'bg-cyan-500/30 border-cyan-400/60 ring-1 ring-cyan-400/30'
            : 'bg-cyan-500/20 border-cyan-400/40 hover:bg-cyan-500/30'
          }
          border text-white
          disabled:opacity-50 disabled:cursor-not-allowed
        `}
      >
        <span className="truncate flex-1 text-left">
          {selected ? selected.label : value}
        </span>
        {selected?.tags && selected.tags.length > 0 && (
          <span className="flex items-center gap-1 shrink-0">
            {sortedTags(selected.tags).map(tag => {
              const cfg = TAG_CONFIG[tag];
              if (!cfg) return null;
              return (
                <span key={tag} className={`text-[10px] px-1.5 py-0 rounded font-medium ${cfg.className}`}>
                  {cfg.label}
                </span>
              );
            })}
          </span>
        )}
        <svg
          className={`w-4 h-4 text-cyan-400 shrink-0 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div
          className="absolute z-50 mt-1 left-0 right-0 min-w-[280px] bg-gray-900/95 backdrop-blur-sm
            border border-cyan-500/20 rounded-xl shadow-xl shadow-black/40 overflow-hidden"
        >
          <div ref={listRef} className="max-h-[320px] overflow-y-auto py-1">
            {[...algorithms].reverse().map(algo => {
              const isSelected = algo.name === value;
              const tags = sortedTags(algo.tags);

              return (
                <button
                  key={algo.name}
                  type="button"
                  data-selected={isSelected}
                  onClick={() => handleSelect(algo.name)}
                  className={`
                    w-full text-left px-3 py-2.5 transition-colors duration-150
                    ${isSelected
                      ? 'bg-cyan-500/15 border-l-2 border-cyan-400'
                      : 'border-l-2 border-transparent hover:bg-white/5'
                    }
                  `}
                >
                  <div className="flex items-center gap-2">
                    <span className={`text-sm font-medium ${isSelected ? 'text-cyan-300' : 'text-white'}`}>
                      {algo.label}
                    </span>
                    {tags.length > 0 && (
                      <span className="flex items-center gap-1">
                        {tags.map(tag => {
                          const cfg = TAG_CONFIG[tag];
                          if (!cfg) return null;
                          return (
                            <span key={tag} className={`text-[10px] px-1.5 py-0 rounded font-medium ${cfg.className}`}>
                              {cfg.label}
                            </span>
                          );
                        })}
                      </span>
                    )}
                  </div>
                  <p className={`text-xs mt-0.5 ${isSelected ? 'text-cyan-400/70' : 'text-gray-400'}`}>
                    {algo.description}
                  </p>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
