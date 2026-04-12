"use client";
import React, { useEffect, useRef } from "react";
import { Cpu, Search, AlertCircle } from "lucide-react";

export default function ResearchSession({ logs = [] }: { logs?: any[] }) {
    const scrollRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [logs]);
    return (
        <div className="bg-[#111] border border-gray-800 rounded-3xl overflow-hidden h-full flex flex-col">
            <div className="p-6 border-b border-gray-800 flex items-center justify-between bg-gradient-to-r from-[#111] to-[#161616]">
                <div className="flex items-center gap-3">
                    <Cpu className="text-amber-500" size={20} />
                    <h3 className="font-semibold">Live Research Stream</h3>
                </div>
                <div className="px-3 py-1 bg-amber-500/10 border border-amber-500/20 rounded-full text-[10px] text-amber-500 font-bold uppercase tracking-widest">
                    Active Session
                </div>
            </div>

            <div ref={scrollRef} className="flex-1 p-6 font-mono text-xs space-y-4 overflow-y-auto scrollbar-hide">
                {logs.slice(-50).map((log, idx) => {
                    const agentColors: Record<string, string> = {
                        "RESEARCHER": "text-blue-400",
                        "CODER": "text-purple-400",
                        "VALIDATOR": "text-rose-400",
                        "SYNTHESIS": "text-emerald-400",
                        "SWARM": "text-amber-400",
                        "PLANNER": "text-cyan-400",
                        "VISION": "text-pink-400"
                    };
                    const colorClass = agentColors[log.agent?.toUpperCase()] || "text-blue-500";
                    
                    return (
                        <div key={idx} className="flex gap-4 group hover:bg-white/5 p-1 rounded transition-all">
                            <span className="text-gray-600 w-16 shrink-0">{log.time}</span>
                            <span className={`${colorClass} font-bold w-24 shrink-0 truncate`}>[{log.agent}]</span>
                            <span className="text-gray-400 group-hover:text-gray-200 transition-colors">{log.message}</span>
                        </div>
                    );
                })}
                <div className="flex gap-4 animate-pulse">
                    <span className="text-gray-600 w-16">...</span>
                    <span className="text-green-500 font-bold w-20">[Librarian]</span>
                    <span className="text-gray-400 italic">Sincronizando con base vectorial...</span>
                </div>
            </div>
        </div>
    );
}
