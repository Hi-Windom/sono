import dagre from 'dagre';
import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { Header } from '../components/Header';
import type { FlowData, FlowNode, FlowEdge } from '../types/flow';

const NODE_W = 170;
const NODE_H = 48;
const LAYER_ORDER = ['frontend', 'shared', 'backend'];

const LAYER_COLORS: Record<string, { bg: string; border: string; text: string; fill: string }> = {
  frontend: { bg: 'rgba(6,182,212,0.15)', border: 'rgba(6,182,212,0.5)', text: '#22d3ee', fill: 'rgba(6,182,212,0.06)' },
  backend: { bg: 'rgba(52,211,153,0.15)', border: 'rgba(52,211,153,0.5)', text: '#34d399', fill: 'rgba(52,211,153,0.06)' },
  shared: { bg: 'rgba(148,163,184,0.15)', border: 'rgba(148,163,184,0.5)', text: '#94a3b8', fill: 'rgba(148,163,184,0.06)' },
};

const LAYER_LABELS: Record<string, string> = {
  frontend: '前端层',
  backend: '后端层',
  shared: '共享层',
};

function orthogonalPath(points: Array<{ x: number; y: number }>, r = 4): string {
  if (points.length < 2) return '';
  let d = `M ${points[0].x} ${points[0].y}`;
  for (let i = 1; i < points.length - 1; i++) {
    const p = points[i - 1], c = points[i], n = points[i + 1];
    const dx1 = c.x - p.x, dy1 = c.y - p.y;
    const dx2 = n.x - c.x, dy2 = n.y - c.y;
    const len1 = Math.sqrt(dx1 * dx1 + dy1 * dy1);
    const len2 = Math.sqrt(dx2 * dx2 + dy2 * dy2);
    if (len1 < 0.01 || len2 < 0.01) { d += ` L ${c.x} ${c.y}`; continue; }
    const cr = Math.min(r, len1 / 2, len2 / 2);
    const sx = c.x - (dx1 / len1) * cr, sy = c.y - (dy1 / len1) * cr;
    const ex = c.x + (dx2 / len2) * cr, ey = c.y + (dy2 / len2) * cr;
    d += ` L ${sx} ${sy} Q ${c.x} ${c.y} ${ex} ${ey}`;
  }
  const last = points[points.length - 1];
  d += ` L ${last.x} ${last.y}`;
  return d;
}

function getLayerColor(layer: string) {
  return LAYER_COLORS[layer] || LAYER_COLORS.shared;
}

export default function FlowVisualizationPage() {
  const [flowData, setFlowData] = useState<FlowData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [layerFilter, setLayerFilter] = useState<'all' | 'frontend' | 'backend' | 'shared'>('all');
  const [selectedNode, setSelectedNode] = useState<FlowNode | null>(null);
  const [expandedParents, setExpandedParents] = useState<Set<string>>(new Set());
  const [transform, setTransform] = useState({ x: 40, y: 40, scale: 1 });
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState({ x: 0, y: 0 });

  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const layoutVersionRef = useRef(0);
  const [layoutVersion, setLayoutVersion] = useState(0);
  const isInitialLayoutRef = useRef(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const res = await fetch('/flow-data.json');
        if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        const data: FlowData = await res.json();
        setFlowData(data);
        const parents = new Set<string>();
        for (const node of data.nodes) {
          if (node.children && node.children.length > 0) {
            parents.add(node.id);
          }
        }
        setExpandedParents(parents);
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

  const visibleNodeIds = useMemo(() => {
    const visible = new Set<string>();
    for (const node of filteredNodes) {
      visible.add(node.id);
      if (node.children && node.children.length > 0 && !expandedParents.has(node.id)) {
        for (const childId of node.children) {
          visible.delete(childId);
        }
      }
    }
    return visible;
  }, [filteredNodes, expandedParents]);

  const visibleNodes = useMemo(() => {
    return filteredNodes.filter(n => visibleNodeIds.has(n.id));
  }, [filteredNodes, visibleNodeIds]);

  const layoutData = useMemo(() => {
    if (!flowData || visibleNodes.length === 0) {
      return { nodePositions: new Map<string, { x: number; y: number }>(), edgePoints: [], layerBounds: new Map<string, { minX: number; minY: number; maxX: number; maxY: number }>() };
    }

    const g = new dagre.graphlib.Graph({ directed: true, compound: true, multigraph: false });
    g.setGraph({ rankdir: 'TB', nodesep: 40, ranksep: 100, marginx: 40, marginy: 40 });
    g.setDefaultEdgeLabel(() => ({}));

    for (const layer of LAYER_ORDER) {
      g.setNode(`layer-${layer}`, { width: 0, height: 0 });
    }

    for (const node of visibleNodes) {
      g.setNode(node.id, { width: NODE_W, height: NODE_H });
      g.setParent(node.id, `layer-${node.layer}`);
    }

    for (const edge of flowData.edges) {
      if (visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target)) {
        g.setEdge(edge.source, edge.target, {});
      }
    }

    dagre.layout(g);

    const nodePositions = new Map<string, { x: number; y: number }>();
    for (const node of visibleNodes) {
      const pos = g.node(node.id);
      if (pos) {
        nodePositions.set(node.id, {
          x: pos.x - NODE_W / 2,
          y: pos.y - NODE_H / 2,
        });
      }
    }

    const layerAvgY = new Map<string, number>();
    const layerCount = new Map<string, number>();
    for (const node of visibleNodes) {
      const pos = nodePositions.get(node.id);
      if (!pos) continue;
      layerAvgY.set(node.layer, (layerAvgY.get(node.layer) || 0) + pos.y);
      layerCount.set(node.layer, (layerCount.get(node.layer) || 0) + 1);
    }
    for (const layer of LAYER_ORDER) {
      const count = layerCount.get(layer) || 0;
      if (count > 0) {
        layerAvgY.set(layer, (layerAvgY.get(layer) || 0) / count);
      }
    }
    for (const node of visibleNodes) {
      const pos = nodePositions.get(node.id);
      if (!pos) continue;
      const avgY = layerAvgY.get(node.layer);
      if (avgY !== undefined) {
        pos.y = avgY;
      }
    }

    const edgePoints: Array<{ edge: FlowEdge; points: Array<{ x: number; y: number }> }> = [];
    for (const edge of flowData.edges) {
      if (visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target)) {
        const ep = g.edge(edge.source, edge.target);
        if (ep && ep.points && ep.points.length >= 2) {
          edgePoints.push({ edge, points: ep.points });
        }
      }
    }

    const layerBounds = new Map<string, { minX: number; minY: number; maxX: number; maxY: number }>();
    for (const layer of LAYER_ORDER) {
      const layerNodes = visibleNodes.filter(n => n.layer === layer);
      if (layerNodes.length === 0) continue;
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      for (const node of layerNodes) {
        const pos = nodePositions.get(node.id);
        if (!pos) continue;
        minX = Math.min(minX, pos.x);
        minY = Math.min(minY, pos.y);
        maxX = Math.max(maxX, pos.x + NODE_W);
        maxY = Math.max(maxY, pos.y + NODE_H);
      }
      const pad = 24;
      layerBounds.set(layer, {
        minX: minX - pad,
        minY: minY - pad,
        maxX: maxX + pad,
        maxY: maxY + pad,
      });
    }

    layoutVersionRef.current += 1;

    return { nodePositions, edgePoints, layerBounds };
  }, [flowData, visibleNodes, visibleNodeIds]);

  useEffect(() => {
    if (layoutVersionRef.current > 0 && isInitialLayoutRef.current) {
      isInitialLayoutRef.current = false;
    }
    setLayoutVersion(layoutVersionRef.current);
  }, [layoutData]);

  const visibleEdges = useMemo(() => {
    if (!flowData) return [];
    return flowData.edges.filter(e => visibleNodeIds.has(e.source) && visibleNodeIds.has(e.target));
  }, [flowData, visibleNodeIds]);

  const handleNodeClick = useCallback((node: FlowNode) => {
    setSelectedNode(node);
    if (node.children && node.children.length > 0) {
      setExpandedParents(prev => {
        const next = new Set(prev);
        if (next.has(node.id)) {
          next.delete(node.id);
        } else {
          next.add(node.id);
        }
        return next;
      });
    }
  }, []);

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

  const focusOnNode = useCallback((node: FlowNode) => {
    const pos = layoutData.nodePositions.get(node.id);
    if (!pos || !containerRef.current) return;
    const containerRect = containerRef.current.getBoundingClientRect();
    const cx = containerRect.width / 2;
    const cy = containerRect.height / 2;
    const targetX = cx - (pos.x + NODE_W / 2) * transform.scale;
    const targetY = cy - (pos.y + NODE_H / 2) * transform.scale;
    setTransform(prev => ({
      ...prev,
      x: targetX,
      y: targetY,
    }));
  }, [layoutData, transform.scale]);

  const focusOnNodeRef = useRef(focusOnNode);
  focusOnNodeRef.current = focusOnNode;

  useEffect(() => {
    if (selectedNode) {
      const timer = setTimeout(() => {
        focusOnNodeRef.current(selectedNode);
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [selectedNode]);

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

  const parentNodes = new Set<string>();
  if (flowData) {
    for (const node of flowData.nodes) {
      if (node.children && node.children.length > 0) {
        parentNodes.add(node.id);
      }
    }
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
              {visibleNodes.length} 节点 · {visibleEdges.length} 边
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
            <defs>
              <filter id="node-glow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur in="SourceAlpha" stdDeviation="3" result="blur" />
                <feFlood floodColor="currentColor" floodOpacity="0.35" result="color" />
                <feComposite in="color" in2="blur" operator="in" result="glow" />
                <feMerge>
                  <feMergeNode in="glow" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
              <filter id="node-hover-glow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur in="SourceAlpha" stdDeviation="2" result="blur" />
                <feFlood floodColor="currentColor" floodOpacity="0.2" result="color" />
                <feComposite in="color" in2="blur" operator="in" result="glow" />
                <feMerge>
                  <feMergeNode in="glow" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            <g style={{ transition: isInitialLayoutRef.current ? 'none' : 'transform 0.5s ease' }} transform={`translate(${transform.x},${transform.y}) scale(${transform.scale})`}>
              {LAYER_ORDER.map(layer => {
                const bounds = layoutData.layerBounds.get(layer);
                if (!bounds) return null;
                const colors = getLayerColor(layer);
                return (
                  <g key={`layer-${layer}`}>
                    <rect
                      x={bounds.minX}
                      y={bounds.minY}
                      width={bounds.maxX - bounds.minX}
                      height={bounds.maxY - bounds.minY}
                      rx={10}
                      ry={10}
                      fill={colors.fill}
                      stroke={colors.border}
                      strokeWidth={1}
                      strokeDasharray="6 3"
                    />
                    <text
                      x={bounds.minX + 12}
                      y={bounds.minY + 18}
                      fill={colors.text}
                      fontSize={13}
                      fontWeight={700}
                      opacity={0.7}
                    >
                      {LAYER_LABELS[layer]}
                    </text>
                  </g>
                );
              })}

              {layoutData.edgePoints.map((ep, idx) => (
                <g key={`edge-${idx}`}>
                  <path
                    d={orthogonalPath(ep.points)}
                    fill="none"
                    stroke="rgba(148,163,184,0.2)"
                    strokeWidth="1.5"
                  />
                  {ep.points.length >= 2 && (() => {
                    const last = ep.points[ep.points.length - 1];
                    const prev = ep.points[ep.points.length - 2];
                    const angle = Math.atan2(last.y - prev.y, last.x - prev.x) * 180 / Math.PI;
                    const size = 5;
                    return (
                      <polygon
                        points={`${last.x - size},${last.y - size * 0.5} ${last.x - size},${last.y + size * 0.5} ${last.x},${last.y}`}
                        fill="rgba(148,163,184,0.3)"
                        transform={`rotate(${angle}, ${last.x}, ${last.y})`}
                      />
                    );
                  })()}
                </g>
              ))}

              {visibleNodes.map(node => {
                const pos = layoutData.nodePositions.get(node.id);
                if (!pos) return null;
                const colors = getLayerColor(node.layer);
                const isSelected = selectedNode?.id === node.id;
                const isParent = parentNodes.has(node.id);
                const isExpanded = expandedParents.has(node.id);
                const isCollapsed = isParent && !isExpanded;

                const childIds = node.children || [];
                const hasHiddenChildren = isCollapsed && childIds.some(cid => filteredNodes.some(fn => fn.id === cid));

                return (
                  <g
                    key={node.id}
                    transform={`translate(${pos.x},${pos.y})`}
                    style={{
                      transition: isInitialLayoutRef.current ? 'none' : 'transform 0.4s ease, opacity 0.4s ease',
                    }}
                    onClick={() => handleNodeClick(node)}
                    className="cursor-pointer flow-node"
                  >
                    <rect
                      x={0}
                      y={0}
                      width={NODE_W}
                      height={NODE_H}
                      rx={8}
                      ry={8}
                      fill={isSelected ? colors.bg : 'rgba(255,255,255,0.03)'}
                      stroke={isSelected ? colors.border : 'rgba(255,255,255,0.08)'}
                      strokeWidth={isSelected ? 2.5 : 1}
                      className="flow-node-rect"
                      filter={isSelected ? 'url(#node-glow)' : undefined}
                      style={{ color: colors.text, transition: 'all 0.2s ease' }}
                    />
                    <circle cx={12} cy={NODE_H / 2} r={4} fill={colors.text} />
                    <text
                      x={22}
                      y={NODE_H / 2 + 1}
                      fill={colors.text}
                      fontSize={11}
                      dominantBaseline="middle"
                    >
                      {node.label.length > 18 ? node.label.slice(0, 17) + '\u2026' : node.label}
                    </text>
                    <text
                      x={22}
                      y={NODE_H - 8}
                      fill="rgba(148,163,184,0.5)"
                      fontSize={8}
                    >
                      {node.type}
                    </text>
                    {isParent && (
                      <g transform={`translate(${NODE_W - 18}, ${NODE_H / 2})`}>
                        <circle r={7} fill="rgba(255,255,255,0.08)" stroke="rgba(255,255,255,0.15)" strokeWidth={1} />
                        <text
                          textAnchor="middle"
                          dominantBaseline="central"
                          fill="rgba(255,255,255,0.5)"
                          fontSize={10}
                        >
                          {isExpanded ? '\u2212' : '+'}
                        </text>
                        {hasHiddenChildren && (
                          <circle cx={5} cy={-5} r={3} fill={colors.text} />
                        )}
                      </g>
                    )}
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
              \u2212
            </button>
            <button
              onClick={() => setTransform(prev => ({ ...prev, x: 40, y: 40, scale: 1 }))}
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
                  \u2715
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
                              {edge.source === selectedNode.id ? '\u2192' : '\u2190'}
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