// frontend/src/components/AIProcessingModal.jsx
// Modale dédiée au suivi du TRAITEMENT IA des candidats.

import { useState, useEffect, useRef } from "react";
import {
  X,
  Sparkles,
  Brain,
  CheckCircle2,
  Clock,
  AlertTriangle,
  Loader2,
  RefreshCw,
  ChevronRight,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import axiosClient from "../api/axiosClient";
import { useAIProcessing, useAIProcessingStatus } from "../hooks/useCandidates";

// ─── Constants ────────────────────────────────────────────────────────────────
const POLL_INTERVAL = 4000; // ms

const PROC_META = {
  queued: {
    color: "text-amber-600",
    bg: "bg-amber-50",
    border: "border-amber-200",
    icon: Clock,
    label: "En file",
  },
  processing: {
    color: "text-blue-600",
    bg: "bg-blue-50",
    border: "border-blue-200",
    icon: Loader2,
    label: "En cours",
    spin: true,
  },
  done: {
    color: "text-emerald-600",
    bg: "bg-emerald-50",
    border: "border-emerald-200",
    icon: CheckCircle2,
    label: "Traité",
  },
  error: {
    color: "text-red-500",
    bg: "bg-red-50",
    border: "border-red-200",
    icon: AlertTriangle,
    label: "Erreur",
  },
  skipped: {
    color: "text-gray-400",
    bg: "bg-gray-50",
    border: "border-gray-100",
    icon: ChevronRight,
    label: "Ignoré",
  },
};

const getFallback = (status) => PROC_META[status] ?? PROC_META.queued;

// ─── Component ────────────────────────────────────────────────────────────────
export default function AIProcessingModal({ onClose }) {
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);
  const [lastRefresh, setLastRefresh] = useState(null);
  const intervalRef = useRef(null);
  const qc = useQueryClient();

  const { mutate: triggerAI, isPending: isTriggering } = useAIProcessing();
  const { data: statusData, refetch: refetchStatus } = useAIProcessingStatus({ refetchInterval: POLL_INTERVAL });

  // ── Fetch candidates with a processing status ──────────────────────────────
  const fetchData = async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const res = await axiosClient.get("/candidates", {
        params: { limit: 50, order: "created_at.desc" },
      });
      const all = Array.isArray(res.data?.items) ? res.data.items
                : Array.isArray(res.data)        ? res.data
                : [];
      // Keep all candidates that ever had an AI processing status
      const relevant = all.filter(
        (c) => c.processing_status && c.processing_status !== "none"
      );
      setCandidates(relevant);
      setLastRefresh(new Date());
    } catch (err) {
      setError("Impossible de récupérer les candidats.");
    } finally {
      setLoading(false);
    }
  };

  // ── Auto-poll every POLL_INTERVAL ms ──────────────────────────────────────
  useEffect(() => {
    fetchData();
    intervalRef.current = setInterval(() => fetchData(true), POLL_INTERVAL);
    return () => clearInterval(intervalRef.current);
  }, []);

  // ── Derived stats ──────────────────────────────────────────────────────────
  const total      = candidates.length;
  const done       = candidates.filter(c => c.processing_status === "done").length;
  const processing = candidates.filter(c => c.processing_status === "processing").length;
  const queued     = candidates.filter(c => c.processing_status === "queued").length;
  const errors     = candidates.filter(c => c.processing_status === "error").length;
  const allDone    = total > 0 && (done + errors) === total;
  const progress   = total > 0 ? Math.round(((done + errors) / total) * 100) : 0;

  const formatTime = (date) => {
    if (!date) return "—";
    return date.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div
        className="relative w-full max-w-2xl rounded-3xl bg-white shadow-2xl border border-white/20 flex flex-col"
        style={{ maxHeight: "90vh" }}
      >
        {/* Glow */}
        <div className="pointer-events-none absolute -top-16 -right-16 w-48 h-48 bg-indigo-400/10 rounded-full blur-3xl" />
        <div className="pointer-events-none absolute -bottom-16 -left-16 w-48 h-48 bg-violet-400/10 rounded-full blur-3xl" />

        {/* ── HEADER ── */}
        <div className="flex items-start justify-between px-6 pt-6 pb-5 border-b border-gray-100 shrink-0">
          <div className="flex items-start gap-4">
            <div className="p-3 rounded-2xl bg-indigo-100">
              <Brain size={20} className="text-indigo-600" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-gray-900">Traitement IA</h2>
              <p className="text-sm text-gray-500 mt-0.5">
                Suivi de l'analyse et du scoring des candidats par l'IA
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => { fetchData(); refetchStatus(); }}
              className="p-2 rounded-xl text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors"
              title="Rafraîchir"
            >
              <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
            </button>
            <button
              onClick={onClose}
              className="p-2 rounded-xl text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* ── BODY ── */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">

          {/* Stats cards */}
          {total > 0 && (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                  { label: "Total", value: total, color: "text-gray-700", bg: "bg-gray-50", border: "border-gray-200" },
                  { label: "Traités",     value: done,       color: "text-emerald-700", bg: "bg-emerald-50", border: "border-emerald-200" },
                  { label: "En cours",   value: processing + queued, color: "text-blue-700", bg: "bg-blue-50", border: "border-blue-200" },
                  { label: "Erreurs",    value: errors,     color: "text-red-600",     bg: "bg-red-50",     border: "border-red-200"     },
                ].map((card) => (
                  <div key={card.label} className={`rounded-2xl border p-3 ${card.bg} ${card.border} text-center`}>
                    <p className={`text-2xl font-bold ${card.color}`}>{card.value}</p>
                    <p className="text-xs text-gray-500 mt-0.5">{card.label}</p>
                  </div>
                ))}
              </div>

              {queued > 0 && statusData?.status !== "processing" && (
                <div className="flex justify-center mt-2 mb-4">
                  <button
                    onClick={() => triggerAI()}
                    disabled={isTriggering}
                    className="px-6 py-2.5 bg-indigo-600 text-white font-medium rounded-xl hover:bg-indigo-700 transition-colors disabled:opacity-50 flex items-center gap-2"
                  >
                    {isTriggering ? <Loader2 size={18} className="animate-spin" /> : <Brain size={18} />}
                    Lancer l'analyse IA ({queued} en attente)
                  </button>
                </div>
              )}

              {statusData?.status === "processing" && (
                <div className="p-4 rounded-xl border bg-blue-50 border-blue-200 text-blue-700 mt-2 mb-4">
                  <div className="flex items-center gap-3">
                    <Loader2 size={18} className="animate-spin shrink-0" />
                    <p className="text-sm font-medium">{statusData?.message || "Traitement en cours..."}</p>
                  </div>
                </div>
              )}
              {statusData?.status === "completed" && statusData?.processed > 0 && (
                <div className="p-4 rounded-xl border bg-emerald-50 border-emerald-200 text-emerald-700 mt-2 mb-4">
                  <div className="flex items-center gap-3">
                    <CheckCircle2 size={18} className="shrink-0" />
                    <p className="text-sm font-medium">{statusData?.message || "Traitement terminé."}</p>
                  </div>
                </div>
              )}

              {/* Global progress bar */}
              <div>
                <div className="flex justify-between text-xs text-gray-500 mb-1.5">
                  <span>Progression globale</span>
                  <span className="font-semibold">{progress}%</span>
                </div>
                <div className="h-2.5 rounded-full bg-gray-200 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-700 ${
                      allDone && errors === 0
                        ? "bg-gradient-to-r from-emerald-500 to-teal-400"
                        : "bg-gradient-to-r from-indigo-500 to-violet-500"
                    }`}
                    style={{ width: `${progress}%` }}
                  />
                </div>
                {allDone && (
                  <p className="text-xs text-emerald-600 font-semibold mt-1.5 flex items-center gap-1">
                    <CheckCircle2 size={12} /> Traitement terminé
                  </p>
                )}
              </div>
            </>
          )}

          {/* Loading state */}
          {loading && candidates.length === 0 && (
            <div className="py-16 flex flex-col items-center gap-3 text-gray-400">
              <Loader2 size={28} className="animate-spin text-indigo-400" />
              <p className="text-sm">Chargement des données…</p>
            </div>
          )}

          {/* Error state */}
          {error && (
            <div className="rounded-2xl bg-red-50 border border-red-200 p-4 flex items-center gap-3">
              <AlertTriangle size={18} className="text-red-500 shrink-0" />
              <p className="text-sm text-red-600">{error}</p>
            </div>
          )}

          {/* Empty state */}
          {!loading && !error && total === 0 && (
            <div className="py-16 flex flex-col items-center gap-3 text-gray-400">
              <Sparkles size={32} className="text-indigo-300" />
              <p className="text-sm font-medium">Aucun candidat en cours de traitement</p>
              <p className="text-xs text-gray-400">Chargez des CV pour démarrer l'analyse IA</p>
            </div>
          )}

          {/* Candidate list */}
          {total > 0 && (
            <div className="space-y-2">
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                Candidats ({total})
              </h3>
              <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                {candidates.map((c) => {
                  const meta = getFallback(c.processing_status);
                  const Icon = meta.icon;
                  const name = c.full_name || c.name || `Candidat #${c.id?.slice(0, 6)}`;
                  return (
                    <div
                      key={c.id}
                      className={`rounded-2xl border p-3 flex items-center gap-3 transition-all ${meta.bg} ${meta.border}`}
                    >
                      <div className={`p-2 rounded-xl bg-white/70 shrink-0`}>
                        <Icon
                          size={15}
                          className={`${meta.color} ${meta.spin ? "animate-spin" : ""}`}
                        />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-semibold text-gray-800 truncate">{name}</p>
                        {c.job_title && (
                          <p className="text-[10px] text-gray-400 truncate">{c.job_title}</p>
                        )}
                      </div>
                      <div className="text-right shrink-0">
                        <span className={`text-[10px] font-bold uppercase tracking-wider ${meta.color}`}>
                          {meta.label}
                        </span>
                        {c.ai_score != null && (
                          <p className="text-[10px] text-indigo-600 font-semibold">
                            Score: {c.ai_score}
                          </p>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Polling indicator */}
          <div className="flex items-center gap-2 text-[10px] text-gray-400">
            <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span>Mise à jour automatique toutes les {POLL_INTERVAL / 1000}s</span>
            {lastRefresh && (
              <span className="ml-auto">Dernière MàJ : {formatTime(lastRefresh)}</span>
            )}
          </div>
        </div>

        {/* ── FOOTER ── */}
        <div className="px-6 pb-6 pt-4 border-t border-gray-100 shrink-0 flex justify-end">
          <button
            onClick={onClose}
            className="px-5 py-2.5 rounded-2xl border border-gray-200 bg-white text-sm font-medium text-gray-700 hover:bg-gray-50 hover:border-gray-300 transition-all"
          >
            Fermer
          </button>
        </div>
      </div>
    </div>
  );
}
