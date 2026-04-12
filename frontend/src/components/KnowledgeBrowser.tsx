"use client";
import React, { useEffect, useState, useRef } from "react";
import { ChevronRight, ChevronDown, Database, ExternalLink, BookOpen, CheckCircle2, AlertCircle } from "lucide-react";
import { apiFetch } from "@/lib/api";

export default function KnowledgeBrowser() {
    const [items, setItems] = useState<any[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
    const [isUploading, setIsUploading] = useState(false);
    const [uploadStatus, setUploadStatus] = useState<{ type: 'success' | 'error', message: string } | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        let cancelled = false;
        const fetchKnowledge = async () => {
            try {
                const response = await apiFetch("/knowledge");
                if (cancelled) return;
                if (response.ok) {
                    const data = await response.json();
                    setItems(data);
                }
            } catch (error) {
                if (!cancelled) console.error("Error fetching knowledge:", error);
            } finally {
                if (!cancelled) setIsLoading(false);
            }
        };

        fetchKnowledge();
        const interval = setInterval(fetchKnowledge, 30000); // FIX-POLLING: 5s → 30s
        return () => {
            cancelled = true;
            clearInterval(interval);
        };
    }, []);

    const handleBookUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setIsUploading(true);
        setUploadStatus(null);
        
        const formData = new FormData();
        formData.append("file", file);

        try {
            const response = await apiFetch("/library/upload", {
                method: "POST",
                body: formData
            });

            if (response.ok) {
                const data = await response.json();
                setUploadStatus({ type: 'success', message: data.message });
                if (fileInputRef.current) fileInputRef.current.value = "";
            } else {
                const err = await response.json();
                setUploadStatus({ type: 'error', message: err.detail || "Error al subir el libro" });
            }
        } catch (error) {
            setUploadStatus({ type: 'error', message: "Error de conexión con el servidor" });
        } finally {
            setIsUploading(false);
            setTimeout(() => setUploadStatus(null), 5000);
        }
    };

    if (isLoading && items.length === 0) {
        return <div className="p-12 text-center flex flex-col items-center gap-4">
            <div className="w-10 h-10 border-4 border-blue-500/20 border-t-blue-500 rounded-full animate-spin" />
            <p className="text-gray-500 text-sm animate-pulse">Sincronizando biblioteca personal...</p>
        </div>;
    }

    return (
        <div className="space-y-4">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-blue-600/10 rounded-xl flex items-center justify-center border border-blue-500/20">
                        <Database className="text-blue-500" size={20} />
                    </div>
                    <div>
                        <h3 className="text-xl font-bold text-white tracking-tight">Biblioteca de Conocimiento</h3>
                        <p className="text-xs text-gray-500">Investigaciones y archivos indexados</p>
                    </div>
                </div>
                
                <div className="flex flex-col items-end gap-2">
                    <input 
                        type="file" 
                        ref={fileInputRef}
                        className="hidden" 
                        accept=".pdf,.epub,.txt"
                        onChange={handleBookUpload}
                        aria-label="Seleccionar archivo para cargar a la biblioteca"
                        title="Seleccionar archivo de libro (.pdf, .epub, .txt)"
                    />
                    <button
                        onClick={() => fileInputRef.current?.click()}
                        disabled={isUploading}
                        aria-label={isUploading ? "Procesando el libro seleccionado" : "Cargar un libro completo en formato PDF, EPUB o TXT"}
                        className={`flex items-center gap-2 px-5 py-2.5 rounded-xl border transition-all text-sm font-semibold shadow-lg shadow-blue-600/10 ${isUploading ? 'bg-gray-800 border-gray-700 text-gray-500 cursor-not-allowed' : 'bg-blue-600 border-blue-500 text-white hover:bg-blue-500 hover:scale-[1.02]'}`}
                    >
                        {isUploading ? (
                            <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        ) : (
                            <BookOpen size={16} />
                        )}
                        {isUploading ? "Procesando..." : "Cargar Libro Completo"}
                    </button>
                    <span className="text-[10px] text-gray-600 font-medium">PDF, EPUB o TXT</span>
                </div>
            </div>

            {uploadStatus && (
                <div className={`p-4 rounded-2xl flex items-center gap-3 border animate-in fade-in slide-in-from-top-2 duration-300 ${uploadStatus.type === 'success' ? 'bg-green-500/10 border-green-500/20 text-green-400' : 'bg-red-500/10 border-red-500/20 text-red-400'}`}>
                    {uploadStatus.type === 'success' ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
                    <span className="text-sm font-medium">{uploadStatus.message}</span>
                </div>
            )}

            <div className="grid grid-cols-1 gap-3">
                {items.length === 0 ? (
                    <div className="bg-[#161616] border border-gray-800 p-8 rounded-2xl text-center text-gray-500">
                        No hay fragmentos de conocimiento disponibles aún.
                    </div>
                ) : (
                    items.map((item, idx) => (
                        <div key={item.id || idx} className="bg-[#161616] border border-gray-800 rounded-2xl overflow-hidden transition-all">
                            <div 
                                onClick={() => setExpandedIdx(expandedIdx === idx ? null : idx)}
                                className="p-4 flex items-center justify-between hover:bg-[#1a1a1a] transition-all cursor-pointer group"
                            >
                                <div className="flex items-center gap-4">
                                    <div className="w-10 h-10 bg-gray-800 rounded-xl flex items-center justify-center font-bold text-xs uppercase">
                                        {item.category ? item.category[0] : "?"}
                                    </div>
                                    <div>
                                        <h4 className="text-sm font-medium group-hover:text-blue-400 transition-colors line-clamp-1">{item.title}</h4>
                                        <div className="flex items-center gap-2 mt-1">
                                            <span className="text-[10px] text-gray-500 uppercase tracking-tighter">{item.category}</span>
                                            <span className="text-[10px] text-gray-400 font-mono">• {item.date}</span>
                                        </div>
                                    </div>
                                </div>
                                <div className="flex items-center gap-6">
                                    <div className="text-right hidden sm:block">
                                        <p className="text-xs font-mono text-green-500">{((item.confidence_score ?? item.score ?? 0) * 100).toFixed(0)}%</p>
                                        <p className="text-[10px] text-gray-500 uppercase">Confidence</p>
                                    </div>
                                    {expandedIdx === idx ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                                </div>
                            </div>
                            
                            {expandedIdx === idx && (
                                <div className="px-6 pb-6 pt-4 border-t border-gray-800/50 bg-[#121212]">
                                    <div className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap">
                                        {item.content}
                                    </div>
                                    
                                    {item.concepts && (
                                        <div className="mt-4 flex flex-wrap gap-2">
                                            {(Array.isArray(item.concepts) ? item.concepts : String(item.concepts).split(',')).map((c: string, i: number) => (
                                                <span key={i} className="px-2 py-1 bg-gray-800/50 border border-gray-700 text-gray-400 rounded-lg text-[10px] font-mono">
                                                    {c.trim()}
                                                </span>
                                            ))}
                                        </div>
                                    )}
                                    
                                    {item.url && (
                                        <div className="mt-4 pt-4 border-t border-gray-800/30">
                                            <a href={item.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 transition-colors">
                                                <ExternalLink size={14} />
                                                Fuente Original
                                            </a>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    ))
                )}
            </div>
        </div>
    );
}
