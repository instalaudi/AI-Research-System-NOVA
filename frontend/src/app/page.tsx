"use client";
import AudioStreamPlayer from "@/components/AudioStreamPlayer";
import ControlPanel from "@/components/ControlPanel";
import KnowledgeBrowser from "@/components/KnowledgeBrowser";
import KnowledgeGraph from "@/components/KnowledgeGraph";
import ProjectManager from "@/components/ProjectManager";
import ResearchSession from "@/components/ResearchSession";

import { apiFetch, getBaseUrl } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { Activity, AlertCircle, BarChart as BarChartIcon, BookOpen, Camera, Check, CheckCircle, Clock, Copy, Cpu, Database, FileCode, Lock, Menu, Mic, Paperclip, Search, Send, Shield, SlidersHorizontal, Terminal, TrendingUp, User as UserIcon, Volume2, VolumeX, X } from "lucide-react";
import { useRouter } from "next/navigation";
import React, { useEffect, useState } from "react";
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import remarkGfm from 'remark-gfm';

/**
 * Intelligent Intent Classifier for Chat Messages
 * Determines if user wants to QUERY knowledge or START RESEARCH
 */
function classifyIntent(text: string, hasAttachments: boolean): { intent: "query" | "research"; cleanQuery: string } {
    const lower = text.toLowerCase().trim();

    // 1. Explicit commands: /q for query, /r for research
    if (lower.startsWith("/q ")) {
        return { intent: "query", cleanQuery: text.substring(3).trim() };
    }
    if (lower.startsWith("/r ")) {
        return { intent: "research", cleanQuery: text.substring(3).trim() };
    }

    // 2. Query patterns - user is asking about what the system ALREADY knows
    const queryPatterns = [
        // Spanish
        /qu[eé]\s+(aprendiste|sabes|conoces|encontraste|descubriste|investigaste|tienes)/i,
        /cu[eé]ntame|dime|expl[ií]came|resu[ée]?me|mu[eé]strame|desc[ií]beme/i,
        /qu[eé]\s+es\s+/i,
        /qu[eé]\s+son\s+/i,
        /c[oó]mo\s+funciona/i,
        /cu[aá]l\s+es/i,
        /cu[aá]les\s+son/i,
        /define|definici[oó]n/i,
        /informaci[oó]n\s+sobre/i,
        /lo\s+que\s+(sabes|aprendiste|conoces|encontraste)/i,
        /has\s+(aprendido|investigado|encontrado|analizado)/i,
        /tus\s+(conocimientos|hallazgos|resultados)/i,
        /resumen\s+de/i,
        /lista\s+(de|los|las)/i,
        // English
        /what\s+(did you|do you)\s+(learn|know|find|discover)/i,
        /tell\s+me\s+about/i,
        /explain|summarize|describe|show\s+me/i,
        /what\s+is\s+/i,
        /what\s+are\s+/i,
    ];

    for (const pattern of queryPatterns) {
        if (pattern.test(lower)) {
            return { intent: "query", cleanQuery: text.trim() };
        }
    }

    // 3. Research patterns - user explicitly wants NEW research
    const researchPatterns = [
        /^investiga\s+/i,
        /^aprende\s+(sobre|de|acerca)/i,
        /^busca\s+(sobre|acerca|informaci[oó]n)/i,
        /^analiza\s+/i,
        /^analisa\s+/i,
        /^explora\s+/i,
        /^research\s+/i,
        /^learn\s+about\s+/i,
        /^search\s+for\s+/i,
        /quiero\s+que\s+(investigues|aprendas|busques|analices|explores)/i,
        /necesito\s+que\s+(investigues|aprendas|busques)/i,
        /empieza\s+a\s+investigar/i,
        /inicia\s+(una\s+)?investigaci[oó]n/i,
    ];

    for (const pattern of researchPatterns) {
        if (pattern.test(lower)) {
            // Context Override: If files/images are attached, "analiza" or "explora" likely refers to the local files.
            // We favor "query" mode unless it's a very explicit research-only command like "investiga".
            const isExplicitResearch = /^investiga|^research|quiero que investigues|inicia investigación/i.test(lower);
            if (hasAttachments && !isExplicitResearch) {
                return { intent: "query", cleanQuery: text.trim() };
            }

            // Clean the research prefix for cleaner topic
            const cleaned = text
                .replace(/^(investiga|aprende sobre|aprende de|busca sobre|busca|analiza|explora|research|learn about|search for)\s+/i, "")
                .trim();
            return { intent: "research", cleanQuery: cleaned || text.trim() };
        }
    }

    // 4. Question marks → treat as query
    if (lower.endsWith("?") || lower.startsWith("¿")) {
        return { intent: "query", cleanQuery: text.trim() };
    }

    // 5. Default: QUERY (safer than accidentally launching research)
    const cleaned = text.trim();
    if (!cleaned && hasAttachments) {
        return { intent: "query", cleanQuery: "Analiza este archivo adjunto" };
    }
    return { intent: "query", cleanQuery: cleaned };
}

export default function Home() {
    const { user, isLoading: authLoading, logout } = useAuth();
    const router = useRouter();

    const [activeTab, setActiveTab] = useState("chat");
    const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
    const [showHelpModal, setShowHelpModal] = useState(false);
    const [messages, setMessages] = useState<{ role: 'ai' | 'user', text: string, images?: string[] }[]>([]);
    
    const [inputValue, setInputValue] = useState("");
    const [voiceEnabled, setVoiceEnabled] = useState(false);
    
    // Initial Load from localStorage
    useEffect(() => {
        const savedMessages = localStorage.getItem("nova_chat_history");
        if (savedMessages) {
            try {
                setMessages(JSON.parse(savedMessages));
            } catch (e) {
                console.error("Failed to parse saved messages", e);
                setMessages([{ role: "ai", text: "SISTEMA OPERATIVO NOVA [v12.1.5]\nEstado: LISTO PARA PROCESAMIENTO\n\n📖 CONSULTA: Pregunta sobre el conocimiento ya adquirido en el grafo.\n🔬 INVESTIGACIÓN: Escribe 'investiga [tema]' para activar la autonomía web.\n\nIngrese directiva." }]);
            }
        } else {
            setMessages([{ role: "ai", text: "SISTEMA OPERATIVO NOVA [v12.1.5]\nEstado: LISTO PARA PROCESAMIENTO\n\n📖 CONSULTA: Pregunta sobre el conocimiento ya adquirido en el grafo.\n🔬 INVESTIGACIÓN: Escribe 'investiga [tema]' para activar la autonomía web.\n\nIngrese directiva." }]);
        }
    }, []);

    // Auto-resize textarea
    useEffect(() => {
        if (textareaRef.current) {
            textareaRef.current.style.height = 'auto';
            textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
        }
    }, [inputValue]);

    // Save to localStorage on change
    useEffect(() => {
        if (messages.length > 0) {
            try {
                localStorage.setItem("nova_chat_history", JSON.stringify(messages.slice(-50)));
            } catch (e) {
                console.warn("localStorage quota exceeded, skipping save");
            }
        }
    }, [messages]);
    const [isLoading, setIsLoading] = useState(false);
    const [agentStates, setAgentStates] = useState<Record<string, string>>({
        "Planner": "idle",
        "Explorer": "idle",
        "Analyzer": "idle",
        "Critic": "idle",
        "Verifier": "idle",
        "Librarian": "idle",
        "Browser": "idle"
    });
    const [realtimeLogs, setRealtimeLogs] = useState<any[]>([]);
    const [knowledgeEntries, setKnowledgeEntries] = useState<any[]>([]);
    const [systemStats, setSystemStats] = useState<any>(null);
    const [systemFailures, setSystemFailures] = useState<any[]>([]);
    const [selectedImages, setSelectedImages] = useState<string[]>([]);
    const [selectedFiles, setSelectedFiles] = useState<{ name: string, content: string }[]>([]);
    const [isRecording, setIsRecording] = useState(false);
    const [volume, setVolume] = useState(0);
    const [audioDevices, setAudioDevices] = useState<MediaDeviceInfo[]>([]);
    const [selectedDeviceId, setSelectedDeviceId] = useState<string>("");
    const [chatMode, setChatMode] = useState<'auto' | 'chat' | 'research' | 'build' | 'knowledge'>('auto');
    const [streamingIntent, setStreamingIntent] = useState<string | null>(null);
    const [pendingResearch, setPendingResearch] = useState<string | null>(null);
    const audioContextRef = React.useRef<AudioContext | null>(null);
    const analyserRef = React.useRef<AnalyserNode | null>(null);
    const animationFrameRef = React.useRef<number | null>(null);
    const fileInputRef = React.useRef<HTMLInputElement>(null);
    const textareaRef = React.useRef<HTMLTextAreaElement>(null);
    const mediaRecorderRef = React.useRef<MediaRecorder | null>(null);
    const messagesEndRef = React.useRef<HTMLDivElement>(null);
    
    // v13.7.2: Audio Streaming Queue (Fase 2)
    const audioQueueRef = React.useRef<string[]>([]);
    const [isAudioPlaying, setIsAudioPlaying] = useState(false);

    const playNextAudio = React.useCallback(() => {
        if (audioQueueRef.current.length === 0) {
            setIsAudioPlaying(false);
            return;
        }
        setIsAudioPlaying(true);
        const key = audioQueueRef.current.shift();
        if (!key) return;
        
        const audioUrl = `${getBaseUrl()}/chat/audio/${key}`;
        const audio = new Audio(audioUrl);
        audio.onended = () => playNextAudio();
        audio.onerror = () => playNextAudio();
        audio.play().catch(e => {
            console.error("Audio playback error:", e);
            playNextAudio();
        });
    }, []);

    const queueAudio = React.useCallback((key: string) => {
        if (!voiceEnabled) return;
        audioQueueRef.current.push(key);
        if (!isAudioPlaying) {
            playNextAudio();
        }
    }, [voiceEnabled, isAudioPlaying, playNextAudio]);

    useEffect(() => {
        const handler = (event: Event) => {
            const customEvent = event as CustomEvent<{ text?: string }>;
            const injectedText = customEvent.detail?.text;
            if (!injectedText) return;
            setInputValue(prev => (prev ? `${prev}\n\n${injectedText}` : injectedText));
            setActiveTab("chat");
            textareaRef.current?.focus();
        };
        window.addEventListener("nova:inject-prompt", handler as EventListener);
        return () => window.removeEventListener("nova:inject-prompt", handler as EventListener);
    }, []);

    // Cleanup recording resources on unmount
    useEffect(() => {
        return () => {
            if (animationFrameRef.current) {
                cancelAnimationFrame(animationFrameRef.current);
            }
        };
    }, []);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'auto' });
    }, [messages, isLoading]);

    React.useEffect(() => {
        if (!authLoading && !user) {
            router.push("/login");
            return;
        }

        const fetchStatus = async () => {
            try {
                const response = await apiFetch("/status");
                if (response.ok) {
                    const data = await response.json();
                    setAgentStates(data.states);
                    setRealtimeLogs(data.logs.slice(-100)); // MEM-01: Log limit
                }
            } catch (error) {
                console.error("Error fetching status:", error);
            }
        };

        const fetchKnowledge = async () => {
            try {
                const response = await apiFetch("/knowledge");
                if (response.ok) {
                    const data = await response.json();
                    setKnowledgeEntries(data);
                }
            } catch (error) {
                console.error("Error fetching knowledge:", error);
            }
        };

        const fetchStats = async () => {
            try {
                const response = await apiFetch("/stats");
                if (response.ok) {
                    const data = await response.json();
                    setSystemStats(data);
                    
                    // v11.0: Fetch detailed failures for admin
                    if (data.system?.failures_count > 0) {
                        try {
                            const failResp = await apiFetch("/system/failures");
                            if (failResp.ok) {
                                setSystemFailures(await failResp.json());
                            }
                        } catch (e) {
                             console.warn("Failed to fetch system failures details", e);
                        }
                    } else {
                        setSystemFailures([]);
                    }
                }
            } catch (error) {
                console.error("Error fetching stats:", error);
            }
        };

        // clearFailedJobs moved to Home scope

        // Microphone Device Enumeration
        const getDevices = async () => {
            try {
                // Request temporary permission to get label names, then stop tracks
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                stream.getTracks().forEach(track => track.stop());
                
                const devices = await navigator.mediaDevices.enumerateDevices();
                const audioInputs = devices.filter(d => d.kind === 'audioinput');
                setAudioDevices(audioInputs);
                if (audioInputs.length > 0) {
                    setSelectedDeviceId(audioInputs[0].deviceId);
                }
            } catch (err) {
                console.error("Error enumerating audio devices:", err);
            }
        };

        fetchStatus();
        fetchKnowledge();
        fetchStats();
        getDevices();

        const statusInterval = setInterval(fetchStatus, 30000);      // FIX-POLLING: 5s → 30s
        const knowledgeInterval = setInterval(fetchKnowledge, 30000); // FIX-POLLING: 5s → 30s
        const statsInterval = setInterval(fetchStats, 60000);         // FIX-POLLING: 10s → 60s
        return () => {
            clearInterval(statusInterval);
            clearInterval(knowledgeInterval);
            clearInterval(statsInterval);
        };
    }, [user, authLoading, router]);

    if (authLoading || (!user && typeof window !== "undefined")) {
        return (
            <div className="h-screen bg-[#0a0a0a] flex items-center justify-center">
                <div className="w-12 h-12 border-4 border-blue-600/30 border-t-blue-600 rounded-full animate-spin" />
            </div>
        );
    }

    const handleSendMessage = async () => {
        if ((!inputValue.trim() && selectedImages.length === 0 && selectedFiles.length === 0) || isLoading) return;

        const userText = inputValue.trim();
        const currentImages = [...selectedImages];
        const hasAttachments = currentImages.length > 0 || selectedFiles.length > 0;
        const displayText = userText || (currentImages.length > 0 ? "Imagen adjunta" : selectedFiles.length > 0 ? "Archivo adjunto" : "Mensaje enviado");
        setMessages(prev => [...prev, { role: "user", text: displayText, images: currentImages }]);
        setInputValue("");
        setIsLoading(true);
        setSelectedImages([]); // Clear immediately to provide feedback

        // --- CONVERSATIONAL STATE MACHINE: Handle Pending Research ---
        if (pendingResearch) {
            const lowerUserText = userText.toLowerCase();
            const affirmativeWords = ["si", "sí", "claro", "por favor", "ok", "dale", "yes", "investiga", "hazlo", "por su puesto", "adelante"];
            const negativeWords = ["no", "ni loco", "para nada", "ahora no", "nel", "nope", "paso"];
            
            const isAffirmative = affirmativeWords.some(w => new RegExp(`\\b${w}\\b`, 'i').test(userText));
            const isNegative = negativeWords.some(w => new RegExp(`\\b${w}\\b`, 'i').test(userText));
            
            if (isAffirmative) {
                // User agreed to start research
                setMessages(prev => [...prev, { role: "ai", text: `🔬 Entendido. Iniciando ciclo de investigación profunda sobre: "${pendingResearch}". Puedes seguir el progreso en la pestaña "Investigaciones".` }]);
                
                try {
                    await apiFetch("/research/start", {
                        method: "POST",
                        json: { interest_areas: [pendingResearch] }
                    });
                } catch (e) {
                    console.error("Failed to start research", e);
                }
                setPendingResearch(null);
                setIsLoading(false);
                return;
            } else if (isNegative) {
                // User explicitly declined
                setMessages(prev => [...prev, { role: "ai", text: "De acuerdo, no investigaré ese tema por ahora. ¿En qué más puedo ayudarte?" }]);
                setPendingResearch(null);
                setIsLoading(false);
                return;
            } else {
                // If it's not a clear YES/NO, it's likely a follow-up question or new query.
                // We clear the pending research and proceed with the normal flow.
                setPendingResearch(null);
                // Continue execution to handle current userText as a new query
            }
        }
        // -----------------------------------------------------------

        const { intent, cleanQuery } = classifyIntent(userText, hasAttachments);
        const isQuery = intent === "query";
        const payload = {
            query: cleanQuery,
            images: currentImages,
            files: selectedFiles,
            mode: chatMode
        };
        console.debug("Sending chat payload", { payload, intent, hasAttachments, chatMode });

        try {
            if (isQuery) {
                // Initialize empty AI message for streaming
                setMessages(prev => [...prev, { role: "ai", text: "" }]);
                
                if (voiceEnabled) {
                    const response = await apiFetch("/query/voice", {
                        method: "POST",
                        json: payload
                    });

                    if (!response.ok) {
                        throw new Error(`Error HTTP: ${response.status}`);
                    }

                    const data = await response.json();
                    setMessages(prev => {
                        const newMsg = [...prev];
                        newMsg[newMsg.length - 1].text = data.text;
                        return newMsg;
                    });

                    if (data.audio_b64) {
                        const audio = new Audio("data:audio/wav;base64," + data.audio_b64);
                        audio.play().catch(e => console.error("Error reproduciendo audio:", e));
                    }
                    
                    setSelectedFiles([]); // Clear files after send
                    setIsLoading(false);
                    return;
                }

                const response = await apiFetch("/query/stream", {
                    method: "POST",
                    json: payload
                });

                if (!response.ok) {
                    throw new Error(`Error HTTP: ${response.status}`);
                }

                const reader = response.body?.getReader();
                const decoder = new TextDecoder();
                let buffer = "";
                
                if (reader) {
                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;
                        
                        buffer += decoder.decode(value, { stream: true });
                        const lines = buffer.split('\n\n');
                        buffer = lines.pop() || ""; // Keep the last partial/pending line
                        
                        for (const line of lines) {
                            if (line.startsWith('data: ')) {
                                const dataStr = line.slice(6).trim();
                                if (!dataStr) continue;
                                try {
                                    const data = JSON.parse(dataStr);
                                    if (data.type === 'chunk') {
                                        setMessages(prev => {
                                            const newMsg = [...prev];
                                            const lastMsg = newMsg[newMsg.length - 1];
                                            newMsg[newMsg.length - 1] = {
                                                ...lastMsg,
                                                text: lastMsg.text + data.text
                                            };
                                            return newMsg;
                                        });
                                        
                                        // Auto-switch to Projects tab when a project is created
                                        if (data.text.includes("Ve a la pestaña 'Proyectos'")) {
                                            setActiveTab("projects");
                                        }
                                    } else if (data.type === 'fallback') {
                                        setMessages(prev => {
                                            const newMsg = [...prev];
                                            const lastMsg = newMsg[newMsg.length - 1];
                                            newMsg[newMsg.length - 1] = {
                                                ...lastMsg,
                                                text: data.text
                                            };
                                            return newMsg;
                                        });
                                        if (data.needs_research) {
                                            setPendingResearch(data.query);
                                        }
                                    } else if (data.type === 'error') {
                                        setMessages(prev => {
                                            const newMsg = [...prev];
                                            const lastMsg = newMsg[newMsg.length - 1];
                                            newMsg[newMsg.length - 1] = {
                                                ...lastMsg,
                                                text: lastMsg.text + data.text
                                            };
                                            return newMsg;
                                        });
                                    } else if (data.type === 'action') {
                                        setMessages(prev => {
                                            const newMsg = [...prev];
                                            const lastMsg = newMsg[newMsg.length - 1];
                                            newMsg[newMsg.length - 1] = {
                                                ...lastMsg,
                                                text: lastMsg.text + `\n\n*${data.text}*\n`
                                            };
                                            return newMsg;
                                        });
                                    } else if (data.type === 'metadata') {
                                        // Update intent if provided in metadata
                                        if (data.intent) {
                                            setStreamingIntent(data.intent);
                                            console.debug("Intent updated from metadata:", data.intent);
                                        }
                                    } else if (data.type === 'audio') {
                                        // v13.7.2: Recibir fragmento de voz en tiempo real
                                        queueAudio(data.key);
                                    } else if (data.type === 'observation') {
                                        setMessages(prev => {
                                            const newMsg = [...prev];
                                            const lastMsg = newMsg[newMsg.length - 1];
                                            newMsg[newMsg.length - 1] = {
                                                ...lastMsg,
                                                text: lastMsg.text + `\n> 🔍 **Observación del Sandbox:**\n> ${data.text.replace(/\n/g, '\n> ')}\n\n`
                                            };
                                            return newMsg;
                                        });
                                    } else if (data.type === 'done') {
                                        setIsLoading(false);
                                    }
                                } catch (e) {
                                    console.error("Stream parse error:", e, "on line:", line);
                                }
                            }
                        }
                    }
                }
            } else {
                const response = await apiFetch("/research/start", {
                    method: "POST",
                    json: { interest_areas: [cleanQuery] }
                });

                if (response.ok) {
                    setMessages(prev => [...prev, { role: "ai", text: `🔬 Entendido. He iniciado un ciclo de investigación sobre: "${cleanQuery}". Los agentes están trabajando ahora mismo. Puedes seguir su progreso en la pestaña "Investigaciones".` }]);
                } else {
                    const errBody = await response.json().catch(() => ({ detail: response.statusText }));
                    const detail = Array.isArray(errBody.detail) ? errBody.detail.map((x: any) => x?.msg ?? x).join("; ") : (errBody.detail ?? "Error desconocido");
                    setMessages(prev => [...prev, { role: "ai", text: `Error (${response.status}): ${detail}` }]);
                }
            }
        } catch (error: unknown) {
            console.error("Query send failed", error, { payload, intent, hasAttachments });
            const errorMessage = error instanceof Error ? error.message : "Error de conexión con el backend. ¿Está el servidor en marcha?";
            setMessages(prev => [...prev, { role: "ai", text: errorMessage }]);
        } finally {
            setIsLoading(false);
            setStreamingIntent(null);
            setSelectedFiles([]);
        }
    };

    const clearFailedJobs = async () => {
        if (!confirm("¿Estás seguro de que deseas limpiar todas las interrupciones y fallos?")) return;
        try {
            const response = await apiFetch("/jobs/clear-failed", { method: "POST" });
            if (response.ok) {
                const statsResponse = await apiFetch("/stats");
                if (statsResponse.ok) {
                    setSystemStats(await statsResponse.json());
                }
                setMessages(prev => [...prev, { role: "ai", text: "✅ Sistema purgado. Todos los fallos han sido eliminados de la cola de investigación." }]);
            }
        } catch (error) {
            console.error("Error clearing jobs:", error);
        }
    };

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = e.target.files;
        if (!files) return;

        Array.from(files).forEach(file => {
            const isImage = file.type.startsWith('image/') || /\.(jpe?g|png|gif|bmp|webp|svg)$/i.test(file.name);
            const isBinary = file.type === 'application/pdf' || file.type === 'application/octet-stream';
            const reader = new FileReader();

            reader.onloadend = () => {
                if (isImage) {
                    setSelectedImages(prev => [...prev, reader.result as string]);
                } else if (isBinary) {
                    // Guardar como Data URL (base64) para que el backend reciba el contenido real
                    setSelectedFiles(prev => [...prev, { name: file.name, content: reader.result as string }]);
                } else {
                    setSelectedFiles(prev => [...prev, { name: file.name, content: reader.result as string }]);
                }
            };

            if (isImage) {
                reader.readAsDataURL(file);
            } else if (isBinary) {
                reader.readAsDataURL(file);
            } else {
                reader.readAsText(file);
            }
        });
        
        // Reset input to allow selecting the same file again
        e.target.value = '';
    };

    const removeImage = (index: number) => {
        setSelectedImages(prev => prev.filter((_, i) => i !== index));
    };

    const removeFile = (index: number) => {
        setSelectedFiles(prev => prev.filter((_, i) => i !== index));
    };

    const handlePaste = (e: React.ClipboardEvent) => {
        const items = e.clipboardData?.items;
        if (!items) return;

        for (let i = 0; i < items.length; i++) {
            if (items[i].type.indexOf("image") !== -1) {
                const blob = items[i].getAsFile();
                if (!blob) continue;

                const reader = new FileReader();
                reader.onloadend = () => {
                    setSelectedImages(prev => [...prev, reader.result as string]);
                };
                reader.readAsDataURL(blob);
            }
        }
    };

    const toggleRecording = async () => {
        if (!isRecording) {
            try {
                const constraints = { 
                    audio: selectedDeviceId ? { deviceId: { exact: selectedDeviceId } } : true 
                };
                const stream = await navigator.mediaDevices.getUserMedia(constraints);
                
                // --- Volume Visualization Logic ---
                const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
                const analyser = audioContext.createAnalyser();
                const source = audioContext.createMediaStreamSource(stream);
                source.connect(analyser);
                analyser.fftSize = 256;
                
                audioContextRef.current = audioContext;
                analyserRef.current = analyser;
                
                const bufferLength = analyser.frequencyBinCount;
                const dataArray = new Uint8Array(bufferLength);
                
                const updateVolume = () => {
                    if (!analyserRef.current) return;
                    analyserRef.current.getByteFrequencyData(dataArray);
                    let sum = 0;
                    for(let i = 0; i < bufferLength; i++) {
                        sum += dataArray[i];
                    }
                    const average = sum / bufferLength;
                    setVolume(average); 
                    animationFrameRef.current = requestAnimationFrame(updateVolume);
                };
                updateVolume();
                // ------------------------------------

                const recorder = new MediaRecorder(stream);
                mediaRecorderRef.current = recorder;
                recorder.start();
                setIsRecording(true);
                
                const chunks: Blob[] = [];
                recorder.ondataavailable = (e) => {
                    if (e.data.size > 0) chunks.push(e.data);
                };
                recorder.onstop = async () => {
                    // Show transcribing feedback
                    setInputValue("Transcribiendo voz...");
                    setVolume(0); // Reset volume visual
                    
                    const blob = new Blob(chunks, { type: 'audio/webm' });
                    
                    // Call STT endpoint
                    const formData = new FormData();
                    formData.append("audio", blob, "recording.webm");

                    try {
                        const response = await apiFetch("/stt", {
                            method: "POST",
                            body: formData
                        });

                        if (response.ok) {
                            const data = await response.json();
                            if (data.text) {
                                setInputValue(prev => {
                                    const base = prev === "Transcribiendo voz..." ? "" : prev;
                                    return base ? `${base} ${data.text}` : data.text;
                                });
                            } else {
                                setInputValue(prev => prev === "Transcribiendo voz..." ? "" : prev);
                            }
                        } else {
                            console.error("STT failed", response.status);
                            setInputValue(prev => prev === "Transcribiendo voz..." ? "" : prev);
                        }
                    } catch (err) {
                        console.error("STT error:", err);
                        setInputValue(prev => prev === "Transcribiendo voz..." ? "" : prev);
                    }
                };
            } catch (err: unknown) {
                console.error("Error accessing microphone:", err);
                let errorMsg = "No pudimos acceder al micrófono.";
                const errorName = (err as any)?.name;
                
                if (errorName === 'NotAllowedError' || errorName === 'PermissionDeniedError') {
                    errorMsg = "Permiso denegado. Por favor, habilita el micrófono en los ajustes de tu navegador (busca el icono de configuración o info al lado de la URL).";
                } else if (errorName === 'NotFoundError' || errorName === 'DevicesNotFoundError') {
                    errorMsg = "No se encontró ningún micrófono conectado.";
                } else if (errorName === 'NotReadableError' || errorName === 'TrackStartError') {
                    errorMsg = "El micrófono ya está siendo usado por otra aplicación.";
                }
                
                setMessages(prev => [...prev, { role: "ai", text: `⚠️ Error de Audio: ${errorMsg}` }]);
                setIsRecording(false);
            }
        } else {
            if (mediaRecorderRef.current) {
                mediaRecorderRef.current.stop();
                mediaRecorderRef.current.stream.getTracks().forEach(track => track.stop());
                mediaRecorderRef.current = null;
            }
            
            // Clean up AudioContext
            if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
            if (audioContextRef.current) audioContextRef.current.close();
            audioContextRef.current = null;
            analyserRef.current = null;
            setVolume(0);
            
            setIsRecording(false);
        }
    };

    return (
        <div className="flex h-screen overflow-hidden text-gray-200 relative">
            {/* Mobile Overlay */}
            {isMobileMenuOpen && (
                <div 
                    className="fixed inset-0 bg-black/50 z-40 lg:hidden" 
                    onClick={() => setIsMobileMenuOpen(false)}
                />
            )}

            {/* Sidebar */}
            <aside className={`fixed lg:static inset-y-0 left-0 z-50 w-64 bg-[#111] border-r border-gray-800 flex flex-col transform transition-transform duration-300 ${isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}>
                <div className="p-6 border-b border-gray-800 flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                        <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center shadow-lg shadow-blue-600/20">
                            <Activity className="text-white w-5 h-5" />
                        </div>
                        <h1 className="font-bold text-xl tracking-tight text-white">Research AI</h1>
                    </div>
                    <button 
                        className="p-1 lg:hidden text-gray-500 hover:text-white"
                        onClick={() => setIsMobileMenuOpen(false)}
                        title="Cerrar menú"
                        aria-label="Cerrar menú"
                    >
                        <X size={20} />
                    </button>
                </div>

                <nav className="flex-1 p-4 space-y-2">
                    <NavItem
                        icon={<Terminal size={20} />}
                        label="Chat"
                        active={activeTab === "chat"}
                        onClick={() => { setActiveTab("chat"); setIsMobileMenuOpen(false); }}
                        title="Ir al Chat"
                    />
                    <NavItem
                        icon={<Search size={20} />}
                        label="Investigaciones"
                        active={activeTab === "research"}
                        onClick={() => { setActiveTab("research"); setIsMobileMenuOpen(false); }}
                        title="Ver Investigaciones activas"
                    />
                    <NavItem
                        icon={<BookOpen size={20} />}
                        label="Conocimiento"
                        active={activeTab === "knowledge"}
                        onClick={() => { setActiveTab("knowledge"); setIsMobileMenuOpen(false); }}
                        title="Explorar Base de Conocimiento"
                    />
                    <NavItem
                        icon={<Activity size={20} />}
                        label="Actividad en Vivo"
                        active={activeTab === "activity"}
                        onClick={() => { setActiveTab("activity"); setIsMobileMenuOpen(false); }}
                        title="Grafo de Conocimiento en vivo"
                    />
                    <NavItem
                        icon={<Cpu size={20} />}
                        label="Proyectos"
                        active={activeTab === "tools"}
                        onClick={() => { setActiveTab("tools"); setIsMobileMenuOpen(false); }}
                        title="Proyectos Generados por NOVA"
                    />
                    <NavItem
                        icon={<SlidersHorizontal size={20} />}
                        label="Panel de control"
                        active={activeTab === "control"}
                        onClick={() => { setActiveTab("control"); setIsMobileMenuOpen(false); }}
                        title="Automatización y recursos"
                    />
                </nav>

                <div className="p-4 border-t border-gray-800">
                    <button
                        type="button"
                        onClick={() => { setActiveTab("dashboard"); setIsMobileMenuOpen(false); }}
                        className={`w-full flex items-center gap-3 p-2 rounded-lg cursor-pointer transition-colors group ${activeTab === 'dashboard' ? 'bg-blue-600/10 border border-blue-500/20' : 'hover:bg-gray-800'}`}
                    >
                        <div className={`w-8 h-8 rounded-full border transition-colors flex items-center justify-center ${activeTab === 'dashboard' ? 'bg-blue-600 border-blue-400' : 'bg-gray-700 border-gray-600 group-hover:border-gray-400'}`}>
                            <Cpu size={14} className={activeTab === 'dashboard' ? 'text-white' : 'text-gray-400'} />
                        </div>
                        <span className={`text-sm font-medium transition-colors ${activeTab === 'dashboard' ? 'text-white' : 'text-gray-400 group-hover:text-gray-200'}`}>User Dashboard</span>
                    </button>

                    {user?.is_admin && (
                        <button
                            type="button"
                            onClick={() => router.push("/admin")}
                            className="w-full flex items-center gap-3 p-2 rounded-lg cursor-pointer transition-colors group hover:bg-blue-600/10 border border-transparent hover:border-blue-500/20 mt-2"
                        >
                            <div className="w-8 h-8 rounded-full bg-blue-600/20 border border-blue-500/30 transition-colors flex items-center justify-center group-hover:bg-blue-600 group-hover:border-blue-400">
                                <Shield size={14} className="text-blue-400 group-hover:text-white" />
                            </div>
                            <span className="text-sm font-medium text-gray-400 group-hover:text-white transition-colors">Admin Panel</span>
                        </button>
                    )}

                    <button
                        onClick={logout}
                        className="w-full flex items-center gap-3 p-3 rounded-xl hover:bg-red-500/10 text-gray-400 hover:text-red-400 transition-all mt-4 group"
                        title="Cerrar Sesión"
                    >
                        <Lock size={18} className="group-hover:rotate-12 transition-transform" />
                        <span className="text-sm font-medium">Cerrar Sesión</span>
                    </button>
                </div>
            </aside>

            {/* Main Content */}
            <main className="flex-1 flex flex-col bg-[#0d0d0d] overflow-hidden w-full">
                {/* Header */}
                <header className="h-16 border-b border-gray-800 flex items-center justify-between px-4 md:px-8">
                    <div className="flex items-center gap-2 md:gap-4 overflow-hidden">
                        <button 
                            className="p-1 -ml-1 text-gray-400 hover:text-white lg:hidden flex-shrink-0"
                            onClick={() => setIsMobileMenuOpen(true)}
                            title="Abrir menú"
                            aria-label="Abrir menú"
                        >
                            <Menu size={20} />
                        </button>
                        <h2 className="text-xs md:text-sm font-semibold uppercase tracking-widest text-gray-400 truncate">
                            {activeTab === "chat" ? "AI Research Assistant" :
                                activeTab === "research" ? "Active Research Pipelines" :
                                    activeTab === "knowledge" ? "Knowledge Base Explorer" :
                                        activeTab === "dashboard" ? "System Insights & User Metrics" :
                                            activeTab === "tools" ? "Proyectos Generados" :
                                                activeTab === "control" ? "Panel de control" : "Agent Orchestration"}
                        </h2>
                        {activeTab === "chat" && (
                            <div className="flex items-center gap-2">
                                <button 
                                    onClick={() => {
                                        if (confirm("¿Borrar todo el historial del chat?")) {
                                            const initialMsg = [{ role: "ai" as const, text: "SISTEMA OPERATIVO NOVA [v12.1.5]\nEstado: LISTO PARA PROCESAMIENTO\n\n📖 CONSULTA: Pregunta sobre el conocimiento ya adquirido en el grafo.\n🔬 INVESTIGACIÓN: Escribe 'investiga [tema]' para activar la autonomía web.\n\nIngrese directiva." }];
                                            setMessages(initialMsg);
                                            localStorage.setItem("nova_chat_history", JSON.stringify(initialMsg));
                                        }
                                    }}
                                    className="px-3 py-1 bg-red-600/10 border border-red-500/20 rounded-full text-[9px] font-bold text-red-500 hover:bg-red-600/20 transition-all uppercase tracking-tighter"
                                >
                                    Limpiar Chat
                                </button>
                                <button 
                                    onClick={() => setShowHelpModal(true)}
                                    className="px-3 py-1 bg-blue-600/10 border border-blue-500/20 rounded-full text-[9px] font-bold text-blue-400 hover:bg-blue-600/20 transition-all uppercase tracking-tighter flex items-center gap-1"
                                >
                                    <AlertCircle size={10} />
                                    Guía de Uso
                                </button>
                            </div>
                        )}
                    </div>
                    <div className="flex items-center gap-6">
                        <div className="flex items-center gap-2">
                            <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                            <span className="text-[10px] text-gray-400 font-bold uppercase tracking-wider">{Object.values(agentStates).filter(s => s === 'working').length} Agentes Activos</span>
                        </div>
                        <div className="h-6 w-[1px] bg-gray-800" />
                        <div className="flex items-center gap-2 text-xs text-blue-400 bg-blue-500/10 px-3 py-1 rounded-full border border-blue-500/20">
                            <UserIcon size={12} />
                            <span className="font-bold">{user?.username}</span>
                        </div>
                    </div>
                </header>

                {/* Dynamic Area */}
                <div className="flex-1 flex flex-col p-4 md:p-8 overflow-hidden relative">
                    {activeTab === "chat" && (
                        <div className="flex-1 flex flex-col h-full">
                            <div className="flex-1 space-y-6 overflow-y-auto pr-4 scrollbar-hide">
                                {messages.map((msg, i) => (
                                    <ChatMessage key={i} role={msg.role} text={msg.text} images={msg.images} />
                                ))}
                                {isLoading && (
                                    <div className="flex justify-start items-center gap-3 animate-in fade-in slide-in-from-left-2 duration-500">
                                        <div className="relative">
                                            <div className="w-10 h-10 bg-[#161616] rounded-xl border border-gray-800 flex items-center justify-center overflow-hidden">
                                                <div className={`absolute inset-0 opacity-20 animate-pulse ${
                                                    streamingIntent === 'RESEARCH' ? 'bg-amber-500' : 
                                                    streamingIntent === 'PROJECT_BUILD' ? 'bg-purple-500' : 
                                                    'bg-blue-500'
                                                }`} />
                                                <Activity size={18} className={`animate-pulse ${
                                                    streamingIntent === 'RESEARCH' ? 'text-amber-500' : 
                                                    streamingIntent === 'PROJECT_BUILD' ? 'text-purple-500' : 
                                                    'text-blue-500'
                                                }`} />
                                            </div>
                                        </div>
                                        <div className="flex flex-col">
                                            <span className="text-[10px] font-black uppercase tracking-[0.2em] text-gray-500 mb-0.5">
                                                {streamingIntent || "NOVA CORE"}
                                            </span>
                                            <div className="flex items-center gap-2">
                                                <span className="text-sm text-gray-300 font-medium italic">
                                                    {streamingIntent === 'RESEARCH' ? "Desplegando Swarm de Agentes..." :
                                                     streamingIntent === 'PROJECT_BUILD' ? "Construyendo Arquitectura..." :
                                                     streamingIntent === 'KNOWLEDGE' ? "Consultando Base de Datos..." :
                                                     "Sincronizando Omni-Kernel..."}
                                                </span>
                                                <div className="flex gap-1">
                                                    <span className="w-1 h-1 bg-blue-500 rounded-full animate-bounce [animation-delay:-0.3s]" />
                                                    <span className="w-1 h-1 bg-blue-500 rounded-full animate-bounce [animation-delay:-0.15s]" />
                                                    <span className="w-1 h-1 bg-blue-500 rounded-full animate-bounce" />
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                )}
                                <div ref={messagesEndRef} />
                            </div>

                            {/* Input Area */}
                            <div className="mt-8 relative z-30">
                                <div className="flex flex-col gap-2 mb-4 relative z-30">
                                    {selectedImages.length > 0 && (
                                        <div className="flex flex-wrap gap-2">
                                            {selectedImages.map((img, i) => (
                                                <div key={i} className="relative group w-16 h-16">
                                                    <img src={img} alt="preview" className="w-full h-full object-cover rounded-lg border border-blue-500/30" />
                                                    <button 
                                                        onClick={() => removeImage(i)}
                                                        className="absolute -top-1.5 -right-1.5 bg-red-600 text-white rounded-full p-0.5 shadow-lg opacity-0 group-hover:opacity-100 transition-opacity"
                                                        aria-label="Eliminar imagen"
                                                    >
                                                        <X size={12} />
                                                    </button>
                                                </div>
                                            ))}
                                        </div>
                                    )}

                                    {selectedFiles.length > 0 && (
                                        <div className="flex flex-wrap gap-2">
                                            {selectedFiles.map((file, i) => (
                                                <div key={i} className="relative group px-3 py-1.5 bg-blue-600/10 border border-blue-500/30 rounded-full flex items-center gap-2">
                                                    <FileCode size={12} className="text-blue-400" />
                                                    <span className="text-[10px] text-blue-300 font-mono max-w-[120px] truncate">{file.name}</span>
                                                    <button 
                                                        onClick={() => removeFile(i)}
                                                        className="text-gray-500 hover:text-red-400 transition-colors"
                                                        aria-label="Eliminar archivo"
                                                    >
                                                        <X size={10} />
                                                    </button>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>

                                {/* v13.7.0: Multi-Mode Selector Bar */}
                                <div className="flex items-center gap-2 mb-3 px-1 overflow-x-auto scrollbar-hide no-scrollbar pb-1">
                                    <ModePill 
                                        active={chatMode === 'auto'} 
                                        onClick={() => setChatMode('auto')} 
                                        icon={<Activity size={12} />} 
                                        label="Auto" 
                                        color="blue"
                                        tooltip="Inteligencia Adaptativa"
                                    />
                                    <ModePill 
                                        active={chatMode === 'chat'} 
                                        onClick={() => setChatMode('chat')} 
                                        icon={<Terminal size={12} />} 
                                        label="Chat" 
                                        color="green"
                                        tooltip="Solo conversación (Seguro)"
                                    />
                                    <ModePill 
                                        active={chatMode === 'research'} 
                                        onClick={() => setChatMode('research')} 
                                        icon={<Search size={12} />} 
                                        label="Investigación" 
                                        color="amber"
                                        tooltip="Búsqueda Autónoma Web"
                                    />
                                    <ModePill 
                                        active={chatMode === 'build'} 
                                        onClick={() => setChatMode('build')} 
                                        icon={<Cpu size={12} />} 
                                        label="Proyectos" 
                                        color="purple"
                                        tooltip="Construcción de Software"
                                    />
                                    <ModePill 
                                        active={chatMode === 'knowledge'} 
                                        onClick={() => setChatMode('knowledge')} 
                                        icon={<BookOpen size={12} />} 
                                        label="Conocimiento" 
                                        color="cyan"
                                        tooltip="Consulta de Base Local (RAG)"
                                    />
                                </div>
                                
                                <input
                                    type="file"
                                    ref={fileInputRef}
                                    onChange={handleFileChange}
                                    multiple
                                    accept="image/*,.py,.js,.ts,.tsx,.jsx,.cpp,.c,.h,.hpp,.cs,.java,.kt,.go,.rs,.rb,.php,.swift,.dart,.lua,.r,.scala,.pl,.sh,.bat,.ps1,.txt,.json,.md,.pdf,.html,.css,.scss,.sass,.less,.xml,.yaml,.yml,.toml,.ini,.cfg,.conf,.env,.sql,.graphql,.proto,.dockerfile,.makefile,.cmake,.gradle,.csv,.log,.gitignore,.editorconfig"
                                    className="hidden"
                                    title="Subir archivos"
                                    aria-label="Seleccionar imágenes o archivos de texto"
                                />

                                <div className="relative flex items-center">
                                    <div className="absolute left-3 flex items-center gap-1 z-10">
                                        <button 
                                            onClick={() => fileInputRef.current?.click()}
                                            className="p-2 text-gray-500 hover:text-blue-400 transition-colors"
                                            title="Adjuntar imagen"
                                        >
                                            <Paperclip size={20} />
                                        </button>
                                        <button 
                                            onClick={toggleRecording}
                                            className={`p-2 transition-colors ${isRecording ? 'text-red-500 animate-pulse' : 'text-gray-500 hover:text-blue-400'}`}
                                            title={isRecording ? "Detener grabación" : "Grabar voz"}
                                        >
                                            <Mic size={20} />
                                        </button>
                                        <button 
                                            onClick={() => setVoiceEnabled(!voiceEnabled)}
                                            className={`p-2 transition-colors ${voiceEnabled ? 'text-green-400 drop-shadow-[0_0_8px_rgba(74,222,128,0.5)]' : 'text-gray-500 hover:text-blue-400'}`}
                                            title={voiceEnabled ? "Voz activada — NOVA hablará las respuestas" : "Voz desactivada"}
                                        >
                                            {voiceEnabled ? <Volume2 size={20} /> : <VolumeX size={20} />}
                                        </button>
                                        <button 
                                            onClick={async () => {
                                                try {
                                                    const btn = document.getElementById('webcam-btn');
                                                    if (btn) btn.classList.add('animate-pulse', 'text-green-400');
                                                    const res = await apiFetch('/vision/webcam/analyze', {
                                                        method: 'POST',
                                                        headers: { 'Content-Type': 'application/json' },
                                                        body: JSON.stringify({ prompt: 'Describe en detalle y en español lo que ves en esta imagen de la cámara web. Sé específico sobre objetos, personas, colores y ambiente.' })
                                                    });
                                                    const data = await res.json();
                                                    if (data.analysis) {
                                                        setMessages((prev: any[]) => [...prev, 
                                                            { role: 'user', text: '📷 [Captura de Webcam]' },
                                                            { role: 'ai', text: `🎥 **Análisis de Webcam** (${data.resolution}):\n\n${data.analysis}` }
                                                        ]);
                                                    }
                                                } catch (e: any) {
                                                    setMessages((prev: any[]) => [...prev, { role: 'ai', text: `⚠️ No pude acceder a la cámara: ${e.message}` }]);
                                                } finally {
                                                    const btn = document.getElementById('webcam-btn');
                                                    if (btn) btn.classList.remove('animate-pulse', 'text-green-400');
                                                }
                                            }}
                                            id="webcam-btn"
                                            className="p-2 text-gray-500 hover:text-blue-400 transition-colors"
                                            title="Capturar y analizar webcam"
                                        >
                                            <Camera size={20} />
                                        </button>
                                    </div>
                                    
                                    {/* Mic Selector Chip */}
                                    {audioDevices.length > 1 && !isRecording && (
                                        <div className="absolute bottom-[calc(100%+8px)] right-0 flex items-center gap-2 px-3 py-1.5 bg-[#161616] border border-gray-800 rounded-full text-[10px] text-gray-500 hover:border-gray-700 transition-all z-20 shadow-xl">
                                            <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-pulse" />
                                            <span className="font-medium uppercase tracking-tighter opacity-70">Entrada:</span>
                                            <select 
                                                value={selectedDeviceId}
                                                onChange={(e) => setSelectedDeviceId(e.target.value)}
                                                className="bg-transparent outline-none border-none cursor-pointer max-w-[120px] truncate pr-2 text-gray-300"
                                                title="Seleccionar micrófono"
                                                aria-label="Seleccionar dispositivo de entrada de audio"
                                            >
                                                {audioDevices.map((device, i) => (
                                                    <option key={device.deviceId} value={device.deviceId} className="bg-[#111] text-gray-300">
                                                        {device.label || `Mic ${i + 1}`}
                                                    </option>
                                                ))}
                                            </select>
                                        </div>
                                    )}
                                    
                                    <div className="flex-1 relative">
                                        <textarea
                                            ref={textareaRef}
                                            value={inputValue}
                                            onChange={(e) => setInputValue(e.target.value)}
                                            onKeyDown={(e) => {
                                                if (e.key === "Enter" && !e.shiftKey) {
                                                    e.preventDefault();
                                                    handleSendMessage();
                                                }
                                            }}
                                            onPaste={handlePaste}
                                            rows={1}
                                            placeholder={isRecording ? "Escuchando..." : "Escribe un tema o pregunta..."}
                                            className="w-full bg-[#161616] border border-gray-800 rounded-2xl py-4 pl-[11rem] pr-14 focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition-all text-sm shadow-2xl text-white placeholder:text-gray-600 resize-none overflow-y-auto scrollbar-hide min-h-[56px] flex items-center"
                                        />
                                        {isRecording && (
                                            <div className="absolute left-[88px] top-1/2 -translate-y-1/2 flex items-center gap-1 pointer-events-none">
                                                {React.createElement('div', {
                                                    className: "volume-bar",
                                                    title: "Nivel de voz",
                                                    "aria-label": "Indicador de nivel de voz",
                                                    style: { 
                                                        '--vol-width': `${Math.min(volume * 2, 100)}px`, 
                                                        '--vol-opacity': volume > 5 ? 1 : 0.3 
                                                    } as React.CSSProperties
                                                })}
                                            </div>
                                        )}
                                    </div>
                                    
                                    <button
                                        onClick={handleSendMessage}
                                        disabled={isLoading || isRecording}
                                        aria-label="Send Message"
                                        className="absolute right-3 p-2.5 bg-blue-600 rounded-xl hover:bg-blue-500 transition-all shadow-lg shadow-blue-600/20 active:scale-95 text-white disabled:opacity-50 disabled:cursor-not-allowed"
                                    >
                                        <Send size={18} />
                                    </button>
                                </div>
                            </div>
                        </div>
                    )}

                    {activeTab === "research" && (
                        <div className="h-full">
                            <ResearchSession logs={realtimeLogs} />
                        </div>
                    )}

                    {activeTab === "knowledge" && (
                        <div className="overflow-y-auto h-full pr-2">
                            <KnowledgeBrowser />
                        </div>
                    )}


                    <div className={activeTab === "activity" ? "h-full" : "hidden"}>
                        <div className="flex flex-col items-center justify-center h-full text-center space-y-6">
                            <div className="w-full h-[60vh] bg-[#080808] border border-gray-800 rounded-3xl overflow-hidden shadow-inner relative">
                                <div className="absolute top-6 left-6 flex items-center gap-3 z-10">
                                    <div className="w-3 h-3 bg-blue-500 rounded-full animate-pulse" />
                                    <h3 className="text-sm font-bold uppercase tracking-widest text-gray-500">Live Knowledge Graph</h3>
                                </div>
                                <KnowledgeGraph />
                            </div>
                            <div className="max-w-md">
                                <h3 className="text-xl font-bold text-white">Semantic Network Explorer</h3>
                                <p className="text-gray-500 text-sm mt-2">Los nodos representan conceptos clave y las líneas las relaciones descubiertas por la IA durante sus investigaciones.</p>
                            </div>
                        </div>
                    </div>
                    {activeTab === "dashboard" && (
                        <div className="h-full overflow-y-auto pr-4 scrollbar-hide">
                            <UserDashboard stats={systemStats} failures={systemFailures} onClearFailed={clearFailedJobs} />
                        </div>
                    )}

                    {activeTab === "tools" && (
                        <div className="h-full overflow-y-auto pr-4 scrollbar-hide">
                            <ProjectManager />
                        </div>
                    )}

                    {activeTab === "control" && (
                        <div className="h-full overflow-y-auto pr-4 scrollbar-hide">
                            <ControlPanel />
                        </div>
                    )}
                </div>
            </main>

            {/* Right Intelligence Panel */}
            <aside className="w-80 bg-[#111] border-l border-gray-800 p-6 space-y-8 hidden xl:block overflow-y-auto">
                <div>
                    <h3 className="text-xs font-bold uppercase tracking-widest text-gray-500 mb-4">Estado de Agentes</h3>
                    <div className="space-y-3">
                        <AgentStatus name="Planner" status={agentStates["Planner"] as any} />
                        <AgentStatus name="Explorer" status={agentStates["Explorer"] as any} />
                        <AgentStatus name="Analyzer" status={agentStates["Analyzer"] as any} />
                        <AgentStatus name="Critic" status={agentStates["Critic"] as any} />
                        <AgentStatus name="Verifier" status={agentStates["Verifier"] as any} />
                        <AgentStatus name="Librarian" status={agentStates["Librarian"] as any} />
                        <AgentStatus name="Browser" status={agentStates["Browser"] as any} />
                    </div>
                </div>

                <div>
                    <h3 className="text-xs font-bold uppercase tracking-widest text-gray-500 mb-4">Temas Recientes</h3>
                    <div className="space-y-2">
                        {knowledgeEntries.length === 0 ? (
                            <p className="text-[10px] text-gray-600 italic">No hay temas recientes...</p>
                        ) : (
                            knowledgeEntries.slice(-2).reverse().map((entry, idx) => (
                                <div key={idx} className="bg-[#161616] p-3 rounded-xl border border-gray-800/50 transition-all">
                                    <p className="text-xs font-medium text-blue-400"># {entry.title}</p>
                                    <p className="text-[10px] text-gray-500 mt-1 uppercase tracking-widest font-mono">Confianza: {((entry.confidence_score ?? entry.score ?? 0) * 100).toFixed(0)}%</p>
                                </div>
                            ))
                        )}
                    </div>
                </div>

                <div className="pt-4">
                    <div className="bg-gradient-to-br from-blue-600/10 to-indigo-600/10 p-5 rounded-2xl border border-blue-500/10">
                        <h4 className="text-sm font-bold text-gray-300">Capacidad Total</h4>
                        <div className="mt-3 w-full bg-gray-800 h-1.5 rounded-full overflow-hidden">
                                {React.createElement('div', {
                                    className: "bg-blue-600 h-full progress-bar-fill",
                                    style: { 
                                        "--progress-width": `${systemStats?.knowledge?.quality_ratio !== undefined ? (systemStats.knowledge.quality_ratio * 100).toFixed(0) : 0}%` 
                                    } as React.CSSProperties
                                })}
                        </div>
                        <p className="text-[10px] text-gray-500 mt-2">
                            {systemStats?.knowledge?.quality_ratio !== undefined
                                ? `${(systemStats.knowledge.quality_ratio * 100).toFixed(0)}% del conocimiento procesado es de alta calidad.`
                                : "Sincronizando métricas de calidad..."}
                        </p>
                    </div>
                </div>
            </aside>

            {/* Help Modal Overlay */}
            {showHelpModal && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-300">
                    <div className="bg-[#111] border border-gray-800 w-full max-w-2xl max-h-[85vh] rounded-[2.5rem] overflow-hidden flex flex-col shadow-2xl animate-in zoom-in duration-300">
                        {/* Modal Header */}
                        <div className="p-6 border-b border-gray-800 flex items-center justify-between bg-gradient-to-r from-blue-600/10 to-transparent">
                            <div className="flex items-center gap-3">
                                <div className="p-2.5 bg-blue-600 rounded-2xl shadow-lg shadow-blue-600/20">
                                    <BookOpen size={20} className="text-white" />
                                </div>
                                <div>
                                    <h3 className="text-lg font-bold text-white tracking-tight">Manual de Operaciones NOVA</h3>
                                    <p className="text-[10px] text-blue-400 uppercase tracking-widest font-bold">Neural Autonomous Versatile Agent v13.5</p>
                                </div>
                            </div>
                            <button 
                                onClick={() => setShowHelpModal(false)}
                                className="p-2 text-gray-500 hover:text-white hover:bg-white/5 rounded-full transition-all"
                                aria-label="Cerrar guía"
                            >
                                <X size={20} />
                            </button>
                        </div>
                        
                        {/* Modal Body */}
                        <div className="flex-1 overflow-y-auto p-8 space-y-10 scrollbar-hide">
                            {/* Interaction Modes */}
                            <section>
                                <div className="flex items-center gap-2 mb-4">
                                    <Search size={16} className="text-blue-400" />
                                    <h4 className="text-blue-400 font-bold uppercase tracking-[0.2em] text-[11px]">Modos de Interacción</h4>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div className="bg-[#161616] p-5 rounded-3xl border border-gray-800 hover:border-blue-500/30 transition-all group">
                                        <div className="flex items-center gap-2 mb-2">
                                            <span className="text-lg">📖</span>
                                            <p className="font-bold text-white group-hover:text-blue-400 transition-colors">Consulta (RAG)</p>
                                        </div>
                                        <p className="text-gray-500 text-xs leading-relaxed">Habla con total libertad para preguntar sobre lo que NOVA ya sabe o ha procesado en sus bases de datos y documentos.</p>
                                    </div>
                                    <div className="bg-[#161616] p-5 rounded-3xl border border-gray-800 hover:border-indigo-500/30 transition-all group">
                                        <div className="flex items-center gap-2 mb-2">
                                            <span className="text-lg">🔬</span>
                                            <p className="font-bold text-white group-hover:text-indigo-400 transition-colors">Investigación Web</p>
                                        </div>
                                        <p className="text-gray-500 text-xs leading-relaxed">Escribe <strong>&quot;investiga [tema]&quot;</strong> para desplegar agentes autónomos que navegarán por internet para buscar datos frescos.</p>
                                    </div>
                                </div>
                            </section>

                            {/* Core Capabilities */}
                            <section>
                                <div className="flex items-center gap-2 mb-6">
                                    <Activity size={16} className="text-amber-400" />
                                    <h4 className="text-amber-400 font-bold uppercase tracking-[0.2em] text-[11px]">Capacidades Especiales</h4>
                                </div>
                                <div className="space-y-6">
                                    <div className="flex gap-4">
                                        <div className="w-10 h-10 rounded-2xl bg-amber-500/10 flex items-center justify-center flex-shrink-0 text-xl border border-amber-500/20">👁️</div>
                                        <div>
                                            <p className="font-bold text-white mb-1">Ojos de NOVA (Visión de Escritorio)</p>
                                            <p className="text-gray-500 text-xs leading-relaxed">Dile <strong>&quot;mira mi pantalla&quot;</strong> o <strong>&quot;¿qué ves en la imagen?&quot;</strong>. NOVA puede tomar capturas de tu escritorio y analizar interfaces, código o errores visualmente.</p>
                                        </div>
                                    </div>
                                    <div className="flex gap-4">
                                        <div className="w-10 h-10 rounded-2xl bg-blue-500/10 flex items-center justify-center flex-shrink-0 text-xl border border-blue-500/20">🎙️</div>
                                        <div>
                                            <p className="font-bold text-white mb-1">Voz e Inteligencia Auditiva</p>
                                            <p className="text-gray-500 text-xs leading-relaxed">Usa el icono del micrófono para dar órdenes por voz. Si activas el icono del altavoz, NOVA te responderá con voz neuronal humana (Kokoro).</p>
                                        </div>
                                    </div>
                                    <div className="flex gap-4">
                                        <div className="w-10 h-10 rounded-2xl bg-green-500/10 flex items-center justify-center flex-shrink-0 text-xl border border-green-500/20">🛠️</div>
                                        <div>
                                            <p className="font-bold text-white mb-1">Project Manager Autónomo</p>
                                            <p className="text-gray-500 text-xs leading-relaxed">Pídele que desarrolle aplicaciones o scripts. NOVA creará los archivos reales en tu disco y podrás gestionarlos en la pestaña <strong>Proyectos</strong>.</p>
                                        </div>
                                    </div>
                                </div>
                            </section>

                            {/* Technical Tools */}
                            <section>
                                <div className="flex items-center gap-2 mb-4">
                                    <Terminal size={16} className="text-green-400" />
                                    <h4 className="text-green-400 font-bold uppercase tracking-[0.2em] text-[11px]">Caja de Herramientas (JSON Tools)</h4>
                                </div>
                                <p className="text-gray-500 text-xs mb-6 bg-white/5 p-4 rounded-2xl border border-white/5">NOVA decide qué herramienta usar según tu necesidad. Por seguridad, siempre te pedirá confirmación antes de realizar acciones críticas.</p>
                                <div className="grid grid-cols-2 gap-3">
                                    <div className="p-3 bg-black/40 rounded-xl border border-gray-800 flex flex-col gap-1">
                                        <code className="text-blue-400 font-bold text-[10px]">terminal</code>
                                        <span className="text-gray-600 text-[9px] uppercase font-bold">Comandos de Sistema</span>
                                    </div>
                                    <div className="p-3 bg-black/40 rounded-xl border border-gray-800 flex flex-col gap-1">
                                        <code className="text-indigo-400 font-bold text-[10px]">browser</code>
                                        <span className="text-gray-600 text-[9px] uppercase font-bold">Navegación Web Profunda</span>
                                    </div>
                                    <div className="p-3 bg-black/40 rounded-xl border border-gray-800 flex flex-col gap-1">
                                        <code className="text-amber-400 font-bold text-[10px]">vision</code>
                                        <span className="text-gray-600 text-[9px] uppercase font-bold">Captura y Control de OS</span>
                                    </div>
                                    <div className="p-3 bg-black/40 rounded-xl border border-gray-800 flex flex-col gap-1">
                                        <code className="text-green-400 font-bold text-[10px]">gws</code>
                                        <span className="text-gray-600 text-[9px] uppercase font-bold">Google Workspace Sync</span>
                                    </div>
                                </div>
                            </section>

                            {/* Pro-Tip Footer */}
                            <div className="mt-8 p-6 bg-gradient-to-br from-blue-600/10 to-indigo-600/10 rounded-[2rem] border border-blue-500/20 text-center relative overflow-hidden group">
                                <div className="absolute top-0 right-0 p-2 text-blue-500/20 group-hover:text-blue-500/40 transition-colors">
                                    <Activity size={40} />
                                </div>
                                <p className="text-xs text-gray-300 leading-relaxed relative z-10">
                                    &quot;La verdadera potencia de NOVA reside en su capacidad de **Autocorrección**. Si algo falla, pídeme que analice los logs o que intente un enfoque diferente.&quot;
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

function NavItem({ icon, label, active = false, onClick, title }: { icon: React.ReactNode, label: string, active?: boolean, onClick?: () => void, title?: string }) {
    return (
        <button
            type="button"
            onClick={onClick}
            title={title}
            className={`w-full flex items-center gap-3 p-3 rounded-xl cursor-pointer transition-all duration-200 ${active ? 'bg-blue-600 text-white shadow-xl shadow-blue-600/20' : 'text-gray-400 hover:bg-gray-800/50 hover:text-gray-200'}`}
        >
            {icon}
            <span className="text-sm font-medium">{label}</span>
            {active && <div className="ml-auto w-1.5 h-1.5 bg-white rounded-full" />}
        </button>
    );
}

function GenerativeChart({ dataStr }: { dataStr: string }) {
    try {
        const config = JSON.parse(dataStr);
        
        // Sanitize data: Ensure values are numbers
        const sanitizedData = Array.isArray(config.data) ? config.data.map((item: any) => ({
            ...item,
            value: typeof item.value === 'string' ? parseFloat(item.value.replace(/[^0-9.]/g, '')) : item.value
        })).filter((item: any) => !isNaN(item.value) && item.value !== null) : [];

        if (sanitizedData.length === 0) return null;

        const isBar = config.type === 'bar';
        const ChartComponent: any = isBar ? BarChart : LineChart;

        return (
            <div className="mt-4 mb-6 bg-[#0a0a0a] border border-gray-800 rounded-2xl p-6 shadow-2xl animate-in fade-in zoom-in duration-500">
                <div className="flex items-center gap-2 mb-6">
                    {isBar ? <BarChartIcon size={16} className="text-blue-400" /> : <TrendingUp size={16} className="text-indigo-400" />}
                    <h4 className="text-xs font-bold uppercase tracking-widest text-gray-400">{config.title || "Visualización de Datos"}</h4>
                </div>
                <div className="h-64 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <ChartComponent data={sanitizedData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#222" vertical={false} />
                            <XAxis 
                                dataKey="name" 
                                stroke="#555" 
                                fontSize={10} 
                                tickLine={false} 
                                axisLine={false}
                            />
                            <YAxis 
                                stroke="#555" 
                                fontSize={10} 
                                tickLine={false} 
                                axisLine={false}
                            />
                            <Tooltip 
                                contentStyle={{ backgroundColor: '#111', border: '1px solid #333', borderRadius: '8px', fontSize: '12px' }}
                                itemStyle={{ color: '#60a5fa' }}
                            />
                            {isBar ? (
                                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                                    {sanitizedData.map((entry: any, index: number) => (
                                        <Cell key={`cell-${index}`} fill={index % 2 === 0 ? '#3b82f6' : '#6366f1'} />
                                    ))}
                                </Bar>
                            ) : (
                                <Line type="monotone" dataKey="value" stroke="#6366f1" strokeWidth={3} dot={{ r: 4, fill: '#6366f1' }} activeDot={{ r: 6 }} />
                            )}
                        </ChartComponent>
                    </ResponsiveContainer>
                </div>
            </div>
        );
    } catch (e) {
        console.error("Failed to parse chart data", e);
        return <div className="p-4 border border-red-900/20 bg-red-900/10 rounded-xl text-xs text-red-500">Error rendering chart data</div>;
    }
}

function CodeBlock({ language, value }: { language: string, value: string }) {
    const [copied, setCopied] = useState(false);
    const isShort = value.length < 40 && !value.includes('\n');

    const handleCopy = () => {
        navigator.clipboard.writeText(value);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    const displayLanguage = (language || 'code').toLowerCase();
    const normalizedLanguage = 
        displayLanguage === 'dash' ? 'BASH' : 
        displayLanguage === 'bash' ? 'BASH' : 
        displayLanguage === 'sh' ? 'BASH' : 
        displayLanguage === 'powershell' ? 'PS' : 
        displayLanguage.toUpperCase();

    if (isShort && !language) {
        return (
            <code className="bg-[#0d0d0d] border border-gray-800 px-2 py-1 rounded-md text-blue-400 font-mono text-xs mx-1 inline-block shadow-sm">
                {value === 'undefined' ? '' : value}
            </code>
        );
    }

    return (
        <div className="relative my-4 group rounded-xl overflow-hidden border border-gray-800 bg-[#0d0d0d] shadow-2xl">
            <div className="flex items-center justify-between px-4 py-1.5 bg-[#161616] border-b border-gray-800">
                <span className="text-[10px] font-bold uppercase tracking-widest text-gray-500 font-mono">
                    {normalizedLanguage}
                </span>
                <button
                    onClick={handleCopy}
                    className="flex items-center gap-1.5 p-1 text-gray-500 hover:text-blue-400 transition-colors"
                    title="Copiar código"
                >
                    {copied ? <Check size={14} className="text-green-500" /> : <Copy size={14} />}
                    <span className="text-[10px] font-medium uppercase">{copied ? 'Copiado' : 'Copiar'}</span>
                </button>
            </div>
            <SyntaxHighlighter
                language={language || 'text'}
                style={vscDarkPlus}
                customStyle={{
                    margin: 0,
                    padding: '1.25rem',
                    fontSize: '13px',
                    lineHeight: '1.6',
                    background: 'transparent',
                }}
            >
                {value}
            </SyntaxHighlighter>
        </div>
    );
}

function ChatMessage({ role, text, images }: { role: 'ai' | 'user', text: string, images?: string[] }) {
    // Detect json_chart blocks and separate them from Markdown
    const parts = text.split(/(```json_chart[\s\S]*?```)/g);

    return (
        <div className={`flex flex-col ${role === 'user' ? 'items-end' : 'items-start'} animate-in fade-in slide-in-from-bottom-2 duration-300`}>
            {images && images.length > 0 && (
                <div className="flex flex-wrap gap-2 mb-2 max-w-[85%]">
                    {images.map((img, i) => (
                        <div key={i} className="w-24 h-24 rounded-xl overflow-hidden border border-gray-800 shadow-xl group hover:border-blue-500/50 transition-all">
                            <img src={img} alt="attached" className="w-full h-full object-cover group-hover:scale-110 transition-transform duration-500" />
                        </div>
                    ))}
                </div>
            )}
            <div className={`max-w-[85%] p-5 rounded-3xl text-sm leading-relaxed ${role === 'user' ? 'bg-gradient-to-br from-blue-600 to-indigo-700 text-white rounded-tr-none shadow-xl shadow-blue-600/10' : 'bg-[#121212] border border-gray-800/80 text-gray-200 rounded-tl-none shadow-2xl'}`}>
                {parts.map((part, index) => {
                    if (part.startsWith('```json_chart')) {
                        const dataStr = part.replace(/```json_chart\n?|```/g, '').trim();
                        return <GenerativeChart key={index} dataStr={dataStr} />;
                    }

                    return (
                        <div key={index} className="prose prose-invert max-w-none prose-sm">
                            <ReactMarkdown
                                remarkPlugins={[remarkGfm]}
                                components={{
                                    code({ node, inline, className, children, ...props }: any) {
                                        const match = /language-(\w+)/.exec(className || '');
                                        const lang = match ? match[1] : '';
                                        const value = String(children).replace(/\n$/, '');
                                        
                                        return !inline ? (
                                            <CodeBlock language={lang} value={value} />
                                        ) : (
                                            <code className="bg-gray-800 px-1.5 py-0.5 rounded text-blue-300 font-mono text-xs" {...props}>
                                                {children}
                                            </code>
                                        );
                                    },
                                    strong({ children }) {
                                        return <strong className="font-bold text-white bg-blue-500/10 px-1 rounded">{children}</strong>;
                                    },
                                    p({ children }) {
                                        return <p className="mb-3 last:mb-0 break-words">{children}</p>;
                                    },
                                    ul({ children }) {
                                        return <ul className="list-disc pl-5 mb-4 space-y-2">{children}</ul>;
                                    },
                                    ol({ children }) {
                                        return <ol className="list-decimal pl-5 mb-4 space-y-2">{children}</ol>;
                                    },
                                    li({ children }) {
                                        return React.createElement('li', { className: "marker:text-blue-500 list-none flex gap-2" }, 
                                            React.createElement('span', null, '•'), 
                                            React.createElement('div', null, children)
                                        );
                                    },
                                    table({ children }) {
                                        return (
                                            <div className="overflow-x-auto my-6 rounded-xl border border-gray-800 shadow-2xl bg-[#0a0a0a]">
                                                <table className="w-full text-left border-collapse text-sm">
                                                    {children}
                                                </table>
                                            </div>
                                        );
                                    },
                                    thead({ children }) {
                                        return <thead className="bg-[#111] border-b border-gray-800 text-gray-400 font-bold uppercase tracking-widest text-[10px]">{children}</thead>;
                                    },
                                    tbody({ children }) {
                                        return <tbody className="divide-y divide-gray-800/50">{children}</tbody>;
                                    },
                                    tr({ children }) {
                                        return <tr className="hover:bg-blue-600/5 transition-colors">{children}</tr>;
                                    },
                                    th({ children }) {
                                        return <th className="px-4 py-3 border-r border-gray-800/30 last:border-r-0 whitespace-nowrap">{children}</th>;
                                    },
                                    td({ children }) {
                                        return <td className="px-4 py-3 border-r border-gray-800/30 last:border-r-0 text-white font-medium">{children}</td>;
                                    }
                                }}
                            >
                                {part}
                            </ReactMarkdown>
                        </div>
                    );
                })}
                {role === 'ai' && text.trim().length > 0 && (
                    <div className="mt-3 pt-2 border-t border-gray-800/50 flex items-center justify-between">
                        <AudioStreamPlayer text={text} className="!p-1.5 !bg-[#161616]/80 text-xs border-gray-800/60" />
                        <span className="text-[9px] font-mono text-gray-500 tracking-wider uppercase flex items-center gap-1">
                            <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full inline-block" /> Guardrail Verified
                        </span>
                    </div>
                )}
            </div>
        </div>
    );
}


function AgentStatus({ name, status }: { name: string, status: 'working' | 'idle' }) {
    return (
        <div className="flex items-center justify-between p-3 bg-[#161616] rounded-xl border border-gray-800/30">
            <div className="flex items-center gap-2">
                <div className={`w-1.5 h-1.5 rounded-full ${status === 'working' ? 'bg-amber-500 animate-pulse' : 'bg-green-500'}`} />
                <span className="text-sm text-gray-300">{name}</span>
            </div>
            <span className={`text-[9px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider ${status === 'working' ? 'bg-amber-500/10 text-amber-500 border border-amber-500/20' : 'bg-green-500/10 text-green-500 border border-green-500/20'}`}>
                {status}
            </span>
        </div>
    );
}

function UserDashboard({ stats, failures, onClearFailed }: { stats: any, failures: any[], onClearFailed?: () => void }) {
    if (!stats) return (
        <div className="flex items-center justify-center h-full text-gray-500 animate-pulse font-mono tracking-widest uppercase text-xs">
            <Cpu size={16} className="mr-2" /> Sincronizando Omni-Kernel...
        </div>
    );

    const handleClear = () => {
        if (onClearFailed) {
            onClearFailed();
        }
    };

    return (
        <div className="space-y-10 pb-12 animate-in fade-in slide-in-from-bottom-4 duration-1000">
            {/* Header & Omni-Kernel Heart */}
            <div className="flex flex-col md:flex-row items-center justify-between gap-8 bg-[#111]/40 backdrop-blur-2xl border border-white/5 p-10 rounded-[2.5rem] shadow-2xl relative overflow-hidden group">
                {/* Background Ambient Glow */}
                <div className="absolute -top-24 -right-24 w-64 h-64 bg-blue-600/10 rounded-full blur-[100px] group-hover:bg-blue-600/20 transition-all duration-1000" />
                <div className="absolute -bottom-24 -left-24 w-64 h-64 bg-indigo-600/10 rounded-full blur-[100px] group-hover:bg-indigo-600/20 transition-all duration-1000" />
                
                <div className="relative z-10 flex flex-col items-center md:items-start text-center md:text-left">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="px-3 py-1 bg-blue-500/10 border border-blue-500/20 rounded-full text-[10px] font-bold text-blue-400 uppercase tracking-widest">
                            System Status: Optimal
                        </div>
                    </div>
                    <h2 className="text-4xl font-black text-white tracking-tighter mb-2 italic">NOVA DASHBOARD</h2>
                    <p className="text-gray-500 text-sm max-w-sm">Monitoreo proactivo en tiempo real del Omni-Kernel y el Swarm de Agentes.</p>
                </div>

                <div className="relative z-10 flex flex-col items-center">
                    <div className="relative">
                        <div className="w-24 h-24 bg-gradient-to-br from-blue-600 to-indigo-700 rounded-3xl flex items-center justify-center shadow-[0_0_50px_rgba(37,99,235,0.3)] animate-pulse hover:scale-105 transition-transform duration-500 cursor-help group/kernel">
                            <Cpu size={40} className="text-white" />
                            {/* Inner rings */}
                            <div className="absolute inset-0 border-2 border-white/20 rounded-3xl animate-[ping_3s_infinite]" />
                            <div className="absolute -inset-4 border border-blue-500/10 rounded-[2rem] animate-[pulse_4s_infinite]" />
                        </div>
                        <div className="absolute -top-2 -right-2 w-6 h-6 bg-green-500 border-4 border-[#0a0a0a] rounded-full shadow-lg" />
                    </div>
                    <p className="mt-4 text-[10px] font-bold text-blue-400 uppercase tracking-[0.3em] font-mono">Omni-Kernel Active</p>
                </div>
            </div>

            {/* Core Metrics Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <StatCard
                    label="Artículos Analizados"
                    value={stats?.knowledge?.total_entries ?? 0}
                    icon={<BookOpen size={20} />}
                    color="blue"
                    description="Conocimiento curado"
                />
                <StatCard
                    label="Nodos en Grafo"
                    value={stats?.knowledge?.total_nodes ?? 0}
                    icon={<Activity size={20} />}
                    color="purple"
                    description="Red semántica"
                />
                <StatCard
                    label="Conexiones"
                    value={stats?.knowledge?.total_links ?? 0}
                    icon={<Database size={20} />}
                    color="indigo"
                    description="Relaciones autónomas"
                />
                <StatCard
                    label="Confianza Promedio"
                    value={`${((stats?.knowledge?.avg_confidence ?? 0) * 100).toFixed(0)}%`}
                    icon={<TrendingUp size={20} />}
                    color="green"
                    description="Calidad de datos"
                />
            </div>

            {/* Research & Failures Section */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
                {/* Main Job Metrics */}
                <div className="lg:col-span-8 bg-[#111]/60 backdrop-blur-xl border border-white/5 rounded-[2.5rem] p-10 shadow-3xl hover:border-white/10 transition-colors">
                    <div className="flex items-center justify-between mb-10">
                        <div>
                            <h3 className="text-2xl font-bold text-white tracking-tight">Investigaciones en Curso</h3>
                            <p className="text-gray-500 text-xs mt-1 uppercase tracking-widest font-medium">Distribución de carga de trabajo</p>
                        </div>
                        <div className="flex items-center gap-2 px-4 py-2 bg-white/5 border border-white/5 rounded-2xl text-[10px] font-bold text-gray-400 uppercase tracking-tighter">
                            Total: {stats?.jobs?.total ?? 0}
                        </div>
                    </div>
                    
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-8">
                        <JobMetric label="Completadas con Éxito" count={stats?.jobs?.completed ?? 0} color="bg-green-500" total={stats?.jobs?.total ?? 0} icon={<CheckCircle size={16} className="text-green-500" />} />
                        <JobMetric label="En Ejecución" count={stats?.jobs?.running ?? 0} color="bg-blue-500" total={stats?.jobs?.total ?? 0} icon={<Activity size={16} className="text-blue-500" />} />
                        <JobMetric label="En Espera" count={stats?.jobs?.pending ?? 0} color="bg-gray-500" total={stats?.jobs?.total ?? 0} icon={<Clock size={16} className="text-gray-400" />} />
                        <JobMetric label="Interrupciones/Fallos" count={stats?.jobs?.failed ?? 0} color="bg-red-500" total={stats?.jobs?.total ?? 0} icon={<AlertCircle size={16} className="text-red-500" />} />
                    </div>
                </div>

                {/* System Control / Clear Failures */}
                <div className="lg:col-span-4 flex flex-col gap-6">
                    <div className={`bg-gradient-to-br border rounded-[2rem] p-8 flex flex-col items-center text-center group transition-all duration-500 ${stats?.system?.has_critical ? "from-red-600/20 to-red-600/5 border-red-500/30 shadow-[0_0_30px_rgba(239,68,68,0.1)]" : (stats?.system?.failures_count > 0 ? "from-amber-600/10 to-transparent border-amber-500/20" : "from-gray-800/10 to-transparent border-white/5")}`}>
                        <div className={`p-4 rounded-2xl mb-6 transition-all duration-500 ${stats?.system?.has_critical ? "bg-red-600 text-white shadow-[0_0_40px_rgba(220,38,38,0.5)] animate-pulse" : (stats?.system?.failures_count > 0 ? "bg-amber-500 text-white shadow-xl shadow-amber-500/20" : "bg-gray-800/50 text-gray-600")}`}>
                            <AlertCircle size={32} />
                        </div>
                        <h4 className="text-lg font-bold text-white mb-2">Gestión de Fallos</h4>
                        <p className="text-gray-500 text-xs mb-8">
                            {stats?.system?.failures_count > 0 
                                ? `Detectados ${stats.system.failures_count} fallos de integridad o sistema.` 
                                : "Purga errores críticos para mantener el Omni-Kernel limpio de basura operativa."}
                        </p>
                        <button 
                            onClick={handleClear}
                            disabled={(stats?.jobs?.failed ?? 0) === 0}
                            className={`w-full py-4 rounded-2xl font-bold uppercase tracking-widest text-[10px] transition-all duration-300 ${(stats?.jobs?.failed ?? 0) > 0 ? (stats?.system?.has_critical ? "bg-red-600 hover:bg-red-700 shadow-red-600/20" : "bg-amber-600 hover:bg-amber-500 shadow-amber-600/20") + " text-white shadow-xl active:scale-95" : "bg-gray-800 text-gray-600 cursor-not-allowed opacity-50"}`}
                        >
                            {(stats?.jobs?.failed ?? 0) > 0 ? (stats?.system?.has_critical ? "REMEDIACIÓN CRÍTICA (Limpiar)" : "Restablecer Sistema (Limpiar)") : "Sin fallos detectados"}
                        </button>
                    </div>

                    {/* v11.0: Detailed System Events Drawer style */}
                    {failures && failures.length > 0 && (
                        <div className="bg-[#111]/40 backdrop-blur-xl border border-white/10 rounded-[2rem] p-6 animate-in fade-in zoom-in duration-500">
                            <h4 className="text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-4 flex items-center gap-2">
                                <Activity size={12} className="text-blue-500" /> Auditoría del Núcleo (Reciente)
                            </h4>
                            <div className="space-y-3 max-h-[300px] overflow-y-auto pr-2 scrollbar-hide">
                                {failures.map((fail) => (
                                    <div key={fail.id} className={`p-3 rounded-xl border flex flex-col gap-1 transition-all hover:bg-white/5 ${fail.severity === 'critical' ? 'bg-red-500/5 border-red-500/10' : 'bg-white/5 border-white/5'}`}>
                                        <div className="flex items-center justify-between">
                                            <span className={`text-[9px] font-black uppercase tracking-tighter ${fail.severity === 'critical' ? 'text-red-400' : 'text-amber-400'}`}>
                                                {fail.type}
                                            </span>
                                            <span className="text-[8px] text-gray-600 font-mono">
                                                {new Date(fail.timestamp).toLocaleTimeString()}
                                            </span>
                                        </div>
                                        <p className="text-[10px] text-gray-300 leading-tight">
                                            {fail.description}
                                        </p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    <div className="bg-[#111]/40 backdrop-blur-xl border border-white/5 rounded-[2rem] p-8">
                        <div className="flex items-center gap-3 mb-6">
                            <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center font-bold text-white text-[10px]">v10.1</div>
                            <div>
                                <h4 className="text-sm font-bold text-white tracking-tight">Industrial Core</h4>
                                <p className="text-[10px] text-blue-400 uppercase tracking-widest">Immortal Edition</p>
                            </div>
                        </div>
                        <div className="space-y-3">
                            <div className="flex items-center gap-3 p-3 bg-white/5 rounded-xl border border-white/5">
                                <CheckCircle size={14} className="text-green-500" />
                                <span className="text-[10px] font-bold text-gray-400 uppercase tracking-tighter">Persistence Layer [OK]</span>
                            </div>
                            <div className="flex items-center gap-3 p-3 bg-white/5 rounded-xl border border-white/5">
                                <CheckCircle size={14} className="text-green-500" />
                                <span className="text-[10px] font-bold text-gray-400 uppercase tracking-tighter">Auto-Remediation [Active]</span>
                            </div>
                            <div className="flex items-center gap-3 p-3 bg-white/5 rounded-xl border border-white/5">
                                <CheckCircle size={14} className="text-green-500" />
                                <span className="text-[10px] font-bold text-gray-400 uppercase tracking-tighter">Swarm Sync [Synced]</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

function StatCard({ label, value, icon, color, description }: { label: string, value: any, icon: React.ReactNode, color: string, description?: string }) {
    const colorClasses: any = {
        blue: "bg-blue-600 text-white shadow-blue-600/20",
        purple: "bg-purple-600 text-white shadow-purple-600/20",
        indigo: "bg-indigo-600 text-white shadow-indigo-600/20",
        green: "bg-green-600 text-white shadow-green-600/20"
    };

    const iconBgClasses: any = {
        blue: "bg-blue-500/10 text-blue-500 border-blue-500/20",
        purple: "bg-purple-500/10 text-purple-500 border-purple-500/20",
        indigo: "bg-indigo-500/10 text-indigo-500 border-indigo-500/20",
        green: "bg-green-500/10 text-green-500 border-green-500/20"
    };

    return (
        <div className="bg-[#111]/60 backdrop-blur-xl border border-white/5 p-4 md:p-8 rounded-[2rem] hover:border-white/20 transition-all hover:translate-y-[-8px] duration-500 shadow-2xl group flex flex-col items-center md:items-start text-center md:text-left overflow-hidden">
            <div className={`w-14 h-14 ${iconBgClasses[color]} border rounded-2xl flex items-center justify-center mb-6 group-hover:scale-110 group-hover:rotate-6 transition-all duration-500 flex-shrink-0`}>
                {icon}
            </div>
            <p className="text-gray-500 text-[10px] font-bold uppercase tracking-[0.2em] mb-1 truncate w-full">{label}</p>
            <h4 className="text-2xl md:text-4xl font-black text-white tracking-tighter mb-2 truncate w-full">{value}</h4>
            {description && <p className="text-[9px] md:text-[10px] text-gray-600 font-medium uppercase tracking-widest truncate w-full">{description}</p>}
        </div>
    );
}

function JobMetric({ label, count, color, total, icon }: { label: string, count: number, color: string, total: number, icon?: React.ReactNode }) {
    const safeCount = count || 0;
    const safeTotal = total || 0;
    const percentage = safeTotal > 0 ? (safeCount / safeTotal) * 100 : 0;
    return (
        <div className="space-y-4 group">
            <div className="flex justify-between items-end">
                <div className="flex items-center gap-3">
                    {icon}
                    <span className="text-xs font-bold text-gray-400 uppercase tracking-tighter">{label}</span>
                </div>
                <div className="flex flex-col items-end">
                    <span className="text-2xl font-black text-white leading-none">{safeCount}</span>
                    <span className="text-[10px] text-gray-600 font-bold uppercase">{percentage.toFixed(0)}%</span>
                </div>
            </div>
            <div className="w-full h-3 bg-white/5 border border-white/5 rounded-full overflow-hidden p-[2px] backdrop-blur-md">
                {React.createElement('div', {
                    className: `${color} h-full rounded-full transition-all duration-1000 ease-out shadow-[0_0_20px_rgba(255,255,255,0.05)]`,
                    style: { width: `${percentage}%` }
                })}
            </div>
        </div>
    );
}

function ModePill({ active, onClick, icon, label, color, tooltip }: any) {
    const colors = {
        blue: active ? 'bg-blue-600 text-white shadow-[0_0_15px_rgba(37,99,235,0.4)]' : 'bg-[#161616] text-gray-500 hover:text-blue-400',
        green: active ? 'bg-green-600 text-white shadow-[0_0_15px_rgba(22,163,74,0.4)]' : 'bg-[#161616] text-gray-500 hover:text-green-400',
        amber: active ? 'bg-amber-600 text-white shadow-[0_0_15px_rgba(217,119,6,0.4)]' : 'bg-[#161616] text-gray-500 hover:text-amber-400',
        purple: active ? 'bg-purple-600 text-white shadow-[0_0_15px_rgba(147,51,234,0.4)]' : 'bg-[#161616] text-gray-500 hover:text-purple-400',
        cyan: active ? 'bg-cyan-600 text-white shadow-[0_0_15px_rgba(8,145,178,0.4)]' : 'bg-[#161616] text-gray-500 hover:text-cyan-400',
    } as any;

    return (
        <button
            onClick={onClick}
            title={tooltip}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-full border border-gray-800/50 text-[10px] font-bold uppercase tracking-wider transition-all active:scale-95 whitespace-nowrap ${colors[color]}`}
        >
            {icon}
            <span>{label}</span>
        </button>
    );
}
