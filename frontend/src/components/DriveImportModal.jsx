// frontend/src/components/DriveImportModal.jsx
import { useState, useEffect, useRef } from "react";
import {
  X,
  CloudLightning,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  RefreshCw,
  FolderSync
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useDriveIngest, useDriveIngestStatus } from "../hooks/useCandidates";

const POLL_INTERVAL = 4000; // ms

export default function DriveImportModal({ onClose }) {
  const qc = useQueryClient();
  const { mutate: triggerIngest, isPending: isIngesting } = useDriveIngest();
  const { data: statusData, refetch, isFetching } = useDriveIngestStatus({ refetchInterval: POLL_INTERVAL });
  
  const [lastRefresh, setLastRefresh] = useState(null);

  useEffect(() => {
    setLastRefresh(new Date());
  }, [statusData]);

  const isActive = statusData?.status === "processing";
  const isDone = statusData?.status === "completed";
  const hasError = statusData?.status === "failed";
  const isStopped = statusData?.status === "stopped";

  const total = statusData?.total_files || 0;
  const processed = statusData?.processed || 0;
  const skipped = statusData?.skipped || 0;
  const failed = statusData?.failed || 0;
  const remaining = statusData?.remaining || 0;
  
  // Total attempted so far
  const currentTotal = processed + skipped + failed;
  const progress = total > 0 ? Math.round(((total - remaining) / total) * 100) : 0;

  const handleStart = () => {
    triggerIngest();
  };

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
        <div className="pointer-events-none absolute -top-16 -right-16 w-48 h-48 bg-blue-400/10 rounded-full blur-3xl" />
        <div className="pointer-events-none absolute -bottom-16 -left-16 w-48 h-48 bg-indigo-400/10 rounded-full blur-3xl" />

        {/* HEADER */}
        <div className="flex items-start justify-between px-6 pt-6 pb-5 border-b border-gray-100 shrink-0">
          <div className="flex items-start gap-4">
            <div className="p-3 rounded-2xl bg-blue-100">
              <FolderSync size={20} className="text-blue-600" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-gray-900">Importation Drive</h2>
              <p className="text-sm text-gray-500 mt-0.5">
                Importation des CVs depuis Google Drive vers la base de données
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => refetch()}
              className="p-2 rounded-xl text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
              title="Rafraîchir"
            >
              <RefreshCw size={16} className={isFetching ? "animate-spin" : ""} />
            </button>
            <button
              onClick={onClose}
              className="p-2 rounded-xl text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* BODY */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
          {!isActive && !isDone && !hasError && !isStopped && (
             <div className="py-8 flex flex-col items-center gap-4 text-center">
               <div className="p-4 bg-blue-50 rounded-full">
                 <CloudLightning size={32} className="text-blue-500" />
               </div>
               <div>
                 <h3 className="text-lg font-semibold text-gray-900">Prêt à importer</h3>
                 <p className="text-sm text-gray-500 max-w-sm mt-1">
                   Cette action va scanner votre Google Drive et importer les nouveaux CVs dans la file d'attente.
                 </p>
               </div>
               <button
                 onClick={handleStart}
                 disabled={isIngesting}
                 className="mt-2 px-6 py-2.5 bg-blue-600 text-white font-medium rounded-xl hover:bg-blue-700 transition-colors disabled:opacity-50 flex items-center gap-2"
               >
                 {isIngesting ? <Loader2 size={18} className="animate-spin" /> : <FolderSync size={18} />}
                 Lancer l'importation
               </button>
             </div>
          )}

          {(isActive || isDone || hasError || isStopped) && (
            <>
              {/* Message Banner */}
              <div className={`p-4 rounded-xl border ${
                isActive ? "bg-blue-50 border-blue-200 text-blue-700" :
                isDone ? "bg-emerald-50 border-emerald-200 text-emerald-700" :
                "bg-red-50 border-red-200 text-red-700"
              }`}>
                <div className="flex items-center gap-3">
                  {isActive && <Loader2 size={18} className="animate-spin shrink-0" />}
                  {isDone && <CheckCircle2 size={18} className="shrink-0" />}
                  {(hasError || isStopped) && <AlertTriangle size={18} className="shrink-0" />}
                  <p className="text-sm font-medium">{statusData?.message || "Statut inconnu"}</p>
                </div>
              </div>

              {/* Stats cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                  { label: "Total détecté", value: total, color: "text-gray-700", bg: "bg-gray-50", border: "border-gray-200" },
                  { label: "Importés",     value: processed, color: "text-blue-700", bg: "bg-blue-50", border: "border-blue-200" },
                  { label: "Doublons",     value: skipped,   color: "text-amber-600", bg: "bg-amber-50", border: "border-amber-200" },
                  { label: "Erreurs",      value: failed,    color: "text-red-600", bg: "bg-red-50", border: "border-red-200" },
                ].map((card) => (
                  <div key={card.label} className={`rounded-2xl border p-3 ${card.bg} ${card.border} text-center`}>
                    <p className={`text-2xl font-bold ${card.color}`}>{card.value}</p>
                    <p className="text-xs text-gray-500 mt-0.5">{card.label}</p>
                  </div>
                ))}
              </div>

              {/* Global progress bar */}
              <div>
                <div className="flex justify-between text-xs text-gray-500 mb-1.5">
                  <span>Progression globale</span>
                  <span className="font-semibold">{progress}%</span>
                </div>
                <div className="h-2.5 rounded-full bg-gray-200 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-700 ${
                      isDone
                        ? "bg-gradient-to-r from-emerald-500 to-teal-400"
                        : "bg-gradient-to-r from-blue-500 to-indigo-500"
                    }`}
                    style={{ width: `${progress}%` }}
                  />
                </div>
              </div>

              {(!isActive && !isDone) && (
                 <div className="flex justify-center pt-4">
                   <button
                     onClick={handleStart}
                     disabled={isIngesting}
                     className="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-xl hover:bg-blue-700 transition-colors disabled:opacity-50"
                   >
                     Relancer l'importation
                   </button>
                 </div>
              )}
            </>
          )}

          {/* Polling indicator */}
          <div className="flex items-center gap-2 text-[10px] text-gray-400">
            {isActive && <div className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />}
            <span>Mise à jour toutes les {POLL_INTERVAL / 1000}s</span>
            {lastRefresh && (
              <span className="ml-auto">Dernière MàJ : {formatTime(lastRefresh)}</span>
            )}
          </div>
        </div>

        {/* FOOTER */}
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
