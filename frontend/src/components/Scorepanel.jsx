// src/components/ScorePanel.jsx

import { useMemo, useState } from "react";
import {
  ThumbsUp,
  ThumbsDown,
  Zap,
  Target,
  Briefcase,
  FolderOpen,
  TrendingUp,
  CheckCircle2,
  XCircle,
  Info,
  Layers,
  Brain,
  Sparkles,
  AlertTriangle,
  Clock,
} from "lucide-react";
import toast from "react-hot-toast";
import axiosClient from "../api/axiosClient";

// ─────────────────────────────────────────────────────────────
// Dimension metadata
// ─────────────────────────────────────────────────────────────

const DIMENSIONS = [
  {
    key: "keyword_score",
    label: "Match mots-clés",
    icon: Target,
    accent: "#f97316",
    track: "#fff7ed",
    description: "Correspondance sémantique avec la fiche de poste",
  },
  {
    key: "semantic_score",
    label: "Profondeur compétences",
    icon: Zap,
    accent: "#8b5cf6",
    track: "#f5f3ff",
    description: "Niveau réel des compétences détectées (ecosystèmes, séniorité)",
  },
  {
    key: "experience_score",
    label: "Expérience",
    icon: Briefcase,
    accent: "#3b82f6",
    track: "#eff6ff",
    description: "Années d'expérience professionnelle non-chevauchantes",
  },
  {
    key: "project_complexity_score",
    label: "Qualité projets",
    icon: FolderOpen,
    accent: "#10b981",
    track: "#ecfdf5",
    description: "Diversité, complexité et unicité des projets (pénalité doublons)",
  },
  {
    key: "education_score",
    label: "Progression carrière",
    icon: TrendingUp,
    accent: "#ec4899",
    track: "#fdf2f8",
    description: "Niveau d'études et trajectoire académique détectés",
  },
];

// ─────────────────────────────────────────────────────────────
// Safe helpers — handle string-serialized JSON from the backend
// ─────────────────────────────────────────────────────────────

function safeParse(value) {
  if (!value) return {};
  if (typeof value === "string") {
    try { return JSON.parse(value); } catch { return {}; }
  }
  return typeof value === "object" && !Array.isArray(value) ? value : {};
}

function safeParseArray(value) {
  if (Array.isArray(value)) return value;
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : [];
    } catch { return []; }
  }
  return [];
}

// ─────────────────────────────────────────────────────────────
// Score ring
// ─────────────────────────────────────────────────────────────

function ScoreRing({ score }) {
  const pct = Math.max(0, Math.min(100, Math.round(score ?? 0)));
  const radius = 44;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (pct / 100) * circumference;
  const color = pct >= 80 ? "#10b981" : pct >= 60 ? "#f59e0b" : "#ef4444";
  const label = pct >= 80 ? "Excellent" : pct >= 60 ? "Correct" : "Faible";

  return (
    <div className="flex flex-col items-center gap-1">
      <svg width="108" height="108" viewBox="0 0 108 108">
        <circle cx="54" cy="54" r={radius} fill="none" stroke="#f1f5f9" strokeWidth="8" />
        <circle
          cx="54" cy="54" r={radius}
          fill="none" stroke={color} strokeWidth="8" strokeLinecap="round"
          strokeDasharray={circumference} strokeDashoffset={offset}
          transform="rotate(-90 54 54)"
          style={{ transition: "stroke-dashoffset 0.8s cubic-bezier(.4,0,.2,1)" }}
        />
        <text x="54" y="50" textAnchor="middle" dominantBaseline="middle" fontSize="22" fontWeight="700" fill={color}>
          {pct}
        </text>
        <text x="54" y="68" textAnchor="middle" dominantBaseline="middle" fontSize="11" fill="#94a3b8">
          / 100
        </text>
      </svg>
      <span
        className="text-xs font-semibold px-2.5 py-0.5 rounded-full"
        style={{ background: color + "18", color }}
      >
        {label}
      </span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Dimension row
// ─────────────────────────────────────────────────────────────

function DimensionRow({ dimension, score }) {
  const { label, icon: Icon, accent, track, description } = dimension;
  const pct = Math.max(0, Math.min(100, Math.round(score ?? 0)));
  const [tip, setTip] = useState(false);

  return (
    <div className="group">
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2 min-w-0">
          <span className="shrink-0 w-6 h-6 rounded-lg flex items-center justify-center" style={{ background: track }}>
            <Icon size={12} style={{ color: accent }} />
          </span>
          <span className="text-xs font-semibold text-gray-700 truncate">{label}</span>
          <button
            onMouseEnter={() => setTip(true)}
            onMouseLeave={() => setTip(false)}
            className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity text-gray-300 hover:text-gray-500"
          >
            <Info size={10} />
          </button>
        </div>
        <span className="shrink-0 text-xs font-bold ml-2 tabular-nums" style={{ color: accent }}>
          {pct}
        </span>
      </div>

      {tip && (
        <p className="mb-2 rounded-lg bg-gray-800 px-3 py-2 text-xs text-white leading-relaxed">
          {description}
        </p>
      )}

      <div className="h-1.5 rounded-full overflow-hidden" style={{ background: track }}>
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, background: accent }}
        />
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Keyword chip
// ─────────────────────────────────────────────────────────────

function KeywordChip({ word, matched }) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium border ${
        matched
          ? "bg-emerald-50 text-emerald-700 border-emerald-200"
          : "bg-red-50 text-red-600 border-red-200"
      }`}
    >
      {matched ? <CheckCircle2 size={9} /> : <XCircle size={9} />}
      {word}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────
// Cluster badge
// ─────────────────────────────────────────────────────────────

const CLUSTER_ICONS = {
  python: "🐍", javascript: "🟨", typescript: "🔷",
  devops: "⚙️", cloud: "☁️", data: "🗄️",
  ml: "🤖", java: "☕", mobile: "📱", security: "🔒",
};

function ClusterBadge({ name }) {
  const icon = CLUSTER_ICONS[name?.toLowerCase()] ?? "🔧";
  return (
    <span className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-50 border border-indigo-100 px-3 py-1.5 text-xs font-semibold text-indigo-700">
      <span aria-hidden>{icon}</span>
      {name}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────
// Card wrapper
// ─────────────────────────────────────────────────────────────

function Card({ children, className = "" }) {
  return (
    <div className={`rounded-2xl border border-gray-100 bg-white shadow-sm ${className}`}>
      {children}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Empty states
// ─────────────────────────────────────────────────────────────

function PendingState() {
  return (
    <div className="py-8 text-center">
      <div className="w-10 h-10 rounded-full bg-amber-50 flex items-center justify-center mx-auto mb-3">
        <Clock size={18} className="text-amber-400 animate-pulse" />
      </div>
      <p className="text-sm font-medium text-gray-600">Analyse IA en file d'attente</p>
      <p className="mt-1 text-xs text-gray-400 leading-relaxed">
        Les scores détaillés apparaîtront<br />une fois le traitement terminé
      </p>
    </div>
  );
}

function ProcessingState() {
  return (
    <div className="py-8 text-center">
      <div className="w-10 h-10 rounded-full bg-blue-50 flex items-center justify-center mx-auto mb-3">
        <Brain size={18} className="text-blue-400 animate-pulse" />
      </div>
      <p className="text-sm font-medium text-gray-600">Traitement en cours…</p>
      <p className="mt-1 text-xs text-gray-400">L'analyse IA est en cours d'exécution</p>
    </div>
  );
}

function FailedState() {
  return (
    <div className="py-8 text-center">
      <div className="w-10 h-10 rounded-full bg-red-50 flex items-center justify-center mx-auto mb-3">
        <AlertTriangle size={18} className="text-red-400" />
      </div>
      <p className="text-sm font-medium text-red-500">Échec du traitement</p>
      <p className="mt-1 text-xs text-gray-400">Impossible d'analyser ce CV</p>
    </div>
  );
}

function NoDataState() {
  return (
    <div className="py-8 text-center">
      <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-3">
        <Brain size={18} className="text-gray-400" />
      </div>
      <p className="text-sm text-gray-400">Aucune donnée disponible</p>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────

export default function ScorePanel({ candidate }) {
  const [feedbackSent, setFeedbackSent] = useState(null);
  const [loadingFeedback, setLoadingFeedback] = useState(false);

  // ── Safely resolve all fields ─────────────────────────────
  const aiData = useMemo(() => safeParse(candidate?.ai_extracted_data), [candidate]);

  // FIX: dimension_scores can be an empty object {} when processing_status
  // is "queued" or "processing" — the Celery task hasn't written scores yet.
  // safeParse also handles the case where it arrives as a JSON string.
  const dims = useMemo(() => {
    const raw = candidate?.dimension_scores ?? aiData?.dimension_scores ?? null;
    return safeParse(raw);
  }, [candidate, aiData]);

  const matched = useMemo(
    () => safeParseArray(candidate?.matched_keywords ?? aiData?.matched_keywords),
    [candidate, aiData]
  );

  const missing = useMemo(
    () => safeParseArray(candidate?.missing_keywords ?? aiData?.missing_keywords),
    [candidate, aiData]
  );

  const coveredClusters = useMemo(
    () => safeParseArray(candidate?.covered_clusters ?? aiData?.covered_clusters),
    [candidate, aiData]
  );

  const score       = candidate?.score ?? aiData?.score ?? null;
  const confidence  = candidate?.score_confidence ?? aiData?.score_confidence ?? null;
  const reasoning   = candidate?.score_reasoning ?? aiData?.score_reasoning ?? null;
  const status      = candidate?.processing_status ?? null;

  const hasData     = Object.keys(dims).length > 0;
  const isPending   = status === "queued";
  const isProcessing = status === "processing";
  const isFailed    = status === "failed";

  // ── Feedback ──────────────────────────────────────────────
  async function sendFeedback(type) {
    if (feedbackSent || loadingFeedback) return;
    setLoadingFeedback(true);
    try {
      await axiosClient.post(`/feedback/${candidate.id}/${type}`);
      setFeedbackSent(type);
      toast.success(type === "like" ? "👍 Feedback enregistré" : "👎 Feedback enregistré");
    } catch (err) {
      console.error(err);
      toast.error("Erreur lors de l'envoi du feedback");
    } finally {
      setLoadingFeedback(false);
    }
  }

  // ── Render ────────────────────────────────────────────────
  return (
    <div className="space-y-4">

      {/* ── Score card ───────────────────────────────────── */}
      <Card className="overflow-hidden">
        <div className="flex items-center gap-2 px-5 pt-5 pb-3 border-b border-gray-50">
          <Sparkles size={14} className="text-indigo-400" />
          <h2 className="text-sm font-bold text-gray-900 flex-1">Score ATS Intelligent</h2>
          {confidence !== null && (
            <span className="text-xs text-gray-400 tabular-nums">
              Confiance&nbsp;
              <span className="font-semibold text-gray-600">
                {Math.round(confidence * 100)}%
              </span>
            </span>
          )}
        </div>

        <div className="px-5 py-5">
          {score !== null && (
            <div className="flex justify-center mb-6">
              <ScoreRing score={score} />
            </div>
          )}

          {hasData ? (
            <div className="space-y-4">
              {DIMENSIONS.map((dim) => (
                <DimensionRow key={dim.key} dimension={dim} score={dims?.[dim.key] ?? 0} />
              ))}
            </div>
          ) : isPending ? (
            <PendingState />
          ) : isProcessing ? (
            <ProcessingState />
          ) : isFailed ? (
            <FailedState />
          ) : (
            <NoDataState />
          )}
        </div>

        {reasoning && (
          <div className="mx-5 mb-5 rounded-xl bg-gray-50 border border-gray-100 px-4 py-3">
            <div className="flex items-start gap-2">
              <Brain size={13} className="text-gray-400 mt-0.5 shrink-0" />
              <p className="text-xs leading-relaxed text-gray-600">{reasoning}</p>
            </div>
          </div>
        )}
      </Card>

      {/* ── Feedback card ────────────────────────────────── */}
      <Card className="px-5 py-4">
        <p className="text-sm font-bold text-gray-900 mb-0.5">Ce candidat vous convient ?</p>
        <p className="text-xs text-gray-400 mb-4">Votre retour améliore le scoring ATS.</p>
        <div className="flex gap-2.5">
          <button
            onClick={() => sendFeedback("like")}
            disabled={!!feedbackSent || loadingFeedback}
            className={`flex-1 flex items-center justify-center gap-1.5 rounded-xl border py-2.5 text-sm font-semibold transition-all duration-200 ${
              feedbackSent === "like"
                ? "border-emerald-500 bg-emerald-500 text-white"
                : "border-emerald-200 bg-white text-emerald-600 hover:bg-emerald-50 active:scale-95"
            } disabled:opacity-60 disabled:cursor-not-allowed`}
          >
            <ThumbsUp size={14} />
            Bon profil
          </button>
          <button
            onClick={() => sendFeedback("dislike")}
            disabled={!!feedbackSent || loadingFeedback}
            className={`flex-1 flex items-center justify-center gap-1.5 rounded-xl border py-2.5 text-sm font-semibold transition-all duration-200 ${
              feedbackSent === "dislike"
                ? "border-red-500 bg-red-500 text-white"
                : "border-red-200 bg-white text-red-500 hover:bg-red-50 active:scale-95"
            } disabled:opacity-60 disabled:cursor-not-allowed`}
          >
            <ThumbsDown size={14} />
            Pas adapté
          </button>
        </div>
      </Card>

      {/* ── Tech clusters ────────────────────────────────── */}
      {coveredClusters.length > 0 && (
        <Card className="px-5 py-4">
          <div className="flex items-center gap-2 mb-3">
            <Layers size={14} className="text-indigo-400" />
            <h2 className="text-sm font-bold text-gray-900">Écosystèmes maîtrisés</h2>
          </div>
          <div className="flex flex-wrap gap-2">
            {coveredClusters.map((c) => (
              <ClusterBadge key={c} name={c} />
            ))}
          </div>
        </Card>
      )}

      {/* ── Keywords ─────────────────────────────────────── */}
      {(matched.length > 0 || missing.length > 0) && (
        <Card className="px-5 py-4">
          <h2 className="text-sm font-bold text-gray-900 mb-4">Analyse mots-clés</h2>

          {matched.length > 0 && (
            <div className="mb-4">
              <p className="mb-2 text-xs font-semibold text-emerald-600 uppercase tracking-wide">
                ✓ Présents ({matched.length})
              </p>
              <div className="flex flex-wrap gap-1.5">
                {matched.map((kw) => (
                  <KeywordChip key={kw} word={kw} matched />
                ))}
              </div>
            </div>
          )}

          {missing.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-semibold text-red-500 uppercase tracking-wide">
                ✗ Manquants ({missing.length})
              </p>
              <div className="flex flex-wrap gap-1.5">
                {missing.map((kw) => (
                  <KeywordChip key={kw} word={kw} matched={false} />
                ))}
              </div>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}