"use client";
import { apiFetch, getBaseUrl } from "@/lib/api";
import { Calendar, Copy, Download, ExternalLink, FileCode, HardDrive, Search, Trash, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";

interface Project {
    filename: string;
    size: number;
    created: number;
    download_url: string;
}

interface ProjectListResponse {
    projects: Project[];
}

interface Snippet {
    id: number;
    snippet_type: string;
    language: string;
    framework?: string;
    description?: string;
    code_preview?: string;
    code: string;
    created_at: string;
    usage_count: number;
}

interface SnippetSearchResponse {
    status: string;
    count: number;
    results: Snippet[];
}

interface HistoryItem {
    id: string;
    document: string;
    metadata?: {
        description?: string;
        project_name?: string;
        timestamp?: string;
    };
    distance?: number;
}

interface HistorySearchResponse {
    status: string;
    count: number;
    results: HistoryItem[];
}

interface GitCommit {
    hash: string;
    message: string;
    date: string;
    author: string;
}

interface GitHistoryResponse {
    status: string;
    count?: number;
    commits: GitCommit[];
    message?: string;
}

interface LaneStats {
    attempts: number;
    requests: number;
    errors: number;
    busy: number;
    busy_rate: number;
    avg_latency_ms: number;
    breaker_state: string;
    breaker_failures: number;
}

interface LlmLanesResponse {
    status: string;
    lanes: {
        realtime: LaneStats;
        batch: LaneStats;
    };
}

export default function ProjectManager() {
    const [activeTab, setActiveTab] = useState<"projects" | "snippets" | "history" | "git">("projects");
    const [projects, setProjects] = useState<Project[]>([]);
    const [loadingProjects, setLoadingProjects] = useState(true);
    const [projectsError, setProjectsError] = useState<string | null>(null);
    const [snippetQuery, setSnippetQuery] = useState("");
    const [snippetResults, setSnippetResults] = useState<Snippet[]>([]);
    const [loadingSnippets, setLoadingSnippets] = useState(false);
    const [snippetsError, setSnippetsError] = useState<string | null>(null);
    const [historyQuery, setHistoryQuery] = useState("");
    const [historyResults, setHistoryResults] = useState<HistoryItem[]>([]);
    const [loadingHistory, setLoadingHistory] = useState(false);
    const [historyError, setHistoryError] = useState<string | null>(null);
    const [gitCommits, setGitCommits] = useState<GitCommit[]>([]);
    const [loadingGit, setLoadingGit] = useState(false);
    const [gitError, setGitError] = useState<string | null>(null);
    const [selectedCommitHash, setSelectedCommitHash] = useState<string | null>(null);
    const [diffContent, setDiffContent] = useState<string | null>(null);
    const [loadingDiff, setLoadingDiff] = useState(false);
    const [diffError, setDiffError] = useState<string | null>(null);
    const [laneStats, setLaneStats] = useState<{ realtime: LaneStats; batch: LaneStats } | null>(null);
    const [loadingLanes, setLoadingLanes] = useState(false);
    const [lanesError, setLanesError] = useState<string | null>(null);

    useEffect(() => {
        const handleEsc = (e: KeyboardEvent) => {
            if (e.key === "Escape" && selectedCommitHash) {
                setSelectedCommitHash(null);
                setDiffContent(null);
                setDiffError(null);
            }
        };
        window.addEventListener("keydown", handleEsc);
        return () => window.removeEventListener("keydown", handleEsc);
    }, [selectedCommitHash]);

    useEffect(() => {
        loadProjects();
    }, []);

    const loadProjects = async () => {
        try {
            setLoadingProjects(true);
            setProjectsError(null);
            const response = await apiFetch("/projects/list");
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json() as ProjectListResponse;
            setProjects(data.projects || []);
        } catch (err) {
            setProjectsError("Error al cargar proyectos");
            console.error("Error loading projects:", err);
        } finally {
            setLoadingProjects(false);
        }
    };

    const deleteProject = async (filename: string) => {
        if (!window.confirm(`¿Estás seguro de que deseas eliminar el proyecto "${filename}"?`)) return;

        try {
            const response = await apiFetch(`/projects/delete/${filename}`, { method: "DELETE" });
            if (!response.ok) throw new Error("Error al eliminar el proyecto");
            
            // Actualizar estado local
            setProjects(prev => prev.filter(p => p.filename !== filename));
        } catch (err) {
            console.error(err);
            alert("No se pudo eliminar el proyecto");
        }
    };

    const clearAllProjects = async () => {
        if (!window.confirm("¿Estás seguro de que deseas eliminar TODOS los proyectos? Esta acción no se puede deshacer.")) return;

        try {
            const response = await apiFetch("/projects/clear-all", { method: "DELETE" });
            if (!response.ok) throw new Error("Error al limpiar proyectos");
            
            setProjects([]);
        } catch (err) {
            console.error(err);
            alert("No se pudieron limpiar los proyectos");
        }
    };

    const searchSnippets = async (queryOverride?: string) => {
        const normalizedQuery = (queryOverride ?? snippetQuery).trim();
        if (!normalizedQuery) {
            setSnippetResults([]);
            return;
        }
        try {
            setLoadingSnippets(true);
            setSnippetsError(null);
            const response = await apiFetch(`/snippets/search?query=${encodeURIComponent(normalizedQuery)}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json() as SnippetSearchResponse;
            setSnippetResults(data.results || []);
        } catch (err) {
            setSnippetsError("Error al buscar snippets");
            console.error("Error searching snippets:", err);
        } finally {
            setLoadingSnippets(false);
        }
    };

    const searchHistory = async (queryOverride?: string) => {
        const normalizedQuery = (queryOverride ?? historyQuery).trim();
        if (!normalizedQuery) {
            setHistoryResults([]);
            return;
        }
        try {
            setLoadingHistory(true);
            setHistoryError(null);
            const response = await apiFetch(`/history/search?query=${encodeURIComponent(normalizedQuery)}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json() as HistorySearchResponse;
            setHistoryResults(data.results || []);
        } catch (err) {
            setHistoryError("Error al buscar historial");
            console.error("Error searching history:", err);
        } finally {
            setLoadingHistory(false);
        }
    };

    const loadGitHistory = async (snapshotsOnly: boolean = true) => {
        try {
            setLoadingGit(true);
            setGitError(null);
            const response = await apiFetch(`/git/history?limit=30&snapshots_only=${snapshotsOnly ? "true" : "false"}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json() as GitHistoryResponse;
            if (data.status !== "success") {
                throw new Error(data.message || "No se pudo obtener historial Git");
            }
            setGitCommits(data.commits || []);
        } catch (err) {
            setGitError("Error al cargar historial Git");
            console.error("Error loading git history:", err);
        } finally {
            setLoadingGit(false);
        }
    };

    const loadDiff = async (commitHash: string) => {
        setSelectedCommitHash(commitHash);
        setLoadingDiff(true);
        setDiffError(null);
        setDiffContent(null);
        try {
            const response = await apiFetch(`/git/diff/${commitHash}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json() as { status?: string; message?: string; diff?: string };
            if (data.status && data.status !== "success") {
                throw new Error(data.message || "No se pudo cargar el diff");
            }
            setDiffContent(data.diff || "");
        } catch (err) {
            setDiffError("Error al cargar el diff");
            console.error("Error loading git diff:", err);
        } finally {
            setLoadingDiff(false);
        }
    };

    const loadLaneMetrics = async () => {
        try {
            setLoadingLanes(true);
            setLanesError(null);
            const response = await apiFetch("/llm/lanes");
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json() as LlmLanesResponse;
            if (data.status !== "ok" || !data.lanes) {
                throw new Error("Respuesta inválida de métricas");
            }
            setLaneStats(data.lanes);
        } catch (err) {
            setLanesError("Error al cargar métricas LLM lanes");
            setLaneStats(null);
            console.error("Error loading LLM lane metrics:", err);
        } finally {
            setLoadingLanes(false);
        }
    };

    const reuseSnippet = (snippet: { code: string; description?: string; snippet_type?: string; [key: string]: any }) => {
        const textToInject = [
            "Reutiliza este snippet en la siguiente solución:",
            snippet.description || `Tipo: ${snippet.snippet_type || "snippet"}`,
            "```",
            snippet.code,
            "```"
        ].join("\n");
        window.dispatchEvent(
            new CustomEvent("nova:inject-prompt", {
                detail: { text: textToInject }
            })
        );
    };

    const formatFileSize = (bytes: number): string => {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    };

    const formatDate = (timestamp: number): string => {
        return new Date(timestamp * 1000).toLocaleString('es-ES', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    };

    const getBackendUrl = () => {
        return getBaseUrl().replace("/api", "");
    };

    const handleDownload = async (downloadUrl: string, filename: string) => {
        try {
            // Normalizar el endpoint para apiFetch (eliminar /api inicial si ya viene en download_url)
            const endpoint = downloadUrl.startsWith('/api') 
                ? downloadUrl.replace('/api', '') 
                : downloadUrl;
            
            const response = await apiFetch(endpoint);
            if (!response.ok) {
                throw new Error(`Error al descargar el archivo (HTTP ${response.status})`);
            }
            const blob = await response.blob();
            const blobUrl = window.URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = blobUrl;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            window.URL.revokeObjectURL(blobUrl);
        } catch (err) {
            console.error("Download failed:", err);
            alert("No se pudo descargar el proyecto. Verifica tu sesión.");
        }
    };


    if (loadingProjects) {
        return (
            <div className="flex items-center justify-center h-full">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto mb-4"></div>
                    <p className="text-gray-400">Cargando proyectos...</p>
                </div>
            </div>
        );
    }

    if (projectsError && activeTab === "projects" && !loadingProjects) {
        return (
            <div className="flex items-center justify-center h-full">
                <div className="text-center text-red-400">
                    <p className="mb-4">{projectsError}</p>
                    <button
                        onClick={loadProjects}
                        className="px-4 py-2 bg-red-600/20 border border-red-500/30 rounded-lg hover:bg-red-600/30 transition-colors"
                    >
                        Reintentar
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div className="h-full flex flex-col">
            <div className="mb-6 flex items-center justify-between gap-4">
                <div>
                    <h3 className="text-2xl font-bold text-white mb-2">Gestor de Activos</h3>
                    <p className="text-gray-400 text-sm">
                        Administra proyectos generados y reutiliza snippets guardados.
                    </p>
                </div>
                <div className="flex items-center gap-2 bg-[#121212] border border-gray-800 rounded-xl p-1">
                    <button
                        onClick={() => setActiveTab("projects")}
                        className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                            activeTab === "projects"
                                ? "bg-blue-600/20 text-blue-300 border border-blue-500/30"
                                : "text-gray-400 hover:text-gray-200"
                        }`}
                    >
                        Proyectos
                    </button>
                    <button
                        onClick={() => setActiveTab("snippets")}
                        className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                            activeTab === "snippets"
                                ? "bg-blue-600/20 text-blue-300 border border-blue-500/30"
                                : "text-gray-400 hover:text-gray-200"
                        }`}
                    >
                        Librería
                    </button>
                    <button
                        onClick={() => setActiveTab("history")}
                        className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                            activeTab === "history"
                                ? "bg-blue-600/20 text-blue-300 border border-blue-500/30"
                                : "text-gray-400 hover:text-gray-200"
                        }`}
                    >
                        Historial
                    </button>
                    <button
                        onClick={() => {
                            setActiveTab("git");
                            if (gitCommits.length === 0) {
                                loadGitHistory(true);
                            }
                            if (!laneStats) {
                                loadLaneMetrics();
                            }
                        }}
                        className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                            activeTab === "git"
                                ? "bg-blue-600/20 text-blue-300 border border-blue-500/30"
                                : "text-gray-400 hover:text-gray-200"
                        }`}
                    >
                        Git
                    </button>
                </div>
            </div>

            {activeTab === "projects" && (projects.length === 0 ? (
                <div className="flex-1 flex items-center justify-center">
                    <div className="text-center text-gray-500">
                        <FileCode size={48} className="mx-auto mb-4 opacity-50" />
                        <p className="text-lg mb-2">No hay proyectos generados aún</p>
                        <p className="text-sm">
                            Usa el chat para pedirle a NOVA que cree un proyecto (ej: &quot;crea una app web de tareas&quot;)
                        </p>
                    </div>
                </div>
            ) : (
                <div className="flex-1 overflow-y-auto pr-4 scrollbar-hide">
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                        {projects.map((project) => (
                            <div
                                key={project.filename}
                                className="bg-[#161616] border border-gray-800 rounded-xl p-4 hover:border-gray-700 transition-all group"
                            >
                                <div className="flex items-start justify-between mb-3">
                                    <div className="flex items-center gap-2">
                                        <FileCode size={20} className="text-blue-400" />
                                        <h4 className="text-sm font-semibold text-white truncate max-w-[180px]">
                                            {project.filename.replace('.zip', '').replace(/nova_project_\d+_/, '')}
                                        </h4>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <button
                                            onClick={() => handleDownload(project.download_url, project.filename)}
                                            className="opacity-0 group-hover:opacity-100 transition-opacity p-2 bg-blue-600/20 border border-blue-500/30 rounded-lg hover:bg-blue-600/30"
                                            title="Descargar proyecto"
                                        >
                                            <Download size={16} className="text-blue-400" />
                                        </button>
                                        <button
                                            onClick={() => deleteProject(project.filename)}
                                            className="opacity-0 group-hover:opacity-100 transition-opacity p-2 bg-red-600/20 border border-red-500/30 rounded-lg hover:bg-red-600/30"
                                            title="Eliminar proyecto"
                                        >
                                            <Trash2 size={16} className="text-red-400" />
                                        </button>
                                    </div>
                                </div>

                                <div className="space-y-2 text-xs text-gray-400">
                                    <div className="flex items-center gap-2">
                                        <HardDrive size={12} />
                                        <span>{formatFileSize(project.size)}</span>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <Calendar size={12} />
                                        <span>{formatDate(project.created)}</span>
                                    </div>
                                </div>

                                <div className="mt-4 flex gap-2">
                                    <button
                                        onClick={() => handleDownload(project.download_url, project.filename)}
                                        className="flex-1 flex items-center justify-center gap-2 px-3 py-2 bg-blue-600/10 border border-blue-500/20 rounded-lg text-blue-400 hover:bg-blue-600/20 transition-colors text-xs font-medium"
                                    >
                                        <Download size={14} />
                                        Descargar
                                    </button>
                                    <button
                                        onClick={() => {
                                            const absoluteUrl = project.download_url.startsWith('http')
                                                ? project.download_url
                                                : `${getBackendUrl()}${project.download_url}`;
                                            window.open(absoluteUrl, '_blank');
                                        }}
                                        className="px-3 py-2 bg-gray-600/10 border border-gray-500/20 rounded-lg text-gray-400 hover:bg-gray-600/20 transition-colors"
                                        title="Abrir en nueva pestaña"
                                    >
                                        <ExternalLink size={14} />
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            ))}

            {activeTab === "projects" && projects.length > 0 && (
                <div className="mt-6 pt-4 border-t border-gray-800">
                    <div className="flex items-center justify-between text-sm text-gray-500">
                        <span>{projects.length} proyecto{projects.length !== 1 ? 's' : ''} disponible{projects.length !== 1 ? 's' : ''}</span>
                        <div className="flex items-center gap-4">
                            <button
                                onClick={clearAllProjects}
                                className="flex items-center gap-2 text-red-400 hover:text-red-300 transition-colors"
                            >
                                <Trash size={14} />
                                Limpiar todo
                            </button>
                            <button
                                onClick={loadProjects}
                                className="text-blue-400 hover:text-blue-300 transition-colors"
                            >
                                Actualizar lista
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {activeTab === "snippets" && (
                <div className="flex-1 flex flex-col min-h-0">
                    <div className="mb-4 flex items-center gap-2">
                        <div className="relative flex-1">
                            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
                            <input
                                value={snippetQuery}
                                onChange={(e) => setSnippetQuery(e.target.value)}
                                onKeyDown={(e) => {
                                    if (e.key === "Enter") {
                                        searchSnippets();
                                    }
                                }}
                                placeholder="Buscar por tipo, descripción o palabra clave..."
                                className="w-full bg-[#161616] border border-gray-800 rounded-xl py-2.5 pl-9 pr-4 text-sm text-white placeholder:text-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                            />
                        </div>
                        <button
                            onClick={() => searchSnippets()}
                            className="px-4 py-2.5 bg-blue-600/20 border border-blue-500/30 rounded-xl text-blue-300 text-sm hover:bg-blue-600/30 transition-colors"
                        >
                            Buscar
                        </button>
                    </div>
                    {snippetsError && (
                        <div className="mb-3 text-xs text-red-400 bg-red-600/10 border border-red-500/20 rounded-lg px-3 py-2">
                            {snippetsError}
                        </div>
                    )}

                    <div className="flex-1 overflow-y-auto pr-2 scrollbar-hide">
                        {loadingSnippets ? (
                            <p className="text-sm text-gray-500">Buscando snippets...</p>
                        ) : snippetResults.length === 0 ? (
                            <p className="text-sm text-gray-500">
                                Escribe un término y pulsa buscar para consultar tu librería.
                            </p>
                        ) : (
                            <div className="space-y-3">
                                {snippetResults.map((snippet) => (
                                    <div key={snippet.id} className="bg-[#161616] border border-gray-800 rounded-xl p-4">
                                        <div className="flex items-start justify-between gap-4 mb-2">
                                            <div>
                                                <p className="text-sm font-semibold text-white">{snippet.snippet_type}</p>
                                                <p className="text-xs text-gray-500">
                                                    {snippet.language}
                                                    {snippet.framework ? ` • ${snippet.framework}` : ""}
                                                    {` • usos: ${snippet.usage_count}`}
                                                </p>
                                            </div>
                                            <button
                                                onClick={() => reuseSnippet(snippet)}
                                                className="flex items-center gap-1 px-3 py-1.5 bg-blue-600/10 border border-blue-500/20 rounded-lg text-xs text-blue-300 hover:bg-blue-600/20 transition-colors"
                                                title="Inyectar snippet al chat"
                                            >
                                                <Copy size={12} />
                                                Usar código
                                            </button>
                                        </div>
                                        {snippet.description && (
                                            <p className="text-xs text-gray-400 mb-2">{snippet.description}</p>
                                        )}
                                        <pre className="text-xs text-gray-300 bg-[#0f0f0f] border border-gray-900 rounded-lg p-3 overflow-x-auto">
                                            {snippet.code_preview || snippet.code}
                                        </pre>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {activeTab === "history" && (
                <div className="flex-1 flex flex-col min-h-0">
                    <div className="mb-4 flex items-center gap-2">
                        <div className="relative flex-1">
                            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
                            <input
                                value={historyQuery}
                                onChange={(e) => setHistoryQuery(e.target.value)}
                                onKeyDown={(e) => {
                                    if (e.key === "Enter") {
                                        searchHistory();
                                    }
                                }}
                                placeholder='Buscar semánticamente (ej: "botón con animación")'
                                className="w-full bg-[#161616] border border-gray-800 rounded-xl py-2.5 pl-9 pr-4 text-sm text-white placeholder:text-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                            />
                        </div>
                        <button
                            onClick={() => searchHistory()}
                            className="px-4 py-2.5 bg-blue-600/20 border border-blue-500/30 rounded-xl text-blue-300 text-sm hover:bg-blue-600/30 transition-colors"
                        >
                            Buscar
                        </button>
                    </div>
                    {historyError && (
                        <div className="mb-3 text-xs text-red-400 bg-red-600/10 border border-red-500/20 rounded-lg px-3 py-2">
                            {historyError}
                        </div>
                    )}

                    <div className="flex-1 overflow-y-auto pr-2 scrollbar-hide">
                        {loadingHistory ? (
                            <p className="text-sm text-gray-500">Buscando en historial semántico...</p>
                        ) : historyResults.length === 0 ? (
                            <p className="text-sm text-gray-500">Sin resultados. Prueba con otra descripción.</p>
                        ) : (
                            <div className="space-y-3">
                                {historyResults.map((item) => (
                                    <div key={item.id} className="bg-[#161616] border border-gray-800 rounded-xl p-4">
                                        <div className="flex items-start justify-between gap-3 mb-2">
                                            <div>
                                                <p className="text-sm font-semibold text-white">
                                                    {item.metadata?.project_name || "Proyecto histórico"}
                                                </p>
                                                <p className="text-xs text-gray-500">
                                                    {item.metadata?.timestamp
                                                        ? new Date(item.metadata.timestamp).toLocaleString("es-ES")
                                                        : "Fecha no disponible"}
                                                    {typeof item.distance === "number" ? ` • distancia: ${item.distance.toFixed(3)}` : ""}
                                                </p>
                                            </div>
                                            <button
                                                onClick={() => reuseSnippet({
                                                    id: Number(item.id) || Date.now(),
                                                    snippet_type: "history",
                                                    language: "mixed",
                                                    code: item.document || "",
                                                    created_at: item.metadata?.timestamp || "",
                                                    usage_count: 0,
                                                    description: item.metadata?.description
                                                })}
                                                className="flex items-center gap-1 px-3 py-1.5 bg-blue-600/10 border border-blue-500/20 rounded-lg text-xs text-blue-300 hover:bg-blue-600/20 transition-colors"
                                            >
                                                <Copy size={12} />
                                                Reutilizar
                                            </button>
                                        </div>
                                        {item.metadata?.description && (
                                            <p className="text-xs text-gray-400 mb-2">{item.metadata.description}</p>
                                        )}
                                        <pre className="text-xs text-gray-300 bg-[#0f0f0f] border border-gray-900 rounded-lg p-3 overflow-x-auto">
                                            {item.document?.slice(0, 600)}
                                            {item.document && item.document.length > 600 ? "..." : ""}
                                        </pre>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {activeTab === "git" && (
                <div className="flex-1 flex flex-col min-h-0">
                    <div className="mb-4 flex items-center justify-between gap-2">
                        <p className="text-sm text-gray-400">Historial local de commits (snapshots automáticos).</p>
                        <div className="flex items-center gap-2">
                            <button
                                onClick={() => loadLaneMetrics()}
                                className="px-4 py-2 bg-indigo-600/20 border border-indigo-500/30 rounded-xl text-indigo-300 text-sm hover:bg-indigo-600/30 transition-colors"
                            >
                                LLM Lanes
                            </button>
                            <button
                                onClick={() => loadGitHistory(true)}
                                className="px-4 py-2 bg-blue-600/20 border border-blue-500/30 rounded-xl text-blue-300 text-sm hover:bg-blue-600/30 transition-colors"
                            >
                                Actualizar
                            </button>
                        </div>
                    </div>
                    {lanesError && (
                        <div className="mb-3 text-xs text-red-400 bg-red-600/10 border border-red-500/20 rounded-lg px-3 py-2">
                            {lanesError}
                        </div>
                    )}
                    {loadingLanes && (
                        <p className="text-xs text-gray-500 mb-3">Cargando métricas por lane...</p>
                    )}
                    {laneStats && (
                        <div className="mb-4 grid grid-cols-1 md:grid-cols-2 gap-3">
                            {(["realtime", "batch"] as const).map((lane) => (
                                <div key={lane} className="bg-[#161616] border border-gray-800 rounded-xl p-3">
                                    <p className="text-sm font-semibold text-white mb-2">{lane === "realtime" ? "Realtime Lane" : "Batch Lane"}</p>
                                    <div className="space-y-1 text-xs text-gray-400">
                                        <p>requests: <span className="text-gray-200">{laneStats[lane].requests}</span></p>
                                        <p>avg latency: <span className="text-gray-200">{laneStats[lane].avg_latency_ms} ms</span></p>
                                        <p>busy rate: <span className="text-gray-200">{(laneStats[lane].busy_rate * 100).toFixed(2)}%</span></p>
                                        <p>errors: <span className="text-gray-200">{laneStats[lane].errors}</span></p>
                                        <p>breaker: <span className="text-gray-200">{laneStats[lane].breaker_state}</span></p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                    {gitError && (
                        <div className="mb-3 text-xs text-red-400 bg-red-600/10 border border-red-500/20 rounded-lg px-3 py-2">
                            {gitError}
                        </div>
                    )}
                    <div className="flex-1 overflow-y-auto pr-2 scrollbar-hide">
                        {loadingGit ? (
                            <p className="text-sm text-gray-500">Cargando historial Git...</p>
                        ) : gitCommits.length === 0 ? (
                            <p className="text-sm text-gray-500">No hay commits para mostrar en el filtro actual.</p>
                        ) : (
                            <div className="space-y-2">
                                {gitCommits.map((commit) => (
                                    <button
                                        type="button"
                                        key={commit.hash}
                                        onClick={() => loadDiff(commit.hash)}
                                        className="w-full text-left bg-[#161616] border border-gray-800 rounded-xl p-3 hover:border-gray-700 transition-all cursor-pointer"
                                        title="Ver cambios del commit"
                                    >
                                        <p className="text-sm text-white font-medium">{commit.message}</p>
                                        <p className="text-xs text-gray-500 mt-1">
                                            {commit.hash.slice(0, 10)} • {new Date(commit.date).toLocaleString("es-ES")} • {commit.author}
                                        </p>
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {selectedCommitHash && (
                <>
                    <div
                        className="fixed inset-0 bg-black/50 z-40"
                        onClick={() => {
                            setSelectedCommitHash(null);
                            setDiffContent(null);
                            setDiffError(null);
                        }}
                    />
                    <div className="fixed inset-y-0 right-0 w-full md:w-1/2 bg-[#0f0f0f] border-l border-gray-800 shadow-2xl z-50 overflow-y-auto">
                        <div className="p-4">
                            <div className="flex items-center justify-between mb-4">
                                <div>
                                    <h4 className="text-lg font-semibold text-white">Diff del commit</h4>
                                    <p className="text-xs text-gray-500 mt-1">{selectedCommitHash}</p>
                                </div>
                                <button
                                    onClick={() => {
                                        setSelectedCommitHash(null);
                                        setDiffContent(null);
                                        setDiffError(null);
                                    }}
                                    className="text-gray-400 hover:text-white transition-colors"
                                    title="Cerrar panel de diff"
                                >
                                    <X size={18} />
                                </button>
                            </div>
                            {loadingDiff && <p className="text-gray-400 text-sm">Cargando diff...</p>}
                            {diffError && <p className="text-red-400 text-sm">{diffError}</p>}
                            {diffContent && (
                                <pre className="text-xs text-gray-300 bg-[#0a0a0a] border border-gray-900 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap">
                                    {diffContent}
                                </pre>
                            )}
                        </div>
                    </div>
                </>
            )}
        </div>
    );
}