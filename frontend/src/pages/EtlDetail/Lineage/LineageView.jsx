import { useMemo, useEffect, useRef, useState } from "react";
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

// Encuadre fijo al entrar y al centrar/restablecer — un solo lugar para
// ajustar zoom/posición en vez de repetirlo en cada callback.
const DEFAULT_VIEWPORT = { x: 100, y: 30, zoom: 1 };

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

function buildFlowData(lineage, stepsMap = {}) {
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
        data: {
          label: n.step_name,
          tipo: n.tipo_step,
          tabla: n.tabla ?? null,
          capa,
          stepInfo: stepsMap[n.step_name] ?? null,
        },
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

export default function LineageView({ lineage, steps = [] }) {
  const stepsMap = useMemo(
    () => Object.fromEntries(steps.map(s => [s.nombre, s])),
    [steps]
  );
  const [hoveredStep, setHoveredStep] = useState(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  const [viewport, setViewport] = useState({ x: 0, y: 0, zoom: 1 });
  const flowData = useMemo(() => buildFlowData(lineage, stepsMap), [lineage, stepsMap]);
  const [nodes, setNodes, onNodesChange] = useNodesState(flowData.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(flowData.edges);
  const rfInstance = useRef(null);
  const canvasRef   = useRef(null);

  useEffect(() => {
    setNodes(flowData.nodes);
    setEdges(flowData.edges);
  }, [flowData, setNodes, setEdges]);

  // El contenedor se dimensiona vía flex (llena el alto disponible de la
  // página) — puede medir 0 en el instante exacto en que React Flow monta
  // (bug de layout ya resuelto en CSS, esto queda como red defensiva). Si el
  // canvas cambia de tamaño, reaplicamos el viewport fijo en vez de dejarlo
  // en lo que haya quedado.
  useEffect(() => {
    const el = canvasRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      rfInstance.current?.setViewport(DEFAULT_VIEWPORT);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Único lugar que aplica el encuadre fijo — lo usan el botón "Centrar",
  // el ResizeObserver de arriba y handleReset.
  const handleCenter = () => {
    rfInstance.current?.setViewport(DEFAULT_VIEWPORT);
  };

  const handleReset = () => {
    const { nodes: freshNodes, edges: freshEdges } = buildFlowData(lineage, stepsMap);
    setNodes(freshNodes);
    setEdges(freshEdges);
    handleCenter();
  };

  // Helper temporal: paneá/zoomeá a mano hasta encontrar el encuadre que
  // quieras y quedan los valores en pantalla + consola para copiar y fijar
  // como defaultViewport={{ x, y, zoom }} en <ReactFlow>.
  const handleMoveEnd = (_, vp) => {
    setViewport(vp);
    console.log("[Lineage] viewport:", vp);
  };

  return (
    <div
      className="lineage-view-wrapper"
      onMouseMove={(e) => setMousePos({ x: e.clientX, y: e.clientY })}
    >
      <div className="ln-toolbar">
        <span className="ln-viewport-readout">
          x: {viewport.x.toFixed(1)} · y: {viewport.y.toFixed(1)} · zoom: {viewport.zoom.toFixed(2)}
        </span>
        <div className="ln-toolbar__actions">
          <button className="ln-reset-btn" onClick={handleCenter}>
            Centrar
          </button>
          <button className="ln-reset-btn" onClick={handleReset}>
            Restablecer orden
          </button>
        </div>
      </div>
      <div className="lineage-view" ref={canvasRef}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          defaultViewport={DEFAULT_VIEWPORT}
          fitView={false}
          proOptions={{ hideAttribution: true }}
          nodesDraggable={true}
          nodesConnectable={false}
          elementsSelectable={true}
          onInit={(instance) => { rfInstance.current = instance; setViewport(instance.getViewport()); }}
          onMoveEnd={handleMoveEnd}
          onNodeMouseEnter={(_, node) => setHoveredStep(node.data.stepInfo ?? null)}
          onNodeMouseLeave={() => setHoveredStep(null)}
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

      {hoveredStep && (
        <div
          className="ln-step-panel"
          style={{ left: mousePos.x + 18, top: mousePos.y + 18 }}
        >
          <span className="ln-step-panel__orden">Step {hoveredStep.orden}</span>
          <p className="ln-step-panel__desc">{hoveredStep.descripcion}</p>
          {hoveredStep.justificacion && (
            <p className="ln-step-panel__just">
              <strong>Por qué:</strong> {hoveredStep.justificacion}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
