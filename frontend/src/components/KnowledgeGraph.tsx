"use client";

import { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3';
import { Database, RotateCcw, ZoomIn, ZoomOut, Maximize } from 'lucide-react';
import { apiFetch } from "@/lib/api";

interface Node extends d3.SimulationNodeDatum {
    id: string;
    group: number;
}

interface Link extends d3.SimulationLinkDatum<Node> {
    source: string;
    target: string;
    value: number;
}

function normalizeGraph(data: { nodes: any[], links: any[] }) {
    const nodes = [...(data.nodes || [])].sort((a, b) => String(a.id).localeCompare(String(b.id)));
    const links = [...(data.links || [])].sort((a, b) =>
        String(a.source).localeCompare(String(b.source)) || String(a.target).localeCompare(String(b.target)));
    return { nodes, links };
}

function graphSignature(data: { nodes: any[], links: any[] }) {
    const n = normalizeGraph(data);
    return `${n.nodes.length}-${n.links.length}-${n.nodes.map((x: any) => x.id).join(",")}`;
}

export default function KnowledgeGraph() {
    const svgRef = useRef<SVGSVGElement>(null);
    const [graphData, setGraphData] = useState<{ nodes: any[], links: any[] }>({ nodes: [], links: [] });
    const [layoutKey, setLayoutKey] = useState(0);
    const lastSigRef = useRef<string>("");
    const zoomHandlerRef = useRef<any>(null);
    const zoomGroupRef = useRef<any>(null);

    useEffect(() => {
        let cancelled = false;
        const fetchGraph = async () => {
            try {
                const response = await apiFetch("/graph");
                if (cancelled || !response.ok) return;
                const data = await response.json();
                const sig = graphSignature(data);
                if (sig !== lastSigRef.current) {
                    lastSigRef.current = sig;
                    setGraphData(normalizeGraph(data));
                }
            } catch (error) {
                if (!cancelled) console.error("Error fetching graph:", error);
            }
        };

        fetchGraph();
        const interval = setInterval(fetchGraph, 60000); // FIX-POLLING: 10s → 60s
        return () => {
            cancelled = true;
            clearInterval(interval);
        };
    }, []);

    useEffect(() => {
        if (!svgRef.current || graphData.nodes.length === 0) return;

        const width = 800;
        const height = 500;

        const data = {
            nodes: graphData.nodes.map((n: any) => ({ ...n })),
            links: graphData.links.map((l: any) => ({ ...l }))
        };

        const svgEl = svgRef.current;
        const svg = d3.select(svgEl)
            .attr("viewBox", `0 0 ${width} ${height}`)
            .style("cursor", "move");

        svg.selectAll("*").remove();

        // Create a container group for zooming
        const g = svg.append("g");
        
        const zoom = d3.zoom<SVGSVGElement, unknown>()
            .scaleExtent([0.1, 5])
            .on("zoom", (event) => {
                g.attr("transform", event.transform);
            });

        svg.call(zoom);
        zoomHandlerRef.current = zoom;
        zoomGroupRef.current = g;

        const colorScale = d3.scaleOrdinal(d3.schemeCategory10);

        const simulation = d3.forceSimulation<Node>(data.nodes as Node[])
            .force("link", d3.forceLink<Node, Link>(data.links).id((d: any) => d.id).distance((d: any) => 100 + ((d.value || 1) * 5)))
            .force("charge", d3.forceManyBody().strength(-800))
            .force("center", d3.forceCenter(width / 2, height / 2))
            .force("collision", d3.forceCollide().radius(30))
            .alpha(0.6)
            .alphaDecay(0.025);

        const link = g.append("g")
            .attr("stroke", "#444")
            .attr("stroke-opacity", 0.3)
            .selectAll("line")
            .data(data.links)
            .join("line")
            .attr("stroke-width", d => Math.sqrt(Math.max(1, (d as any).value ?? 1)));

        const nodeGroup = g.append("g").attr("class", "nodes");
        const node = nodeGroup
            .selectAll("g")
            .data(data.nodes)
            .join("g")
            .style("cursor", "grab");

        node.append("circle")
            .attr("r", 14)
            .attr("fill", (d: any) => colorScale(String(d.group || 1)))
            .attr("stroke", "#222")
            .attr("stroke-width", 2)
            .attr("class", "shadow-xl");

        node.append("text")
            .text((d: any) => d.id)
            .attr("x", 18)
            .attr("y", 4)
            .attr("fill", "#888")
            .style("font-size", "10px")
            .style("font-weight", "500")
            .style("pointer-events", "none")
            .style("font-family", "monospace");

        const drag = d3.drag<SVGGElement, Node>()
            .on("start", function (event) {
                if (!event.active) simulation.alphaTarget(0.3).restart();
                event.subject.fx = event.subject.x;
                event.subject.fy = event.subject.y;
                d3.select(this).style("cursor", "grabbing");
            })
            .on("drag", function (event) {
                // Correctly account for zoom transform during drag
                event.subject.fx = event.x;
                event.subject.fy = event.y;
            })
            .on("end", function (event) {
                if (!event.active) simulation.alphaTarget(0);
                event.subject.fx = null;
                event.subject.fy = null;
                d3.select(this).style("cursor", "grab");
            });

        (node as any).call(drag);

        simulation.on("tick", () => {
            link
                .attr("x1", (d: any) => (d.source as Node).x ?? 0)
                .attr("y1", (d: any) => (d.source as Node).y ?? 0)
                .attr("x2", (d: any) => (d.target as Node).x ?? 0)
                .attr("y2", (d: any) => (d.target as Node).y ?? 0);

            node.attr("transform", (d: any) => `translate(${d.x ?? 0},${d.y ?? 0})`);

            if (simulation.alpha() < 0.005) {
                simulation.stop();
            }
        });

        // Resize listener
        const handleResize = () => {
            const newWidth = svgEl.clientWidth;
            const newHeight = svgEl.clientHeight;
            svg.attr("viewBox", `0 0 ${newWidth} ${newHeight}`);
            simulation.force("center", d3.forceCenter(newWidth / 2, newHeight / 2));
            simulation.alpha(0.3).restart();
        };
        window.addEventListener("resize", handleResize);

        return () => {
            simulation.stop();
            window.removeEventListener("resize", handleResize);
        };
    }, [graphData, layoutKey]);

    const handleZoomIn = () => {
        if (svgRef.current && zoomHandlerRef.current) {
            d3.select(svgRef.current).transition().call(zoomHandlerRef.current.scaleBy, 1.3);
        }
    };

    const handleZoomOut = () => {
        if (svgRef.current && zoomHandlerRef.current) {
            d3.select(svgRef.current).transition().call(zoomHandlerRef.current.scaleBy, 0.7);
        }
    };

    const handleZoomReset = () => {
        if (svgRef.current && zoomHandlerRef.current) {
            d3.select(svgRef.current).transition().call(zoomHandlerRef.current.transform, d3.zoomIdentity);
            setLayoutKey(k => k + 1);
        }
    };

    if (graphData.nodes.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center h-full text-gray-600 space-y-2">
                <div className="w-12 h-12 bg-gray-800/50 rounded-full flex items-center justify-center animate-pulse">
                    <Database size={20} />
                </div>
                <p className="text-xs uppercase tracking-widest font-bold">Esperando descubrimientos...</p>
                <p className="text-[10px] opacity-50 px-10">El mapa se dibujará automáticamente cuando una investigación pase los filtros de calidad.</p>
            </div>
        );
    }

    return (
        <div className="relative h-full w-full overflow-hidden bg-[#080808]/50 rounded-2xl border border-gray-900 shadow-inner">
            <svg ref={svgRef} className="h-full w-full" />
            
            {/* Zoom Controls Overlay */}
            <div className="absolute bottom-4 right-4 flex flex-col gap-2 z-10">
                <button
                    onClick={handleZoomIn}
                    className="p-2 rounded-lg bg-gray-900/80 border border-gray-800 text-gray-400 hover:text-blue-400 hover:bg-gray-800 transition-all shadow-lg"
                    title="Zoom In"
                >
                    <ZoomIn size={18} />
                </button>
                <button
                    onClick={handleZoomOut}
                    className="p-2 rounded-lg bg-gray-900/80 border border-gray-800 text-gray-400 hover:text-blue-400 hover:bg-gray-800 transition-all shadow-lg"
                    title="Zoom Out"
                >
                    <ZoomOut size={18} />
                </button>
                <button
                    onClick={handleZoomReset}
                    className="p-2 rounded-lg bg-gray-900/80 border border-gray-800 text-gray-400 hover:text-blue-400 hover:bg-gray-800 transition-all shadow-lg"
                    title="Centrar Mapa"
                >
                    <Maximize size={18} />
                </button>
            </div>


            <div className="absolute top-4 right-4 z-10">
                <button
                    type="button"
                    onClick={handleZoomReset}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600/10 hover:bg-blue-600/20 border border-blue-500/20 text-blue-400 text-[10px] font-bold uppercase tracking-wider transition-all"
                >
                    <RotateCcw size={12} />
                    Reiniciar Vista
                </button>
            </div>
        </div>
    );
}
