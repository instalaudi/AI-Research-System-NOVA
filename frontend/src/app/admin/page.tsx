"use client";

import React, { useState, useEffect } from "react";
import { useAuth } from "@/lib/AuthContext";
import { apiFetch } from "@/lib/api";
import { 
  Shield, Users, Settings, Activity, User as UserIcon, 
  CheckCircle, XCircle, ShieldAlert, ChevronRight, 
  Cpu, HardDrive, Database as DbIcon, Zap, Clock 
} from "lucide-react";
import { useRouter } from "next/navigation";
import { 
  LineChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid, 
  Tooltip, ResponsiveContainer, BarChart, Bar, Cell 
} from "recharts";

// --- Tipos ---
interface UserInfo {
  id: number;
  username: string;
  email: string;
  is_admin: boolean;
  is_active: boolean;
}

interface EvolutionLog {
  id: number;
  filename: string;
  proposal_title: string;
  timestamp: string;
  status: string;
  score_internal?: number;
  confidence_score?: number;
}

interface SystemStats {
  knowledge_count: number;
  active_jobs: number;
  completed_jobs: number;
  uptime: string;
  hardware?: {
    cpu_usage: number;
    memory_percent: number;
    memory_used_gb: number;
  };
}

// --- Componentes Reutilizables ---
const StatCard = ({ title, value, icon: Icon, color }: any) => (
  <div className="bg-[#111] border border-gray-800/50 p-6 rounded-3xl shadow-xl hover:border-gray-700/50 transition-all">
    <div className={`flex items-center gap-3 mb-4 ${color}`}>
      <Icon size={20} />
      <span className="text-[10px] font-bold uppercase tracking-widest opacity-70">{title}</span>
    </div>
    <p className="text-4xl font-black tracking-tighter text-white">{value}</p>
  </div>
);

export default function AdminPage() {
  const { user, isLoading: authLoading } = useAuth();
  const router = useRouter();
  const [activeTab, setActiveTab] = useState("monitor");
  
  // Data State
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [logs, setLogs] = useState<EvolutionLog[]>([]);
  const [history, setHistory] = useState<any[]>([]);
  
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  // Edit State
  const [isEditing, setIsEditing] = useState<UserInfo | null>(null);
  const [editForm, setEditForm] = useState({ username: "", email: "", password: "" });

  useEffect(() => {
    if (!authLoading) {
      if (!user || !user.is_admin) {
        router.push("/");
        return;
      }
      initialLoad();
      const interval = setInterval(refreshTelemetry, 5000);
      return () => clearInterval(interval);
    }
  }, [authLoading, user, router]);

  const initialLoad = async () => {
    setIsLoading(true);
    await Promise.all([fetchUsers(), fetchLogs(), refreshTelemetry()]);
    setIsLoading(false);
  };

  const fetchUsers = async () => {
    try {
      const res = await apiFetch("/admin/users");
      if (res.ok) setUsers(await res.json());
      else if (res.status === 403) setError("Acceso denegado: Se requiere Nivel Admin.");
    } catch (e) { setError("Error de conexión con el núcleo."); }
  };

  const fetchLogs = async () => {
    try {
      const res = await apiFetch("/nova/logs");
      if (res.ok) setLogs(await res.json());
    } catch (e) { console.error("Logs error", e); }
  };

  const refreshTelemetry = async () => {
    try {
      const res = await apiFetch("/metrics");
      if (res.ok) {
        const raw = await res.json();
        const data: SystemStats = {
          knowledge_count: raw.knowledge?.total_articles || 0,
          active_jobs: raw.knowledge?.tasks?.in_progress || 0,
          completed_jobs: raw.knowledge?.tasks?.completed || 0,
          uptime: raw.uptime?.uptime_human || "0s",
          hardware: raw.hardware || { cpu_usage: 0, memory_percent: 0, memory_used_gb: 0 }
        };
        setStats(data);
        setHistory(prev => {
          const newPoint = {
            time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
            cpu: data.hardware?.cpu_usage || 0,
            ram: data.hardware?.memory_percent || 0
          };
          return [...prev.slice(-19), newPoint];
        });
      }
    } catch (e) { console.error("Telemetry error", e); }
  };

  // --- Acciones de Usuario ---
  const toggleAdmin = async (userId: number) => {
    const res = await apiFetch(`/admin/users/${userId}/toggle-admin`, { method: "POST" });
    if (res.ok) fetchUsers();
  };

  const handleDelete = async (userId: number) => {
    if (confirm("¿Confirmar eliminación permanente?")) {
      const res = await apiFetch(`/admin/users/${userId}`, { method: "DELETE" });
      if (res.ok) fetchUsers();
    }
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isEditing) return;
    const res = await apiFetch(`/admin/users/${isEditing.id}`, { method: "PUT", json: editForm });
    if (res.ok) { setIsEditing(null); fetchUsers(); }
  };

  if (authLoading || isLoading) return (
    <div className="h-screen bg-[#0a0a0a] flex items-center justify-center">
      <div className="w-16 h-16 border-4 border-blue-600/20 border-t-blue-600 rounded-full animate-spin" />
    </div>
  );

  if (error) return (
    <div className="h-screen bg-[#0a0a0a] flex flex-col items-center justify-center p-8 text-center">
      <ShieldAlert size={80} className="text-red-500 mb-8 animate-pulse" />
      <h1 className="text-4xl font-black text-white mb-4 uppercase tracking-tighter">Acceso Restringido</h1>
      <p className="text-gray-500 max-w-md mb-10 text-lg leading-relaxed">{error}</p>
      <button onClick={() => router.push("/")} className="bg-white text-black font-bold px-10 py-4 rounded-2xl hover:bg-gray-200 transition-all">Regresar</button>
    </div>
  );

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-gray-100 font-sans selection:bg-blue-500/30">
      <div className="max-w-[1400px] mx-auto p-6 lg:p-10">
        
        {/* Header Section */}
        <header className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-12">
          <div className="flex items-center gap-5">
            <div className="w-14 h-14 bg-gradient-to-br from-blue-600 to-indigo-700 rounded-2xl flex items-center justify-center shadow-2xl shadow-blue-900/40 relative group">
              <Shield className="text-white group-hover:scale-110 transition-transform" size={28} />
              <div className="absolute inset-0 bg-white/20 rounded-2xl animate-pulse" />
            </div>
            <div>
              <h1 className="text-4xl font-black tracking-tight text-white flex items-center gap-2">
                NOVA <span className="text-blue-500 text-sm font-mono tracking-widest bg-blue-500/10 px-2 py-0.5 rounded border border-blue-500/20">CORE ADMIN</span>
              </h1>
              <p className="text-gray-500 text-sm font-medium mt-1">Soberanía de Inteligencia Artificial • Dashboard v10.7.6</p>
            </div>
          </div>
          
          <div className="flex items-center gap-3 bg-[#111] p-1.5 rounded-2xl border border-gray-800">
            {["monitor", "evolucion", "usuarios"].map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-6 py-2.5 rounded-xl text-xs font-black uppercase tracking-widest transition-all ${
                  activeTab === tab 
                  ? "bg-blue-600 text-white shadow-lg shadow-blue-600/20" 
                  : "text-gray-500 hover:text-gray-300 hover:bg-gray-800"
                }`}
              >
                {tab === "monitor" ? "Monitor" : tab === "evolucion" ? "Cronograma" : "Agentes"}
              </button>
            ))}
          </div>

          <button onClick={() => router.push("/")} className="hidden lg:flex items-center gap-2 text-gray-400 hover:text-white transition-colors font-bold text-sm">
            Cerrar Terminal <ChevronRight size={18} />
          </button>
        </header>

        {/* --- Tab Content: MONITOR --- */}
        {activeTab === "monitor" && (
          <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            {/* Quick Stats */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
              <StatCard title="Conocimiento" value={stats?.knowledge_count || 0} icon={DbIcon} color="text-amber-400" />
              <StatCard title="Tareas Activas" value={stats?.active_jobs || 0} icon={Zap} color="text-blue-400" />
              <StatCard title="Uso CPU" value={`${stats?.hardware?.cpu_usage?.toFixed(1) || 0}%`} icon={Cpu} color="text-emerald-400" />
              <StatCard title="Uso RAM" value={`${stats?.hardware?.memory_percent?.toFixed(1) || 0}%`} icon={HardDrive} color="text-purple-400" />
            </div>

            {/* Charts Section */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              <div className="bg-[#111] border border-gray-800 p-8 rounded-[2.5rem] shadow-2xl">
                <div className="flex items-center justify-between mb-8">
                  <h3 className="text-lg font-bold flex items-center gap-3">
                    <Activity className="text-blue-500" size={20} /> Telemetría en Vivo (Hardware)
                  </h3>
                  <div className="flex gap-4 text-[10px] font-bold uppercase tracking-widest">
                    <span className="flex items-center gap-1.5 text-emerald-400"><div className="w-2 h-2 rounded-full bg-emerald-500" /> CPU</span>
                    <span className="flex items-center gap-1.5 text-blue-400"><div className="w-2 h-2 rounded-full bg-blue-500" /> RAM</span>
                  </div>
                </div>
                <div className="h-[300px] w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={history}>
                      <defs>
                        <linearGradient id="colorCpu" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#10b981" stopOpacity={0.3}/>
                          <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                        </linearGradient>
                        <linearGradient id="colorRam" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
                          <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#222" vertical={false} />
                      <XAxis dataKey="time" hide />
                      <YAxis stroke="#444" fontSize={10} domain={[0, 100]} />
                      <Tooltip contentStyle={{ backgroundColor: '#111', border: '1px solid #333', borderRadius: '12px', fontSize: '12px' }} />
                      <Area type="monotone" dataKey="cpu" stroke="#10b981" fillOpacity={1} fill="url(#colorCpu)" strokeWidth={3} />
                      <Area type="monotone" dataKey="ram" stroke="#3b82f6" fillOpacity={1} fill="url(#colorRam)" strokeWidth={3} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="bg-[#111] border border-gray-800 p-8 rounded-[2.5rem] shadow-2xl">
                <h3 className="text-lg font-bold flex items-center gap-3 mb-8">
                  <Clock className="text-amber-500" size={20} /> Rendimiento de Tareas
                </h3>
                <div className="h-[300px] w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={[
                      { name: 'Activas', val: stats?.active_jobs || 0 },
                      { name: 'Completadas', val: stats?.completed_jobs || 0 }
                    ]}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#222" vertical={false} />
                      <XAxis dataKey="name" stroke="#555" fontSize={12} fontVariant="bold" />
                      <YAxis stroke="#444" fontSize={10} />
                      <Tooltip cursor={{fill: '#222'}} contentStyle={{ backgroundColor: '#111', border: '1px solid #333', borderRadius: '12px' }} />
                      <Bar dataKey="val" radius={[8, 8, 0, 0]}>
                        <Cell fill="#3b82f6" />
                        <Cell fill="#10b981" />
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* --- Tab Content: EVOLUCION --- */}
        {activeTab === "evolucion" && (
          <div className="bg-[#111] border border-gray-800 rounded-[2.5rem] overflow-hidden shadow-2xl animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="p-8 border-b border-gray-800 bg-gray-900/40 backdrop-blur-xl flex items-center justify-between">
              <h2 className="text-xl font-bold flex items-center gap-3 text-white">
                <Clock size={22} className="text-amber-500" /> Log de Auditoría Evolutiva
              </h2>
            </div>
            <div className="max-h-[600px] overflow-y-auto">
              <table className="w-full text-left">
                <thead className="sticky top-0 bg-[#111] z-10">
                  <tr className="border-b border-gray-800 text-[10px] font-bold text-gray-500 uppercase tracking-[0.2em]">
                    <th className="px-8 py-4">Sello de Tiempo</th>
                    <th className="px-8 py-4">Operación</th>
                    <th className="px-8 py-4">Descripción Genómica</th>
                    <th className="px-8 py-4 text-center">Estatus</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800/40">
                  {logs.map((log) => (
                    <tr key={log.id} className="hover:bg-white/[0.02] transition-colors">
                      <td className="px-8 py-5 text-xs text-gray-500 font-mono">
                        {new Date(log.timestamp).toLocaleString('es-LA')}
                      </td>
                      <td className="px-8 py-5">
                        <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-[9px] font-black uppercase tracking-widest bg-gray-800/50 text-gray-400 border border-gray-700/50">
                          {log.filename || "MODULE"}
                        </span>
                      </td>
                      <td className="px-8 py-5 text-sm text-gray-300 font-medium">{log.proposal_title || log.status}</td>
                      <td className="px-8 py-5 text-center">
                        <span className={`inline-flex items-center gap-1 text-[10px] font-black uppercase ${
                          log.status === "SUCCESS" || log.status === "APPLIED" ? "text-emerald-500" : "text-amber-500"
                        }`}>
                          {log.status === "SUCCESS" || log.status === "APPLIED" ? <CheckCircle size={14} /> : <Activity size={14} />}
                          {log.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                  {logs.length === 0 && (
                    <tr>
                      <td colSpan={4} className="px-8 py-20 text-center text-gray-600 font-medium italic">
                        No se han registrado secuencias de evolución todavía.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* --- Tab Content: USUARIOS --- */}
        {activeTab === "usuarios" && (
          <div className="bg-[#111] border border-gray-800 rounded-[2.5rem] overflow-hidden shadow-2xl animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="p-8 border-b border-gray-800 bg-gray-900/40 backdrop-blur-xl">
              <h2 className="text-xl font-bold flex items-center gap-3 text-white">
                <Users size={22} className="text-blue-500" /> Control de Acceso de Agentes
              </h2>
            </div>
            
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-gray-800 text-[10px] font-bold text-gray-500 uppercase tracking-[0.2em]">
                    <th className="px-8 py-5">Identidad</th>
                    <th className="px-8 py-5">Contacto Intelectual</th>
                    <th className="px-8 py-5">Capacidad Nivel</th>
                    <th className="px-8 py-5 text-right">Comandos</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800/30">
                  {users.map((u) => (
                    <tr key={u.id} className="hover:bg-white/[0.02] group transition-all">
                      <td className="px-8 py-6">
                        <div className="flex items-center gap-4">
                          <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${u.is_admin ? 'bg-blue-600' : 'bg-gray-800 text-gray-600'}`}>
                            <UserIcon size={18} />
                          </div>
                          <div>
                            <p className="font-bold text-white tracking-tight">{u.username}</p>
                            <p className="text-[9px] text-gray-600 font-black tracking-widest uppercase">ID_TX_{u.id}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-8 py-6 text-sm text-gray-500 font-mono italic">{u.email}</td>
                      <td className="px-8 py-6">
                        <div className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-[9px] font-black uppercase border ${
                          u.is_admin ? "bg-blue-500/10 text-blue-400 border-blue-500/20" : "bg-gray-800/50 text-gray-500 border-gray-700/50"
                        }`}>
                          {u.is_admin ? <Shield size={10} /> : <UserIcon size={10} />}
                          {u.is_admin ? "System Admin" : "External Agent"}
                        </div>
                      </td>
                      <td className="px-8 py-6 text-right">
                        <div className="flex items-center justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button 
                            onClick={() => { setIsEditing(u); setEditForm({ username: u.username, email: u.email, password: "" }); }}
                            aria-label="Editar Usuario"
                            className="p-2 hover:bg-white/5 rounded-lg text-gray-400 hover:text-white"
                          ><Settings size={16} /></button>
                          <button 
                            onClick={() => toggleAdmin(u.id)}
                            disabled={u.username === user?.username}
                            aria-label={u.is_admin ? "Quitar Privilegios" : "Hacer Admin"}
                            className={`p-2 rounded-lg disabled:hidden ${u.is_admin ? 'text-amber-500 hover:bg-amber-500/10' : 'text-blue-500 hover:bg-blue-500/10'}`}
                          >{u.is_admin ? <ShieldAlert size={16} /> : <Shield size={16} />}</button>
                          <button 
                            onClick={() => handleDelete(u.id)}
                            disabled={u.username === user?.username}
                            aria-label="Eliminar Agente"
                            className="p-2 hover:bg-red-500/10 text-red-500 rounded-lg disabled:hidden"
                          ><XCircle size={16} /></button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Edit Modal (Glassmorphism) */}
      {isEditing && (
        <div className="fixed inset-0 bg-black/90 backdrop-blur-xl z-[100] flex items-center justify-center p-4">
          <div className="bg-[#111] border border-gray-800 rounded-[2.5rem] w-full max-w-lg overflow-hidden shadow-2xl animate-in zoom-in-95 duration-200">
            <div className="p-10 border-b border-gray-800 bg-gray-900/40 flex justify-between items-center">
              <div>
                <h3 className="text-2xl font-black text-white tracking-widest uppercase">Modificar Perfil</h3>
                <p className="text-xs text-blue-500 font-bold mt-1 uppercase tracking-widest">{isEditing.username}</p>
              </div>
              <button onClick={() => setIsEditing(null)} aria-label="Cerrar Modal" className="p-2 text-gray-500 hover:text-white"><XCircle size={32} /></button>
            </div>
            <form onSubmit={handleEditSubmit} className="p-10 space-y-8">
              <div className="space-y-3">
                <label htmlFor="edit-username" className="text-[10px] font-black text-gray-600 uppercase tracking-widest ml-1">Alias de Sistema</label>
                <input 
                  id="edit-username"
                  type="text"
                  placeholder="Nombre de agente"
                  value={editForm.username}
                  onChange={(e) => setEditForm({...editForm, username: e.target.value})}
                  className="w-full bg-[#0a0a0a] border border-gray-800 rounded-2xl py-5 px-8 focus:outline-none focus:border-blue-500 transition-all text-white font-medium"
                />
              </div>
              <div className="space-y-3">
                <label htmlFor="edit-email" className="text-[10px] font-black text-gray-600 uppercase tracking-widest ml-1">Protocolo Email</label>
                <input 
                  id="edit-email"
                  type="email"
                  placeholder="correo@ejemplo.com"
                  value={editForm.email}
                  onChange={(e) => setEditForm({...editForm, email: e.target.value})}
                  className="w-full bg-[#0a0a0a] border border-gray-800 rounded-2xl py-5 px-8 focus:outline-none focus:border-blue-500 transition-all text-white font-medium"
                />
              </div>
              <div className="space-y-3">
                <label className="text-[10px] font-black text-gray-600 uppercase tracking-widest ml-1">Nueva Clave de Acceso (Encriptada)</label>
                <input 
                  type="password"
                  value={editForm.password}
                  onChange={(e) => setEditForm({...editForm, password: e.target.value})}
                  placeholder="Mantener constante si no se altera"
                  className="w-full bg-[#0a0a0a] border border-gray-800 rounded-2xl py-5 px-8 focus:outline-none focus:border-blue-500 transition-all text-white font-medium"
                />
              </div>
              <button type="submit" className="w-full py-6 bg-blue-600 hover:bg-blue-500 text-white rounded-2xl font-black uppercase tracking-[0.2em] text-xs shadow-2xl shadow-blue-900/20 transition-all active:scale-[0.98]">
                Ejecutar Actualización
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
