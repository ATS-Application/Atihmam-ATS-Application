// frontend/src/components/UploadCVModal.jsx
// Modale dédiée au CHARGEMENT des CVs avec suivi en temps réel.

import { useState, useRef, useCallback } from "react";
import {
  X,
  Upload,
  FileText,
  Briefcase,
  CheckCircle2,
  XCircle,
  Loader2,
  AlertCircle,
  Plus,
} from "lucide-react";
import toast from "react-hot-toast";
import { useJobs } from "../hooks/useJobs";
import axiosClient from "../api/axiosClient";
import { useQueryClient } from "@tanstack/react-query";

// ─── File statuses ────────────────────────────────────────────────────────────
const STATUS = {
  PENDING:   "pending",
  UPLOADING: "uploading",
  SUCCESS:   "success",
  DUPLICATE: "duplicate",
  ERROR:     "error",
};

const STATUS_META = {
  [STATUS.PENDING]:   { color: "text-gray-400",    bg: "bg-gray-50",     border: "border-gray-100",    label: "En attente"  },
  [STATUS.UPLOADING]: { color: "text-blue-500",    bg: "bg-blue-50",     border: "border-blue-200",    label: "Chargement" },
  [STATUS.SUCCESS]:   { color: "text-emerald-600", bg: "bg-emerald-50",  border: "border-emerald-200", label: "Chargé"      },
  [STATUS.DUPLICATE]: { color: "text-amber-600",   bg: "bg-amber-50",    border: "border-amber-200",   label: "Doublon"     },
  [STATUS.ERROR]:     { color: "text-red-500",     bg: "bg-red-50",      border: "border-red-200",     label: "Erreur"      },
};

// ─── Helpers ──────────────────────────────────────────────────────────────────
const ALLOWED_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/msword",
  "image/png",
  "image/jpeg",
  "image/jpg",
  "image/webp",
];
const ALLOWED_EXT = [".pdf", ".docx", ".doc", ".png", ".jpeg", ".jpg", ".webp"];
const isValidFile = (f) => {
  if (ALLOWED_TYPES.includes(f.type)) return true;
  const ext = f.name.slice(f.name.lastIndexOf(".")).toLowerCase();
  return ALLOWED_EXT.includes(ext);
};
const formatSize = (bytes) =>
  bytes < 1024 * 1024
    ? `${(bytes / 1024).toFixed(0)} Ko`
    : `${(bytes / (1024 * 1024)).toFixed(2)} Mo`;

// ─── Component ────────────────────────────────────────────────────────────────
export default function UploadCVModal({ onClose }) {
  const [fileEntries, setFileEntries] = useState([]);
  const [jobId, setJobId]             = useState("");
  const [isDragging, setIsDragging]   = useState(false);
  const [isRunning, setIsRunning]     = useState(false);
  const [done, setDone]               = useState(false);

  const fileRef = useRef();
  const qc      = useQueryClient();
  const { data: jobs = [] } = useJobs();

  // ── Derived counts ──
  const total      = fileEntries.length;
  const uploaded   = fileEntries.filter(e => e.status === STATUS.SUCCESS).length;
  const duplicates = fileEntries.filter(e => e.status === STATUS.DUPLICATE).length;
  const errors     = fileEntries.filter(e => e.status === STATUS.ERROR).length;
  const uploading  = fileEntries.filter(e => e.status === STATUS.UPLOADING).length;

  // ── Add files ──
  const addFiles = useCallback((incoming) => {
    const valid   = incoming.filter(isValidFile);
    const invalid = incoming.length - valid.length;
    if (invalid > 0) toast.error(`${invalid} fichier(s) ignoré(s) — format non supporté`);
    setFileEntries(prev => {
      const existing = new Set(prev.map(e => e.file.name + e.file.size));
      const fresh = valid
        .filter(f => !existing.has(f.name + f.size))
        .map(f => ({ id: crypto.randomUUID(), file: f, status: STATUS.PENDING, progress: 0 }));
      return [...prev, ...fresh];
    });
  }, []);

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    addFiles(Array.from(e.dataTransfer.files || []));
  };

  const handleFileSelect = (e) => {
    addFiles(Array.from(e.target.files || []));
    e.target.value = "";
  };

  const removeEntry = (id) =>
    setFileEntries(prev => prev.filter(e => e.id !== id));

  const patchEntry = (id, patch) =>
    setFileEntries(prev => prev.map(e => e.id === id ? { ...e, ...patch } : e));

  // ── Upload one file ──
  const uploadOne = async (entry) => {
    patchEntry(entry.id, { status: STATUS.UPLOADING, progress: 0 });
    const formData = new FormData();
    formData.append("file", entry.file);
    if (jobId) formData.append("job_id", jobId);
    try {
      await axiosClient.post("/ingestion/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (ev) => {
          const pct = ev.total ? Math.round((ev.loaded / ev.total) * 100) : 0;
          patchEntry(entry.id, { progress: pct });
        },
      });
      patchEntry(entry.id, { status: STATUS.SUCCESS, progress: 100 });
    } catch (err) {
      if (err?.response?.status === 409) {
        patchEntry(entry.id, { status: STATUS.DUPLICATE, progress: 100 });
      } else {
        patchEntry(entry.id, { status: STATUS.ERROR, progress: 0 });
      }
    }
  };

  // ── Start uploads ──
  const handleSubmit = async () => {
    if (total === 0 || isRunning) return;
    setIsRunning(true);
    setDone(false);
    const pending = fileEntries.filter(e => e.status === STATUS.PENDING);
    await Promise.all(pending.map(uploadOne));
    setIsRunning(false);
    setDone(true);
    qc.invalidateQueries({ queryKey: ["candidates"] });
  };

  const progressColor = (status) => {
    if (status === STATUS.SUCCESS)   return "bg-emerald-500";
    if (status === STATUS.ERROR)     return "bg-red-400";
    if (status === STATUS.DUPLICATE) return "bg-amber-400";
    return "bg-blue-500";
  };

  const canSubmit = total > 0 && !isRunning && fileEntries.some(e => e.status === STATUS.PENDING);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div
        className="relative w-full max-w-xl rounded-3xl bg-white shadow-2xl border border-white/20 flex flex-col"
        style={{ maxHeight: "90vh" }}
      >
        <div className="pointer-events-none absolute -top-20 -right-20 w-56 h-56 bg-orange-400/10 rounded-full blur-3xl" />

        {/* HEADER */}
        <div className="flex items-start justify-between px-6 pt-6 pb-5 border-b border-gray-100 shrink-0">
          <div className="flex items-start gap-4">
            <div className="p-3 rounded-2xl bg-orange-100">
              <Upload size={20} className="text-orange-600" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-gray-900">Chargement des CV</h2>
              <p className="text-sm text-gray-500 mt-0.5">
                Importez vos fichiers — le traitement IA démarrera automatiquement
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* BODY */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">

          {/* Drop zone */}
          {!done && (
            <div
              onClick={() => !isRunning && fileRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); if (!isRunning) setIsDragging(true); }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              className={[
                "relative rounded-3xl border-2 border-dashed p-7 text-center transition-all duration-300",
                isRunning ? "cursor-default opacity-50" : "cursor-pointer",
                isDragging
                  ? "border-orange-500 bg-orange-50 scale-[1.01]"
                  : "border-gray-300 hover:border-orange-400 hover:bg-orange-50/40",
              ].join(" ")}
            >
              <input
                ref={fileRef}
                type="file"
                accept="application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/*"
                multiple
                className="hidden"
                onChange={handleFileSelect}
              />
              <div className="mx-auto w-14 h-14 rounded-2xl bg-orange-100 flex items-center justify-center mb-3">
                <Upload size={24} className="text-orange-600" />
              </div>
              <p className="text-sm font-semibold text-gray-700">
                Glissez vos CV ici ou{" "}
                <span className="text-orange-600 underline">parcourir</span>
              </p>
              <p className="text-xs text-gray-400 mt-1">PDF, Word, Images — max 10 Mo chacun</p>
            </div>
          )}

          {/* Compteur résumé */}
          {total > 0 && (
            <div className="flex items-center gap-2 flex-wrap">
              <span className="px-3 py-1.5 rounded-full bg-gray-100 text-xs font-semibold text-gray-600">
                {total} fichier{total > 1 ? "s" : ""}
              </span>
              {uploaded > 0 && (
                <span className="px-3 py-1.5 rounded-full bg-emerald-100 text-xs font-semibold text-emerald-700 flex items-center gap-1">
                  <CheckCircle2 size={12} /> {uploaded} chargé{uploaded > 1 ? "s" : ""}
                </span>
              )}
              {duplicates > 0 && (
                <span className="px-3 py-1.5 rounded-full bg-amber-100 text-xs font-semibold text-amber-700 flex items-center gap-1">
                  <AlertCircle size={12} /> {duplicates} doublon{duplicates > 1 ? "s" : ""}
                </span>
              )}
              {errors > 0 && (
                <span className="px-3 py-1.5 rounded-full bg-red-100 text-xs font-semibold text-red-600 flex items-center gap-1">
                  <XCircle size={12} /> {errors} erreur{errors > 1 ? "s" : ""}
                </span>
              )}
              {uploading > 0 && (
                <span className="px-3 py-1.5 rounded-full bg-blue-100 text-xs font-semibold text-blue-600 flex items-center gap-1">
                  <Loader2 size={12} className="animate-spin" /> {uploading} en cours
                </span>
              )}
            </div>
          )}

          {/* File list */}
          {total > 0 && (
            <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
              {fileEntries.map((entry) => {
                const meta = STATUS_META[entry.status];
                return (
                  <div
                    key={entry.id}
                    className={`relative rounded-2xl border p-3 transition-all ${meta.bg} ${meta.border}`}
                  >
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded-xl bg-white/70 shrink-0">
                        <FileText size={15} className={meta.color} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-semibold text-gray-800 truncate">{entry.file.name}</p>
                        <p className="text-[10px] text-gray-400">{formatSize(entry.file.size)}</p>
                      </div>
                      <span className={`text-[10px] font-bold uppercase tracking-wider shrink-0 ${meta.color}`}>
                        {entry.status === STATUS.UPLOADING ? `${entry.progress}%` : meta.label}
                      </span>
                      {entry.status === STATUS.SUCCESS   && <CheckCircle2 size={16} className="text-emerald-500 shrink-0" />}
                      {entry.status === STATUS.DUPLICATE && <AlertCircle  size={16} className="text-amber-500 shrink-0" />}
                      {entry.status === STATUS.ERROR     && <XCircle      size={16} className="text-red-500 shrink-0" />}
                      {entry.status === STATUS.UPLOADING && <Loader2      size={16} className="text-blue-500 animate-spin shrink-0" />}
                      {!isRunning && entry.status !== STATUS.UPLOADING && (
                        <button
                          onClick={() => removeEntry(entry.id)}
                          className="p-1 rounded-lg text-gray-300 hover:text-red-400 hover:bg-red-50 transition-colors shrink-0"
                        >
                          <X size={13} />
                        </button>
                      )}
                    </div>
                    {(entry.status === STATUS.UPLOADING || entry.status === STATUS.SUCCESS) && (
                      <div className="mt-2 h-1.5 rounded-full bg-gray-200 overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-300 ${progressColor(entry.status)}`}
                          style={{ width: `${entry.progress}%` }}
                        />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Ajouter d'autres */}
          {total > 0 && !done && !isRunning && (
            <button
              onClick={() => fileRef.current?.click()}
              className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-dashed border-gray-300 text-gray-500 text-xs font-semibold hover:border-orange-400 hover:text-orange-600 hover:bg-orange-50 transition-all"
            >
              <Plus size={13} /> Ajouter d'autres fichiers
            </button>
          )}

          {/* Job selector */}
          {!done && (
            <div>
              <label className="text-sm font-medium text-gray-700 mb-2 block">
                Associer à un poste{" "}
                <span className="text-gray-400 font-normal">(optionnel)</span>
              </label>
              <div className="relative">
                <Briefcase size={15} className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400" />
                <select
                  value={jobId}
                  onChange={(e) => setJobId(e.target.value)}
                  disabled={isRunning}
                  className="w-full h-11 pl-10 pr-4 rounded-2xl border border-gray-200 bg-white text-sm text-gray-700 outline-none focus:ring-4 focus:ring-orange-100 focus:border-orange-400 transition-all disabled:opacity-50"
                >
                  <option value="">— Aucun poste —</option>
                  {jobs.map((job) => (
                    <option key={job.id} value={job.id}>{job.title}</option>
                  ))}
                </select>
              </div>
            </div>
          )}

          {/* Success summary */}
          {done && (
            <div className="rounded-2xl bg-emerald-50 border border-emerald-200 p-5 text-center space-y-1">
              <CheckCircle2 size={32} className="mx-auto text-emerald-500 mb-2" />
              <p className="text-base font-bold text-emerald-800">
                {uploaded} CV chargé{uploaded > 1 ? "s" : ""} avec succès
              </p>
              {duplicates > 0 && (
                <p className="text-xs text-amber-600">{duplicates} doublon(s) ignoré(s)</p>
              )}
              {errors > 0 && (
                <p className="text-xs text-red-500">{errors} erreur(s) de chargement</p>
              )}
              <p className="text-xs text-emerald-600 mt-2">
                Le traitement IA a démarré en arrière-plan.
              </p>
            </div>
          )}
        </div>

        {/* FOOTER */}
        <div className="px-6 pb-6 pt-4 border-t border-gray-100 shrink-0 flex items-center justify-between gap-3">
          <button
            onClick={onClose}
            className="px-5 py-2.5 rounded-2xl border border-gray-200 bg-white text-sm font-medium text-gray-700 hover:bg-gray-50 hover:border-gray-300 transition-all"
          >
            {done ? "Fermer" : "Annuler"}
          </button>

          {!done ? (
            <button
              disabled={!canSubmit}
              onClick={handleSubmit}
              className="flex items-center gap-2 px-6 py-2.5 rounded-2xl bg-gradient-to-r from-orange-600 to-amber-500 text-white text-sm font-semibold shadow-md hover:shadow-xl transition-all duration-300 hover:-translate-y-0.5 active:scale-[0.98] disabled:opacity-60 disabled:cursor-not-allowed disabled:translate-y-0 disabled:hover:shadow-md"
            >
              {isRunning ? (
                <>
                  <Loader2 size={15} className="animate-spin" />
                  Chargement en cours…
                </>
              ) : (
                <>
                  <Upload size={15} />
                  Charger {total > 0 ? `${total} CV` : "les CV"}
                </>
              )}
            </button>
          ) : (
            <button
              onClick={() => { setFileEntries([]); setDone(false); setJobId(""); }}
              className="flex items-center gap-2 px-6 py-2.5 rounded-2xl border border-orange-300 text-orange-700 bg-orange-50 text-sm font-semibold hover:bg-orange-100 transition-all"
            >
              <Plus size={15} /> Charger d'autres CV
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
