import { useMemo, useEffect, useRef } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  MarkerType,
  useNodesState,
  useEdgesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import "./LineageView.css";

const NODE_W  = 220;
const NODE_H  = 94;
const ROW_GAP = 48;
const COL_GAP = 120;

const CAPA_ORDER = ["origen", "staging", "dwh"];
const CAPA_LABEL = { origen: "Origen", staging: "Staging", dwh: "DWH" };

function LineageNodeCard({ data }) {
  return (
    <div className={`ln-node ln-node--${data.capa}`}>
      <Handle type="target" position={Position.Left} className="ln-handle" />
      <div className="ln-node__top">
        <span className={`ln-node__badge ln-node__badge--${data.capa}`}>
          {CAPA_LABEL[data.capa]}
        </span>
        <span className="ln-node__tipo">{data.tipo}</span>
      </div>
      <div className="ln-node__name">{data.label}</div>
      {data.tabla && (
        <div className="ln-node__tabla" title={data.tabla}>{data.tabla}</div>
      )}
      <Handle type="source" position={Position.Right} className="ln-handle" />
    </div>
  );
}

const nodeTypes = { lineageNode: LineageNodeCard };

function buildFlowData(lineage) {
  const byLayer = { origen: [], staging: [], dwh: [] };
  for (const n of lineage.nodes) {
    const bucket = byLayer[n.capa] ?? byLayer.staging;
    bucket.push(n);
  }

  const nodes = [];

  // Column-based layout: each layer is a column (Origen → Staging → DWH, left → right)
  CAPA_ORDER.forEach((capa, colIdx) => {
    const layerNodes = byLayer[capa];
    if (layerNodes.length === 0) return;

    const colX = colIdx * (NODE_W + COL_GAP);

    layerNodes.forEach((n, i) => {
      nodes.push({
        id: n.step_name,
        type: "lineageNode",
        position: { x: colX, y: i * (NODE_H + ROW_GAP) },
        data: { label: n.step_name, tipo: n.tipo_step, tabla: n.tabla ?? null, capa },
        style: { width: NODE_W },
      });
    });
  });

  const edges = lineage.edges.map((e, i) => ({
    id: `e-${i}`,
    source: e.from_step,
    target: e.to_step,
    type: "smoothstep",
    animated: true,
    markerEnd: { type: MarkerType.ArrowClosed, color: "var(--accent)" },
    style: { stroke: "var(--accent)", strokeWidth: 2 },
  }));

  return { nodes, edges };
}

export default function LineageView({ lineage }) {
  const flowData = useMemo(() => buildFlowData(lineage), [lineage]);
  const [nodes, setNodes, onNodesChange] = useNodesState(flowData.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(flowData.edges);
  const rfInstance = useRef(null);

  useEffect(() => {
    setNodes(flowData.nodes);
    setEdges(flowData.edges);
  }, [flowData, setNodes, setEdges]);

  // Canvas height derived from node positions so the page doesn't scroll unnecessarily
  const canvasHeight = useMemo(() => {
    if (flowData.nodes.length === 0) return 300;
    const maxY = Math.max(...flowData.nodes.map(n => n.position.y)) + NODE_H;
    return Math.max(maxY + 80, 300);
  }, [flowData.nodes]);

  const handleReset = () => {
    const { nodes: freshNodes, edges: freshEdges } = buildFlowData(lineage);
    setNodes(freshNodes);
    setEdges(freshEdges);
    setTimeout(() => {
      rfInstance.current?.fitView({ padding: 0.2 });
    }, 50);
  };

  return (
    <div className="lineage-view-wrapper">
      <div className="ln-toolbar">
        <button className="ln-reset-btn" onClick={handleReset}>
          Restablecer orden
        </button>
      </div>
      <div className="lineage-view" style={{ height: canvasHeight }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.18 }}
          proOptions={{ hideAttribution: true }}
          nodesDraggable={true}
          nodesConnectable={false}
          elementsSelectable={true}
          onInit={(instance) => { rfInstance.current = instance; }}
        >
          <Background gap={24} size={1} color="var(--border)" />
          <Controls showInteractive={false} />
          <MiniMap
            nodeColor={(n) => {
              if (n.data?.capa === "origen") return "#22c55e66";
              if (n.data?.capa === "dwh") return "#6366f166";
              return "#f59e0b66";
            }}
            pannable
            zoomable
          />
        </ReactFlow>
      </div>
    </div>
  );
}
