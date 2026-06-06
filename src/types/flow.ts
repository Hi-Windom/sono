export interface FlowNode {
  id: string;
  label: string;
  type: string;
  layer: string;
  filePath: string;
  description?: string;
  children?: string[];
}

export interface FlowEdge {
  source: string;
  target: string;
  label?: string;
  type: string;
}

export interface FlowData {
  nodes: FlowNode[];
  edges: FlowEdge[];
}