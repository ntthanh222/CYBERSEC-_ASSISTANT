import React, { memo, useCallback, useEffect, useMemo, useState } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  Panel,
  Position,
  ReactFlowProvider,
  type Edge,
  type Node,
  type NodeProps,
  useReactFlow,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { AlertTriangle, Crosshair, Database, GitBranch, Globe2, Network, Plus, RefreshCw, Server, Shield, X } from 'lucide-react';
import {
  createAttackEdge,
  createAttackNode,
  getAttackGraph,
  type AttackGraph,
  type AttackGraphNode,
  type AttackNodeStatus,
  type AttackNodeType,
  type AttackSeverity,
} from '../../../lib/api/attackGraph';

const NODE_WIDTH = 280;
const NODE_HEIGHT = 124;
const RANK_SEPARATION = 360;
const NODE_SEPARATION = 180;
const CANVAS_MIN_HEIGHT = 620;

const STATUS_COLORS: Record<string, string> = {
  compromised: '#ff716c',
  vulnerable: '#f59e0b',
  secure: '#84fdad',
};

const TYPE_COLORS: Record<string, string> = {
  attacker: '#ff716c',
  asset: '#78e3ff',
  database: '#bfa3ff',
  gateway: '#f59e0b',
  target: '#84fdad',
};

const NODE_TYPE_LABELS: Record<string, string> = {
  attacker: 'Kẻ tấn công',
  asset: 'Tài sản',
  database: 'Cơ sở dữ liệu',
  gateway: 'MITRE / Gateway',
  target: 'Mục tiêu / Incident',
};

const SEVERITY_LABELS: Record<string, string> = {
  critical: 'Nghiêm trọng',
  high: 'Cao',
  medium: 'Trung bình',
  low: 'Thấp',
};

const NODE_TYPE_OPTIONS: AttackNodeType[] = ['attacker', 'asset', 'database', 'gateway', 'target'];
const SEVERITY_OPTIONS: AttackSeverity[] = ['critical', 'high', 'medium', 'low'];

interface AttackNodeData {
  attackNode: AttackGraphNode;
  onSelect: (node: AttackGraphNode) => void;
}

interface LayoutResult {
  nodes: Node<AttackNodeData>[];
  edges: Edge[];
}

function nodeIcon(type: string) {
  if (type === 'attacker') return Globe2;
  if (type === 'database') return Database;
  if (type === 'gateway') return GitBranch;
  if (type === 'target') return Crosshair;
  return Server;
}

function orderValue(node: AttackGraphNode): number {
  if (node.node_type === 'attacker') return 0;
  if (node.node_type === 'asset') return 1;
  if (node.node_type === 'database') return 2;
  if (node.node_type === 'target') return 3;
  if (node.node_type === 'gateway') return 4;
  return 5;
}

function stableNodeSort(a: AttackGraphNode, b: AttackGraphNode): number {
  return orderValue(a) - orderValue(b) || a.position_x - b.position_x || a.position_y - b.position_y || a.label.localeCompare(b.label) || a.id.localeCompare(b.id);
}

function computeRanks(graph: AttackGraph): Map<string, number> {
  const nodes = [...graph.nodes].sort(stableNodeSort);
  const nodeIds = new Set(nodes.map((node) => node.id));
  const incoming = new Map<string, number>();
  const outgoing = new Map<string, string[]>();

  for (const node of nodes) {
    incoming.set(node.id, 0);
    outgoing.set(node.id, []);
  }

  for (const edge of graph.edges) {
    if (!nodeIds.has(edge.source_node_id) || !nodeIds.has(edge.target_node_id)) continue;
    incoming.set(edge.target_node_id, (incoming.get(edge.target_node_id) ?? 0) + 1);
    outgoing.get(edge.source_node_id)?.push(edge.target_node_id);
  }

  for (const targets of outgoing.values()) {
    targets.sort((a, b) => {
      const nodeA = graph.nodes.find((node) => node.id === a);
      const nodeB = graph.nodes.find((node) => node.id === b);
      if (!nodeA || !nodeB) return a.localeCompare(b);
      return stableNodeSort(nodeA, nodeB);
    });
  }

  const ranks = new Map<string, number>();
  const queue = nodes.filter((node) => (incoming.get(node.id) ?? 0) === 0);
  if (queue.length === 0) queue.push(...nodes.filter((node) => node.node_type === 'attacker'));
  if (queue.length === 0 && nodes[0]) queue.push(nodes[0]);

  for (const node of queue) ranks.set(node.id, 0);

  let cursor = 0;
  while (cursor < queue.length) {
    const source = queue[cursor++];
    const nextRank = (ranks.get(source.id) ?? 0) + 1;
    for (const targetId of outgoing.get(source.id) ?? []) {
      const previous = ranks.get(targetId);
      if (previous === undefined || previous < nextRank) ranks.set(targetId, nextRank);
      incoming.set(targetId, Math.max(0, (incoming.get(targetId) ?? 0) - 1));
      if ((incoming.get(targetId) ?? 0) === 0) {
        const target = nodes.find((node) => node.id === targetId);
        if (target && !queue.some((queued) => queued.id === target.id)) queue.push(target);
      }
    }
  }

  for (const node of nodes) {
    if (!ranks.has(node.id)) {
      const fallbackRank = Math.max(0, Math.round((node.position_x || 0) / RANK_SEPARATION));
      ranks.set(node.id, fallbackRank);
    }
  }

  return ranks;
}

function layoutGraph(graph: AttackGraph, onSelect: (node: AttackGraphNode) => void): LayoutResult {
  const ranks = computeRanks(graph);
  const rankGroups = new Map<number, AttackGraphNode[]>();

  for (const node of [...graph.nodes].sort(stableNodeSort)) {
    const rank = ranks.get(node.id) ?? 0;
    const group = rankGroups.get(rank) ?? [];
    group.push(node);
    rankGroups.set(rank, group);
  }

  const largestRankSize = Math.max(1, ...Array.from(rankGroups.values()).map((group) => group.length));
  const centerOffset = ((largestRankSize - 1) * NODE_SEPARATION) / 2;
  const reactNodes: Node<AttackNodeData>[] = [];

  for (const [rank, group] of Array.from(rankGroups.entries()).sort(([a], [b]) => a - b)) {
    group.sort(stableNodeSort);
    const groupOffset = ((group.length - 1) * NODE_SEPARATION) / 2;
    group.forEach((attackNode, index) => {
      reactNodes.push({
        id: attackNode.id,
        type: 'attackNode',
        position: {
          x: rank * RANK_SEPARATION,
          y: centerOffset - groupOffset + index * NODE_SEPARATION,
        },
        data: { attackNode, onSelect },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
      });
    });
  }

  const parallelCounts = new Map<string, number>();
  const reactEdges = graph.edges.map((edge) => {
    const pairKey = `${edge.source_node_id}->${edge.target_node_id}`;
    const parallelIndex = parallelCounts.get(pairKey) ?? 0;
    parallelCounts.set(pairKey, parallelIndex + 1);
    const labelOffset = (parallelIndex % 3) * 18;

    return {
      id: edge.id,
      source: edge.source_node_id,
      target: edge.target_node_id,
      type: 'smoothstep',
      label: edge.label,
      data: { original: edge },
      className: `attack-graph-edge attack-graph-edge-${edge.status}`,
      markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18, color: edge.status === 'blocked' ? '#84fdad' : '#94a3b8' },
      style: {
        stroke: edge.status === 'blocked' ? '#84fdad' : edge.status === 'active' ? '#78e3ff' : '#94a3b8',
        strokeWidth: 2,
        strokeDasharray: edge.status === 'potential' ? '7 7' : undefined,
      },
      labelBgPadding: [8, 5] as [number, number],
      labelBgBorderRadius: 6,
      labelBgStyle: { fill: '#0f0f14', fillOpacity: 0.96, stroke: '#1c1c24', strokeWidth: 1 },
      labelStyle: { fill: '#fbf8fc', fontSize: 11, fontWeight: 700 },
      labelShowBg: true,
      pathOptions: { offset: 24 + labelOffset, borderRadius: 18 },
    } satisfies Edge;
  });

  return { nodes: reactNodes, edges: reactEdges };
}

const AttackGraphNodeCard = memo(({ data, selected }: NodeProps<AttackNodeData>) => {
  const attackNode = data.attackNode;
  const Icon = nodeIcon(attackNode.node_type);
  const typeColor = TYPE_COLORS[attackNode.node_type] ?? '#78e3ff';
  const statusColor = STATUS_COLORS[attackNode.status] ?? typeColor;

  return (
    <div
      role="button"
      tabIndex={0}
      title={`${attackNode.label} - ${NODE_TYPE_LABELS[attackNode.node_type] ?? attackNode.node_type}`}
      data-testid={`attack-node-${attackNode.id}`}
      onClick={() => data.onSelect(attackNode)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          data.onSelect(attackNode);
        }
      }}
      className={`attack-node-card text-left ${selected ? 'attack-node-card-selected' : ''}`}
      style={{ '--node-accent': typeColor, '--node-status': statusColor } as React.CSSProperties}
    >
      <div className="attack-node-main">
        <div className="attack-node-icon" aria-hidden="true">
          <Icon className="h-4 w-4" />
        </div>
        <div className="min-w-0">
          <div className="attack-node-title" data-testid={`attack-node-label-${attackNode.id}`}>{attackNode.label}</div>
          <div className="attack-node-subtitle">{NODE_TYPE_LABELS[attackNode.node_type] ?? attackNode.node_type}</div>
        </div>
      </div>
      <div className="attack-node-meta">
        <span>{SEVERITY_LABELS[attackNode.severity] ?? attackNode.severity}</span>
        <span>{attackNode.ip_address || attackNode.status}</span>
      </div>
    </div>
  );
});

AttackGraphNodeCard.displayName = 'AttackGraphNodeCard';

const nodeTypes = { attackNode: AttackGraphNodeCard };

const AttackGraphCanvasInner: React.FC<{
  graph: AttackGraph;
  selectedNode: AttackGraphNode | null;
  onSelectNode: (node: AttackGraphNode | null) => void;
}> = ({ graph, selectedNode, onSelectNode }) => {
  const { fitView } = useReactFlow();
  const { nodes, edges } = useMemo(() => layoutGraph(graph, onSelectNode), [graph, onSelectNode]);

  const runFitView = useCallback(() => {
    window.setTimeout(() => {
      fitView({ padding: graph.nodes.length <= 6 ? 0.18 : 0.12, duration: 260, maxZoom: graph.nodes.length <= 6 ? 1.08 : 0.92 });
    }, 40);
  }, [fitView, graph.nodes.length]);

  useEffect(runFitView, [runFitView, nodes.length, edges.length]);

  return (
    <div className="attack-graph-flow" data-testid="attack-graph-canvas">
      <div className="sr-only" aria-hidden="true">
        {graph.edges.map((edge) => <span key={edge.id} data-testid={`attack-edge-${edge.id}`} />)}
      </div>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        nodesDraggable
        nodesConnectable={false}
        elementsSelectable
        fitView
        minZoom={0.35}
        maxZoom={1.35}
        defaultEdgeOptions={{ interactionWidth: 18 }}
        onPaneClick={() => onSelectNode(null)}
        onNodeClick={(_, node) => onSelectNode((node.data as AttackNodeData).attackNode)}
      >
        <Background color="#1c1c24" gap={28} size={1} />
        <Controls className="attack-graph-controls" showInteractive={false} />
        {graph.nodes.length >= 10 && <MiniMap className="attack-graph-minimap" nodeColor={(node) => TYPE_COLORS[(node.data as AttackNodeData).attackNode.node_type] ?? '#78e3ff'} pannable zoomable />}
        <Panel position="top-left" className="attack-graph-legend">
          {Object.entries(NODE_TYPE_LABELS).map(([type, label]) => (
            <span key={type}><span style={{ background: TYPE_COLORS[type] }} />{label}</span>
          ))}
        </Panel>
        <Panel position="top-right">
          <button type="button" className="attack-graph-action" onClick={runFitView}>
            <Network className="h-3.5 w-3.5" /> Tự sắp xếp
          </button>
        </Panel>
      </ReactFlow>

      {selectedNode && (
        <aside className="attack-node-drawer" data-testid="attack-node-details">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-[10px] uppercase font-mono tracking-wider text-text-muted">Node details</p>
              <h3 className="text-sm font-bold text-text-primary break-words">{selectedNode.label}</h3>
            </div>
            <button type="button" className="p-1 rounded border border-surface-container-highest" onClick={() => onSelectNode(null)} aria-label="Đóng chi tiết node">
              <X className="h-4 w-4" />
            </button>
          </div>
          <dl className="mt-4 grid grid-cols-1 gap-3 text-xs">
            <div><dt>Type</dt><dd>{NODE_TYPE_LABELS[selectedNode.node_type] ?? selectedNode.node_type}</dd></div>
            <div><dt>IP / Host</dt><dd>{selectedNode.ip_address || 'Không có'}</dd></div>
            <div><dt>Severity</dt><dd>{SEVERITY_LABELS[selectedNode.severity] ?? selectedNode.severity}</dd></div>
            <div><dt>Status</dt><dd>{selectedNode.status}</dd></div>
            {selectedNode.cves?.length > 0 && <div><dt>CVEs</dt><dd>{selectedNode.cves.join(', ')}</dd></div>}
            {selectedNode.description && <div><dt>Description</dt><dd className="whitespace-pre-wrap">{selectedNode.description}</dd></div>}
            <div><dt>Connections</dt><dd>{graph.edges.filter((edge) => edge.source_node_id === selectedNode.id || edge.target_node_id === selectedNode.id).length}</dd></div>
          </dl>
        </aside>
      )}
    </div>
  );
};

const AttackGraphCanvas: React.FC<{
  graph: AttackGraph;
  selectedNode: AttackGraphNode | null;
  onSelectNode: (node: AttackGraphNode | null) => void;
}> = (props) => (
  <ReactFlowProvider>
    <AttackGraphCanvasInner {...props} />
  </ReactFlowProvider>
);

export const AttackGraphView: React.FC = () => {
  const [graph, setGraph] = useState<AttackGraph>({ nodes: [], edges: [] });
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [selectedNode, setSelectedNode] = useState<AttackGraphNode | null>(null);
  const [nodeForm, setNodeForm] = useState({
    label: '',
    node_type: 'asset' as AttackNodeType,
    status: 'vulnerable' as AttackNodeStatus,
    severity: 'high' as AttackSeverity,
    ip_address: '',
  });
  const [edgeForm, setEdgeForm] = useState({
    source_node_id: '',
    target_node_id: '',
    label: '',
  });

  const load = useCallback(() => {
    setIsLoading(true);
    setError('');
    getAttackGraph()
      .then((nextGraph) => {
        setGraph(nextGraph);
        setSelectedNode((current) => nextGraph.nodes.find((node) => node.id === current?.id) ?? null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Không thể tải Attack Graph.'))
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(load, [load]);

  const addNode = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    try {
      await createAttackNode({
        ...nodeForm,
        position_x: 0,
        position_y: 0,
      });
      setNodeForm({ label: '', node_type: 'asset', status: 'vulnerable', severity: 'high', ip_address: '' });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không thể thêm node.');
    }
  };

  const addEdge = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    try {
      await createAttackEdge({ ...edgeForm, status: 'potential' });
      setEdgeForm({ source_node_id: '', target_node_id: '', label: '' });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không thể thêm liên kết.');
    }
  };

  return (
    <div className="space-y-5 min-w-0">
      <div className="flex flex-col gap-3 border-b border-surface-container-highest/60 pb-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">Sơ đồ Attack Graph</h2>
          <p className="text-xs text-text-secondary">Các đường tấn công giữa tài sản, mục tiêu và điểm xoay trục do chuyên viên phân tích ghi nhận.</p>
        </div>
        <button onClick={load} className="flex w-fit items-center gap-1.5 rounded-lg border border-surface-container-highest px-3 py-2 text-xs"><RefreshCw className="h-3.5 w-3.5" /> Làm mới</button>
      </div>

      <div className="grid grid-cols-1 gap-3 2xl:grid-cols-[1fr_1fr]">
        <form onSubmit={addNode} className="attack-graph-form">
          <div className="attack-graph-form-title">Create Node</div>
          <input required value={nodeForm.label} onChange={(e) => setNodeForm({ ...nodeForm, label: e.target.value })} placeholder="Tên node" className="attack-graph-input attack-graph-input-wide" />
          <input value={nodeForm.ip_address} onChange={(e) => setNodeForm({ ...nodeForm, ip_address: e.target.value })} placeholder="IP / host" className="attack-graph-input" />
          <select value={nodeForm.node_type} onChange={(e) => setNodeForm({ ...nodeForm, node_type: e.target.value as AttackNodeType })} className="attack-graph-input">
            {NODE_TYPE_OPTIONS.map((type) => <option key={type} value={type}>{NODE_TYPE_LABELS[type]}</option>)}
          </select>
          <select value={nodeForm.severity} onChange={(e) => setNodeForm({ ...nodeForm, severity: e.target.value as AttackSeverity })} className="attack-graph-input">
            {SEVERITY_OPTIONS.map((severity) => <option key={severity} value={severity}>{SEVERITY_LABELS[severity]}</option>)}
          </select>
          <button className="attack-graph-submit"><Plus className="h-3.5 w-3.5" /> Node</button>
        </form>

        <form onSubmit={addEdge} className="attack-graph-form">
          <div className="attack-graph-form-title">Create Relation</div>
          <select required value={edgeForm.source_node_id} onChange={(e) => setEdgeForm({ ...edgeForm, source_node_id: e.target.value })} className="attack-graph-input">
            <option value="">Nguồn</option>
            {graph.nodes.map((node) => <option key={node.id} value={node.id}>{node.label}</option>)}
          </select>
          <select required value={edgeForm.target_node_id} onChange={(e) => setEdgeForm({ ...edgeForm, target_node_id: e.target.value })} className="attack-graph-input">
            <option value="">Mục tiêu</option>
            {graph.nodes.map((node) => <option key={node.id} value={node.id}>{node.label}</option>)}
          </select>
          <input required value={edgeForm.label} onChange={(e) => setEdgeForm({ ...edgeForm, label: e.target.value })} placeholder="Tên đường liên kết" className="attack-graph-input attack-graph-input-wide" />
          <button className="attack-graph-secondary-submit">Thêm liên kết</button>
        </form>
      </div>

      {error && <div className="flex items-center gap-2 rounded-lg border border-critical/30 bg-critical/10 p-3 text-xs text-critical"><AlertTriangle className="h-4 w-4" />{error}</div>}

      <div className="overflow-hidden rounded-lg border border-surface-container-highest bg-surface-container">
        {isLoading ? (
          <div className="py-20 text-center text-xs text-text-muted">Đang tải Attack Graph...</div>
        ) : graph.nodes.length === 0 ? (
          <div className="flex min-h-[420px] flex-col items-center justify-center gap-3 px-4 text-center text-xs text-text-muted">
            <Shield className="h-8 w-8 text-primary" />
            <div>
              <p className="text-sm font-bold text-text-primary">Chưa có dữ liệu Attack Graph</p>
              <p className="mt-1">Tạo node đầu tiên hoặc generate từ incident để bắt đầu.</p>
            </div>
          </div>
        ) : (
          <AttackGraphCanvas graph={graph} selectedNode={selectedNode} onSelectNode={setSelectedNode} />
        )}
      </div>

      <style>{`
        .attack-graph-flow {
          position: relative;
          height: min(72vh, 780px);
          min-height: ${CANVAS_MIN_HEIGHT}px;
          width: 100%;
          background:
            radial-gradient(circle at 25% 15%, rgba(120, 227, 255, 0.08), transparent 32%),
            linear-gradient(180deg, rgba(15, 15, 20, 0.96), rgba(7, 7, 9, 0.96));
        }
        .attack-node-card {
          width: ${NODE_WIDTH}px;
          min-height: ${NODE_HEIGHT}px;
          border: 1px solid color-mix(in srgb, var(--node-accent) 58%, #1c1c24);
          border-left: 4px solid var(--node-accent);
          border-radius: 8px;
          background: rgba(15, 15, 20, 0.98);
          box-shadow: 0 14px 32px rgba(0, 0, 0, 0.38);
          color: #fbf8fc;
          padding: 12px;
          overflow: hidden;
        }
        .attack-node-card:hover,
        .attack-node-card-selected {
          border-color: var(--node-accent);
          box-shadow: 0 0 0 1px var(--node-accent), 0 16px 36px rgba(0, 0, 0, 0.48);
        }
        .attack-node-main {
          display: grid;
          grid-template-columns: 32px minmax(0, 1fr);
          gap: 10px;
          align-items: start;
        }
        .attack-node-icon {
          display: grid;
          place-items: center;
          width: 32px;
          height: 32px;
          border-radius: 999px;
          background: color-mix(in srgb, var(--node-accent) 16%, transparent);
          color: var(--node-accent);
        }
        .attack-node-title {
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
          overflow-wrap: anywhere;
          line-height: 1.25;
          min-height: 32px;
          font-size: 13px;
          font-weight: 800;
          letter-spacing: 0;
        }
        .attack-node-subtitle {
          margin-top: 4px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          color: #acaaae;
          font-size: 10px;
          text-transform: uppercase;
          letter-spacing: 0;
        }
        .attack-node-meta {
          display: flex;
          justify-content: space-between;
          gap: 8px;
          margin-top: 12px;
          color: #fbf8fc;
          font-size: 10px;
          font-weight: 700;
        }
        .attack-node-meta span {
          min-width: 0;
          max-width: 48%;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          border-radius: 999px;
          border: 1px solid #1c1c24;
          background: rgba(255, 255, 255, 0.04);
          padding: 4px 7px;
        }
        .attack-graph-edge-potential {
          opacity: 0.86;
        }
        .attack-graph-controls {
          border: 1px solid #1c1c24;
          border-radius: 8px;
          overflow: hidden;
          box-shadow: 0 8px 20px rgba(0, 0, 0, 0.38);
        }
        .attack-graph-controls button {
          background: #0f0f14;
          border-bottom: 1px solid #1c1c24;
          color: #fbf8fc;
        }
        .attack-graph-controls button:hover {
          background: #14141a;
        }
        .attack-graph-minimap {
          background: rgba(15, 15, 20, 0.96);
          border: 1px solid #1c1c24;
          border-radius: 8px;
        }
        .attack-graph-legend {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          max-width: min(720px, calc(100vw - 80px));
          border: 1px solid #1c1c24;
          border-radius: 8px;
          background: rgba(15, 15, 20, 0.94);
          padding: 8px;
          color: #acaaae;
          font-size: 10px;
          box-shadow: 0 8px 20px rgba(0, 0, 0, 0.28);
        }
        .attack-graph-legend span {
          display: inline-flex;
          align-items: center;
          gap: 5px;
          white-space: nowrap;
        }
        .attack-graph-legend span span {
          width: 9px;
          height: 9px;
          border-radius: 999px;
        }
        .attack-graph-action {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          border: 1px solid #1c1c24;
          border-radius: 8px;
          background: rgba(15, 15, 20, 0.96);
          padding: 8px 10px;
          color: #fbf8fc;
          font-size: 11px;
          font-weight: 800;
          box-shadow: 0 8px 20px rgba(0, 0, 0, 0.28);
        }
        .attack-node-drawer {
          position: absolute;
          right: 12px;
          bottom: 12px;
          z-index: 8;
          width: min(340px, calc(100% - 24px));
          max-height: min(520px, calc(100% - 100px));
          overflow: auto;
          border: 1px solid #1c1c24;
          border-radius: 8px;
          background: rgba(15, 15, 20, 0.98);
          box-shadow: 0 18px 46px rgba(0, 0, 0, 0.48);
          padding: 14px;
        }
        .attack-node-drawer dt {
          color: #828184;
          font-size: 10px;
          text-transform: uppercase;
        }
        .attack-node-drawer dd {
          margin-top: 2px;
          color: #fbf8fc;
          overflow-wrap: anywhere;
        }
        .attack-graph-form {
          display: grid;
          grid-template-columns: repeat(1, minmax(0, 1fr));
          gap: 8px;
          border: 1px solid #1c1c24;
          border-radius: 8px;
          background: #0f0f14;
          padding: 12px;
        }
        .attack-graph-form-title {
          color: #828184;
          font-size: 10px;
          font-weight: 800;
          text-transform: uppercase;
        }
        .attack-graph-input {
          min-width: 0;
          border: 1px solid #1c1c24;
          border-radius: 6px;
          background: #070709;
          padding: 9px 10px;
          color: #fbf8fc;
          font-size: 12px;
        }
        .attack-graph-submit,
        .attack-graph-secondary-submit {
          display: inline-flex;
          min-height: 38px;
          align-items: center;
          justify-content: center;
          gap: 6px;
          border-radius: 6px;
          padding: 9px 12px;
          font-size: 12px;
          font-weight: 800;
        }
        .attack-graph-submit {
          background: #84fdad;
          color: #070709;
        }
        .attack-graph-secondary-submit {
          border: 1px solid #1c1c24;
          color: #fbf8fc;
        }
        @media (min-width: 1180px) {
          .attack-graph-form {
            grid-template-columns: auto repeat(4, minmax(120px, 1fr)) auto;
            align-items: center;
          }
          .attack-graph-input-wide {
            grid-column: span 2 / span 2;
          }
          .attack-graph-form-title {
            align-self: center;
          }
        }
        @media (max-width: 767px) {
          .attack-graph-flow {
            height: 68vh;
            min-height: 520px;
          }
          .attack-graph-legend {
            max-width: calc(100vw - 36px);
            padding: 6px;
          }
          .attack-node-drawer {
            left: 12px;
            right: 12px;
            width: auto;
            max-height: 44%;
          }
        }
      `}</style>
    </div>
  );
};

export default AttackGraphView;
