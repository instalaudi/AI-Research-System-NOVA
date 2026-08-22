"use client";

import React, { useState, useRef, useEffect } from "react";
import { Volume2, VolumeX, Play, Square, Loader2 } from "lucide-react";
import { apiFetch } from "@/lib/api";

interface AudioStreamPlayerProps {
    text?: string;
    autoPlay?: boolean;
    onPlaybackEnded?: () => void;
    className?: string;
}

export default function AudioStreamPlayer({
    text,
    autoPlay = false,
    onPlaybackEnded,
    className = "",
}: AudioStreamPlayerProps) {
    const [isPlaying, setIsPlaying] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [isMuted, setIsMuted] = useState(false);
    
    const audioRef = useRef<HTMLAudioElement | null>(null);
    const abortControllerRef = useRef<AbortController | null>(null);

    useEffect(() => {
        if (autoPlay && text) {
            playStream(text);
        }
        return () => {
            stopPlayback();
        };
    }, [text, autoPlay]);

    const playStream = async (textToSpeak: string) => {
        if (!textToSpeak.trim()) return;

        stopPlayback();
        setIsLoading(true);

        try {
            abortControllerRef.current = new AbortController();
            
            let response = await apiFetch("/tts/stream", {
                method: "POST",
                json: { text: textToSpeak, speed: 1.0 },
                signal: abortControllerRef.current.signal,
            });

            if (!response.ok) {
                // Fallback a endpoint estándar si streaming falla
                response = await apiFetch("/tts", {
                    method: "POST",
                    json: { text: textToSpeak, speed: 1.0 },
                    signal: abortControllerRef.current.signal,
                });
            }

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const arrayBuffer = await response.arrayBuffer();
            if (!arrayBuffer || arrayBuffer.byteLength < 44) {
                // Buffer vacío o menor al header mínimo WAV
                console.warn("[AudioStreamPlayer] Audio buffer recibido está vacío.");
                return;
            }

            const blob = new Blob([arrayBuffer], { type: "audio/wav" });
            const blobUrl = URL.createObjectURL(blob);

            if (audioRef.current) {
                audioRef.current.src = blobUrl;
                audioRef.current.muted = isMuted;
                try {
                    await audioRef.current.play();
                    setIsPlaying(true);
                } catch (playErr: any) {
                    if (playErr.name !== "AbortError") {
                        console.warn("[AudioStreamPlayer] Playback no pudo iniciar:", playErr.message);
                    }
                }
            }
        } catch (err: any) {
            if (err.name !== "AbortError") {
                console.warn("[AudioStreamPlayer] Error streaming audio:", err.message || err);
            }
        } finally {
            setIsLoading(false);
        }

    };

    const stopPlayback = () => {
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
            abortControllerRef.current = null;
        }
        if (audioRef.current) {
            audioRef.current.pause();
            audioRef.current.currentTime = 0;
        }
        setIsPlaying(false);
        setIsLoading(false);
    };

    const togglePlay = () => {
        if (isPlaying) {
            stopPlayback();
        } else if (text) {
            playStream(text);
        }
    };

    const toggleMute = () => {
        const nextMuted = !isMuted;
        setIsMuted(nextMuted);
        if (audioRef.current) {
            audioRef.current.muted = nextMuted;
        }
    };

    return (
        <div className={`flex items-center gap-2 p-2 bg-[#181818] border border-gray-800 rounded-lg ${className}`}>
            <audio
                ref={audioRef}
                onEnded={() => {
                    setIsPlaying(false);
                    onPlaybackEnded?.();
                }}
            />

            <button
                onClick={togglePlay}
                disabled={isLoading || !text}
                className="p-2 text-gray-300 hover:text-white bg-gray-800/60 hover:bg-gray-700/60 rounded-md transition-colors"
                title={isPlaying ? "Detener voz" : "Escuchar respuesta"}
            >
                {isLoading ? (
                    <Loader2 size={16} className="animate-spin text-blue-400" />
                ) : isPlaying ? (
                    <Square size={16} className="text-red-400 fill-current" />
                ) : (
                    <Play size={16} className="text-blue-400 fill-current" />
                )}
            </button>

            <button
                onClick={toggleMute}
                className="p-2 text-gray-400 hover:text-gray-200 transition-colors"
                title={isMuted ? "Activar audio" : "Silenciar"}
            >
                {isMuted ? <VolumeX size={16} /> : <Volume2 size={16} />}
            </button>

            {isPlaying && (
                <div className="flex items-center gap-1 px-2">
                    <span className="w-1 h-3 bg-blue-500 rounded-full animate-bounce [animation-delay:-0.3s]" />
                    <span className="w-1 h-4 bg-blue-400 rounded-full animate-bounce [animation-delay:-0.15s]" />
                    <span className="w-1 h-2 bg-blue-600 rounded-full animate-bounce" />
                </div>
            )}
        </div>
    );
}
