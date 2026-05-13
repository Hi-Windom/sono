import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { Header } from '../components/Header';
import type { FlowData, FlowNode, FlowEdge } from '../types/flow';

const LAYER_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  frontend: { bg: 'rgba(6,182,212,0.15)', border: 'rgba(6,182,212,0.5)', text: '#22d3ee' },
  backend: { bg: 'rgba(52,211,153,0.15)', border: 'rgba(52,211,153,0.5)', text: '#34d399' },
  shared: { bg: 'rgba(148,163,184,0.15)', border: 'rgba(148,163,184,0.5)', text: '#94a3b8' },
};

const NODE_W = 170;
const NODE_H = 48;
const H_GAP = 30;
const V_GAP = 25;
const LAYER_GAP = 80;
const PADDING = 40;

interface LayoutNode extends FlowNode {
  x: number;
  y: number;
}

export default function FlowVisualizationPage() {
  const [flowData, setFlowData] = useState<FlowData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [layerFilter, setLayerFilter] = useState<'all' | 'frontend' | 'backend' | 'shared'>('all');
  const [selectedNode, setSelectedNode] = useState<FlowNode | null>(null);
  const [transform, setTransform] = useState({ x: 0, y: 0, scale: 1 });
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState({ x: 0, y: 0 });
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const res = await fetch('/flow-data.json');
        if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        const data: FlowData = await res.json();
        setFlowData(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : '加载流程数据失败');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const handler = (e: WheelEvent) => {
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        const delta = e.deltaY > 0 ? 0.9 : 1.1;
        setTransform(prev => ({
          ...prev,
          scale: Math.max(0.2, Math.min(5, prev.scale * delta)),
        }));
      }
    };
    svg.addEventListener('wheel', handler, { passive: false });
    return () => svg.removeEventListener('wheel', handler);
  }, []);

  const filteredNodes = useMemo(() => {
    if (!flowData) return [];
    let nodes = flowData.nodes;
    if (layerFilter !== 'all') {
      nodes = nodes.filter(n => n.layer === layerFilter);
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      nodes = nodes.filter(n => n.label.toLowerCase().includes(q) || n.id.toLowerCase().includes(q));
    }
    return nodes;
  }, [flowData, layerFilter, searchQuery]);

  const layoutNodes = useMemo(() => {
    const layers = ['frontend', 'shared', 'backend'];
    const grouped: Record<string, FlowNode[]> = {};
    for (const l of layers) {
      grouped[l] = filteredNodes.filter(n => n.layer === l);
    }

    const result: LayoutNode[] = [];
    let currentY = PADDING;

    for (const layer of layers) {
      const nodes = grouped[layer];
      if (nodes.length === 0) continue;

      let currentX = PADDING;
      let rowMaxY = currentY;

      for (const node of nodes) {
        if (currentX + NODE_W > 1200 - PADDING) {
          currentX = PADDING;
          currentY = rowMaxY + V_GAP;
        }
        result.push({ ...node, x: currentX, y: currentY });
        currentX += NODE_W + H_GAP;
        rowMaxY = Math.max(rowMaxY, currentY + NODE_H);
      }

      currentY = rowMaxY + LAYER_GAP;
    }

    return result;
  }, [filteredNodes]);

  const nodeMap = useMemo(() => {
    const map = new Map<string, LayoutNode>();
    for (const n of layoutNodes) {
      map.set(n.id, n);
    }
    return map;
  }, [layoutNodes]);

  const visibleEdges = useMemo(() => {
    if (!flowData) return [];
    return flowData.edges.filter(e => nodeMap.has(e.source) && nodeMap.has(e.target));
  }, [flowData, nodeMap]);

  const renderEdge = (edge: FlowEdge, idx: number) => {
    const src = nodeMap.get(edge.source);
    const tgt = nodeMap.get(edge.target);
    if (!src || !tgt) return null;

    const x1 = src.x + NODE_W / 2;
    const y1 = src.y + NODE_H;
    const x2 = tgt.x + NODE_W / 2;
    const y2 = tgt.y;

    const cy = (y1 + y2) / 2;
    const path = `M ${x1} ${y1} Q ${x1} ${cy} ${(x1 + x2) / 2} ${cy} Q ${x2} ${cy} ${x2} ${y2}`;

    return (
      <g key={`edge-${idx}`}>
        <path d={path} fill="none" stroke="rgba(148,163,184,0.25)" strokeWidth="1.5" />
        <polygon
          points={`${x2 - 4},${y2} ${x2 + 4},${y2} ${x2},${y2 + 6}`}
          fill="rgba(148,163,184,0.35)"
        />
      </g>
    );
  };

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button === 0) {
      setIsPanning(true);
      setPanStart({ x: e.clientX - transform.x, y: e.clientY - transform.y });
    }
  }, [transform]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (isPanning) {
      setTransform(prev => ({
        ...prev,
        x: e.clientX - panStart.x,
        y: e.clientY - panStart.y,
      }));
    }
  }, [isPanning, panStart]);

  const handleMouseUp = useCallback(() => {
    setIsPanning(false);
  }, []);

  const getNodeLayerColor = (node: FlowNode) => {
    return LAYER_COLORS[node.layer] || LAYER_COLORS.shared;
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-dark">
        <Header />
        <div className="flex items-center justify-center h-[80vh]">
          <div className="text-center">
            <div className="w-8 h-8 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            <p className="text-gray-400">加载流程数据...</p>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-dark">
        <Header />
        <div className="container mx-auto px-4 py-16 max-w-4xl">
          <div className="bg-red-500/10 border border-red-500/30 rounded-2xl p-8 text-center">
            <div className="text-4xl mb-4">⚠️</div>
            <h2 className="text-white text-lg font-bold mb-2">加载失败</h2>
            <p className="text-gray-400 mb-4">{error}</p>
            <p className="text-gray-500 text-sm">
              请确保 flow-data.json 文件存在于 public 目录下
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-dark flex flex-col">
      <Header />

      <div className="border-b border-white/5 bg-primary/30">
        <div className="container mx-auto px-4 py-4 max-w-7xl">
          <div className="flex flex-col md:flex-row md:items-center gap-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-cyan-500/20 to-emerald-500/20 rounded-xl flex items-center justify-center border border-cyan-400/20">
                <svg className="w-5 h-5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z" />
                </svg>
              </div>
              <h1 className="text-xl font-bold text-white">系统流程可视化</h1>
            </div>

            <div className="flex-1 flex flex-col sm:flex-row gap-3">
              <div className="relative flex-1 max-w-md">
                <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                <input
                  type="text"
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  placeholder="搜索节点..."
                  className="w-full bg-white/5 border border-white/10 rounded-lg pl-10 pr-4 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-cyan-400/50 transition"
                />
              </div>

              <div className="flex gap-2">
                {(['all', 'frontend', 'backend', 'shared'] as const).map(layer => (
                  <button
                    key={layer}
                    onClick={() => setLayerFilter(layer)}
                    className={`px-3 py-2 rounded-lg text-sm font-medium transition cursor-pointer ${
                      layerFilter === layer
                        ? layer === 'all'
                          ? 'bg-white/10 text-white border border-white/20'
                          : layer === 'frontend'
                          ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-400/30'
                          : layer === 'backend'
                          ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-400/30'
                          : 'bg-gray-500/20 text-gray-400 border border-gray-400/30'
                        : 'bg-white/5 text-gray-500 border border-white/10 hover:text-white hover:bg-white/10'
                    }`}
                  >
                    {layer === 'all' ? '全部' : layer === 'frontend' ? '前端' : layer === 'backend' ? '后端' : '共享'}
                  </button>
                ))}
              </div>
            </div>

            <div className="text-xs text-gray-500 whitespace-nowrap">
              {filteredNodes.length} 节点 · {visibleEdges.length} 边
            </div>
          </div>
        </div>
      </div>

      <div className="flex-1 flex overflow-hidden">
        <div ref={containerRef} className="flex-1 overflow-hidden relative bg-[#0a0a0f]">
          <svg
            ref={svgRef}
            className="w-full h-full"
            style={{ cursor: isPanning ? 'grabbing' : 'grab' }}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
          >
            <g transform={`translate(${transform.x},${transform.y}) scale(${transform.scale})`}>
              {visibleEdges.map((edge, idx) => renderEdge(edge, idx))}

              {layoutNodes.map(node => {
                const colors = getNodeLayerColor(node);
                const isSelected = selectedNode?.id === node.id;
                return (
                  <g
                    key={node.id}
                    onClick={() => setSelectedNode(node)}
                    className="cursor-pointer"
                  >
                    <rect
                      x={node.x}
                      y={node.y}
                      width={NODE_W}
                      height={NODE_H}
                      rx={8}
                      ry={8}
                      fill={isSelected ? colors.bg : 'rgba(255,255,255,0.03)'}
                      stroke={isSelected ? colors.border : 'rgba(255,255,255,0.08)'}
                      strokeWidth={isSelected ? 2 : 1}
                    />
                    <circle cx={node.x + 12} cy={node.y + NODE_H / 2} r={4} fill={colors.text} />
                    <text
                      x={node.x + 22}
                      y={node.y + NODE_H / 2 + 1}
                      fill={colors.text}
                      fontSize={11}
                      dominantBaseline="middle"
                    >
                      {node.label.length > 18 ? node.label.slice(0, 17) + '…' : node.label}
                    </text>
                    <text
                      x={node.x + 22}
                      y={node.y + NODE_H - 8}
                      fill="rgba(148,163,184,0.5)"
                      fontSize={8}
                    >
                      {node.type}
                    </text>
                  </g>
                );
              })}
            </g>
          </svg>

          <div className="absolute bottom-4 right-4 flex gap-2">
            <button
              onClick={() => setTransform(prev => ({ ...prev, scale: Math.max(0.2, prev.scale * 0.8) }))}
              className="w-8 h-8 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg flex items-center justify-center text-gray-400 hover:text-white transition cursor-pointer text-sm"
            >
              −
            </button>
            <button
              onClick={() => setTransform(prev => ({ ...prev, x: 0, y: 0, scale: 1 }))}
              className="px-3 h-8 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg flex items-center justify-center text-gray-400 hover:text-white transition cursor-pointer text-xs"
            >
              {Math.round(transform.scale * 100)}%
            </button>
            <button
              onClick={() => setTransform(prev => ({ ...prev, scale: Math.min(5, prev.scale * 1.25) }))}
              className="w-8 h-8 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg flex items-center justify-center text-gray-400 hover:text-white transition cursor-pointer text-sm"
            >
              +
            </button>
          </div>
        </div>

        {selectedNode && (
          <div className="w-80 border-l border-white/5 bg-primary/30 overflow-y-auto shrink-0">
            <div className="p-4">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-white font-bold text-sm">节点详情</h3>
                <button
                  onClick={() => setSelectedNode(null)}
                  className="w-6 h-6 flex items-center justify-center rounded text-gray-500 hover:text-white hover:bg-white/10 transition cursor-pointer text-sm"
                >
                  ✕
                </button>
              </div>

              <div className="space-y-3">
                <div>
                  <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">名称</div>
                  <div className="text-white text-sm break-all">{selectedNode.label}</div>
                </div>

                <div>
                  <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">类型</div>
                  <span className="inline-block px-2 py-0.5 rounded text-xs bg-white/10 text-gray-300">
                    {selectedNode.type}
                  </span>
                </div>

                <div>
                  <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">层级</div>
                  <span className={`inline-block px-2 py-0.5 rounded text-xs ${
                    selectedNode.layer === 'frontend'
                      ? 'bg-cyan-500/20 text-cyan-400'
                      : selectedNode.layer === 'backend'
                      ? 'bg-emerald-500/20 text-emerald-400'
                      : 'bg-gray-500/20 text-gray-400'
                  }`}>
                    {selectedNode.layer === 'frontend' ? '前端' : selectedNode.layer === 'backend' ? '后端' : '共享'}
                  </span>
                </div>

                {selectedNode.filePath && (
                  <div>
                    <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">文件路径</div>
                    <div className="text-gray-400 text-xs break-all font-mono">{selectedNode.filePath}</div>
                  </div>
                )}

                {selectedNode.description && (
                  <div>
                    <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">描述</div>
                    <div className="text-gray-400 text-xs leading-relaxed">{selectedNode.description}</div>
                  </div>
                )}

                {selectedNode.children && selectedNode.children.length > 0 && (
                  <div>
                    <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">子节点 ({selectedNode.children.length})</div>
                    <div className="space-y-1 max-h-32 overflow-y-auto">
                      {selectedNode.children.map(childId => {
                        const child = flowData?.nodes.find(n => n.id === childId);
                        return (
                          <div
                            key={childId}
                            onClick={() => child && setSelectedNode(child)}
                            className="text-xs text-gray-400 hover:text-cyan-400 cursor-pointer transition truncate"
                          >
                            {child?.label || childId}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                <div>
                  <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">连接关系</div>
                  <div className="space-y-1 max-h-40 overflow-y-auto">
                    {flowData?.edges
                      .filter(e => e.source === selectedNode.id || e.target === selectedNode.id)
                      .slice(0, 30)
                      .map((edge, idx) => {
                        const otherId = edge.source === selectedNode.id ? edge.target : edge.source;
                        const other = flowData?.nodes.find(n => n.id === otherId);
                        return (
                          <div
                            key={idx}
                            onClick={() => {
                              const target = flowData?.nodes.find(n => n.id === otherId);
                              if (target) setSelectedNode(target);
                            }}
                            className="text-xs text-gray-500 flex items-center gap-1 cursor-pointer hover:text-gray-300 transition"
                          >
                            <span className={edge.source === selectedNode.id ? 'text-cyan-400' : 'text-emerald-400'}>
                              {edge.source === selectedNode.id ? '→' : '←'}
                            </span>
                            <span className="text-gray-400 truncate">{other?.label || otherId}</span>
                            {edge.label && <span className="text-gray-600 shrink-0">({edge.label})</span>}
                          </div>
                        );
                      })}
                    {flowData?.edges.filter(e => e.source === selectedNode.id || e.target === selectedNode.id).length === 0 && (
                      <span className="text-gray-600 text-xs">无连接关系</span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}