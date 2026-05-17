"use client";

import { apiFetch } from "@/lib/api";
import { SlidersHorizontal, RefreshCw } from "lucide-react";
import React, { useCallback, useEffect, useState } from "react";

type FeatureKey = "distillation" | "self_evolution" | "proactive" | "swarm_research";

const LABELS: Record<FeatureKey, { title: string; hint: string }> = {
    distillation: {
        title: "Destilación automática",
        hint: "Scheduler nocturno y destilación paralela al guardar conocimiento. Las sesiones manuales desde API siguen disponibles.",
    },
    self_evolution: {
        title: "Auto-evolución programada",
        hint: "Ciclos periódicos de introspección y vigilancia tecnológica. Los análisis manuales desde el panel de evolución no se bloquean.",
    },
    proactive: {
        title: "Sistema proactivo",
        hint: "Briefings, curiosidad (Thinker) y chequeos que usan el LLM en segundo plano. Telegram sigue recibiendo mensajes.",
    },
    swarm_research: {
        title: "Investigación autónoma en cola",
        hint: "Encadenado automático (exploración profunda, etc.). Tus investigaciones iniciadas desde la UI o «investiga» siguen funcionando.",
    },
};

interface TtsStatus {
    ready: boolean;
    current_voice: string;
    engine: string;
    piper_voices: string[];
    edge_voices: string[];
}

export default function ControlPanel() {
    const [features, setFeatures] = useState<Record<FeatureKey, boolean> | null>(null);
    const [ttsStatus, setTtsStatus] = useState<TtsStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        setError(null);
        setLoading(true);
        try {
            const [sysRes, ttsRes] = await Promise.all([
                apiFetch("/system/features"),
                apiFetch("/tts/status")
            ]);
            
            if (!sysRes.ok) throw new Error(`HTTP ${sysRes.status}`);
            
            const sysData = await sysRes.json();
            setFeatures(sysData.features as Record<FeatureKey, boolean>);

            if (ttsRes.ok) {
                const ttsData = await ttsRes.json();
                setTtsStatus(ttsData as TtsStatus);
            }
        } catch (e: unknown) {
            setFeatures(null);
            setError(e instanceof Error ? e.message : "Error al cargar");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    const patchFlag = async (key: FeatureKey, value: boolean) => {
        if (!features) return;
        setSaving(true);
        setError(null);
        try {
            const res = await apiFetch("/system/features", {
                method: "PUT",
                json: { [key]: value },
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            setFeatures(data.features as Record<FeatureKey, boolean>);
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : "Error al guardar");
        } finally {
            setSaving(false);
        }
    };

    const preset = async (name: "focus" | "full") => {
        setSaving(true);
        setError(null);
        try {
            const res = await apiFetch(`/system/features/preset/${name}`, { method: "POST", json: {} });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            setFeatures(data.features as Record<FeatureKey, boolean>);
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : "Error al aplicar preset");
        } finally {
            setSaving(false);
        }
    };

    const changeVoice = async (voice: string) => {
        setSaving(true);
        setError(null);
        try {
            const res = await apiFetch("/tts/voice", {
                method: "POST",
                json: { voice },
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            // Reload TTS status to reflect changes
            const ttsRes = await apiFetch("/tts/status");
            if (ttsRes.ok) {
                const ttsData = await ttsRes.json();
                setTtsStatus(ttsData as TtsStatus);
            }
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : "Error al cambiar voz");
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="max-w-2xl mx-auto space-y-8 py-6 px-2">
            <div className="flex items-start justify-between gap-4 flex-wrap">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center">
                        <SlidersHorizontal className="w-5 h-5 text-indigo-400" />
                    </div>
                    <div>
                        <h2 className="text-lg font-bold text-white">Panel de control</h2>
                        <p className="text-sm text-gray-500 mt-0.5">
                            Activa o pausa procesos autónomos para priorizar chat, voz y Ollama.
                        </p>
                    </div>
                </div>
                <button
                    type="button"
                    onClick={() => load()}
                    disabled={loading}
                    className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-gray-300 text-sm hover:bg-gray-750 disabled:opacity-50"
                >
                    <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
                    Actualizar
                </button>
            </div>

            {error && (
                <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-300 text-sm">{error}</div>
            )}

            <div className="flex flex-wrap gap-2">
                <button
                    type="button"
                    disabled={saving}
                    onClick={() => preset("focus")}
                    className="px-4 py-2 rounded-xl bg-amber-600/20 border border-amber-500/40 text-amber-200 text-sm font-medium hover:bg-amber-600/30 disabled:opacity-50"
                >
                    Modo piloto (solo interacción)
                </button>
                <button
                    type="button"
                    disabled={saving}
                    onClick={() => preset("full")}
                    className="px-4 py-2 rounded-xl bg-emerald-600/20 border border-emerald-500/40 text-emerald-200 text-sm font-medium hover:bg-emerald-600/30 disabled:opacity-50"
                >
                    Autonomía completa
                </button>
            </div>

            {loading && !features ? (
                <p className="text-gray-500 text-sm">Cargando estado…</p>
            ) : features ? (
                <ul className="space-y-3">
                    {(Object.keys(LABELS) as FeatureKey[]).map((key) => (
                        <li
                            key={key}
                            className="flex items-start justify-between gap-4 p-4 rounded-2xl bg-[#141414] border border-gray-800/80"
                        >
                            <div className="min-w-0">
                                <p className="text-sm font-semibold text-gray-200">{LABELS[key].title}</p>
                                <p className="text-xs text-gray-500 mt-1 leading-relaxed">{LABELS[key].hint}</p>
                            </div>
                            <button
                                type="button"
                                aria-label={LABELS[key].title}
                                title={`Alternar ${LABELS[key].title}`}
                                disabled={saving}
                                onClick={() => patchFlag(key, !features[key])}
                                className={`shrink-0 relative w-12 h-7 rounded-full transition-colors ${
                                    features[key] ? "bg-blue-600" : "bg-gray-700"
                                } disabled:opacity-50`}
                            >
                                <span
                                    className={`absolute top-1 left-1 w-5 h-5 rounded-full bg-white shadow transition-transform ${
                                        features[key] ? "translate-x-5" : "translate-x-0"
                                    }`}
                                />
                            </button>
                        </li>
                    ))}
                </ul>
            ) : null}

            {/* Selector de Voz */}
            {ttsStatus && (
                <div className="mt-8 p-4 rounded-2xl bg-[#141414] border border-gray-800/80">
                    <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0 flex-1">
                            <p className="text-sm font-semibold text-gray-200">🗣️ Motor de Síntesis de Voz</p>
                            <p className="text-xs text-gray-500 mt-1 leading-relaxed">
                                Selecciona el motor de voz de NOVA. Las voces <strong>Offline</strong> son privadas y usan tu CPU. Las voces <strong>Premium Nube</strong> usan internet y ofrecen fluidez máxima (estilo Alexa).
                            </p>
                            
                            <div className="mt-4 flex flex-col sm:flex-row gap-3 items-start sm:items-center">
                                <select 
                                    className="bg-gray-800 border border-gray-700 text-white text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full sm:w-auto p-2.5 outline-none"
                                    value={ttsStatus.current_voice}
                                    disabled={saving}
                                    onChange={(e) => changeVoice(e.target.value)}
                                    aria-label="Motor de Síntesis de Voz"
                                    title="Seleccionar Motor de Voz"
                                >
                                    <optgroup label="🌐 Premium Nube (Edge-TTS)">
                                        {ttsStatus.edge_voices?.map(v => (
                                            <option key={v} value={v}>{v}</option>
                                        ))}
                                    </optgroup>
                                    <optgroup label="🔒 Local Offline (Piper)">
                                        {ttsStatus.piper_voices?.map(v => (
                                            <option key={v} value={v}>{v}</option>
                                        ))}
                                    </optgroup>
                                </select>
                                
                                {ttsStatus.engine === "edge-tts" ? (
                                    <span className="px-2 py-1 bg-purple-500/20 text-purple-300 text-xs rounded-md border border-purple-500/30">Nube / Online</span>
                                ) : (
                                    <span className="px-2 py-1 bg-green-500/20 text-green-300 text-xs rounded-md border border-green-500/30">Local / Privado</span>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            )}

            <p className="text-[11px] text-gray-600 leading-relaxed">
                Los cambios se guardan en la base de datos local y se aplican de inmediato. El monitor de salud, la cola de
                proyectos y el chat no se desactivan desde aquí.
            </p>
        </div>
    );
}
