// src/components/ScorePanel.jsx

import { useMemo, useState, useEffect } from "react";
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
  ExternalLink,
} from "lucide-react";

import toast from "react-hot-toast";
import axiosClient from "../api/axiosClient";
import { useOpenCV } from "../hooks/useOpenCV";

// ─────────────────────────────────────────────────────────────────────────────
// CONFIG
// ─────────────────────────────────────────────────────────────────────────────

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
    label: "Compétences",
    icon: Zap,
    accent: "#8b5cf6",
    track: "#f5f3ff",
    description: "Profondeur réelle des compétences et technologies détectées",
  },
  {
    key: "experience_score",
    label: "Expérience",
    icon: Briefcase,
    accent: "#3b82f6",
    track: "#eff6ff",
    description: "Années d'expérience professionnelle détectées",
  },
  {
    key: "project_complexity_score",
    label: "Projets",
    icon: FolderOpen,
    accent: "#10b981",
    track: "#ecfdf5",
    description: "Complexité et diversité des projets réalisés",
  },
  {
    key: "education_score",
    label: "Formation",
    icon: TrendingUp,
    accent: "#ec4899",
    track: "#fdf2f8",
    description: "Progression académique et niveau d'études",
  },
  {
  key: "certification_score",
  label: "Certifications",
  icon: CheckCircle2,     // already imported
  accent: "#f59e0b",
  track: "#fffbeb",
  description: "Certifications professionnelles détectées (AWS, Scrum, Oracle…)",
  },
  {
    key: "leadership_score",
    label: "Leadership",
    icon: TrendingUp,       // already imported, or swap for another
    accent: "#6366f1",
    track: "#eef2ff",
    description: "Capacités d'encadrement et de management détectées",
  },
];

const CLUSTER_ICONS = {
  python: "🐍",
  javascript: "🟨",
  typescript: "🔷",
  cloud: "☁️",
  devops: "⚙️",
  data: "🗄️",
  ml: "🤖",
  mobile: "📱",
  java: "☕",
  security: "🔒",
};

const FEEDBACK_BUTTONS = [
  {
    type: "like",
    label: "Bon profil",
    icon: ThumbsUp,
    activeClass: "border-emerald-500 bg-emerald-500 text-white",
    idleClass: "border-emerald-200 bg-white text-emerald-600 hover:bg-emerald-50",
  },
  {
    type: "dislike",
    label: "Pas adapté",
    icon: ThumbsDown,
    activeClass: "border-red-500 bg-red-500 text-white",
    idleClass: "border-red-200 bg-white text-red-500 hover:bg-red-50",
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────────────────────────

function safeParse(value) {
  if (!value) return {};
  if (typeof value === "string") {
    try {
      return JSON.parse(value);
    } catch {
      return {};
    }
  }
  return typeof value === "object" && !Array.isArray(value) ? value : {};
}

function safeParseArray(value) {
  if (Array.isArray(value)) return value;
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }
  return [];
}

/**
 * Normalize score_confidence to a 0–100 integer.
 * Backend may return a decimal (0.85) or a percentage (85).
 */
function normalizeConfidence(value) {
  if (value == null) return null;
  const n = parseFloat(value);
  if (isNaN(n)) return null;
  return Math.round(n > 1 ? n : n * 100);
}

function clamp(n) {
  return Math.max(0, Math.min(100, Math.round(n ?? 0)));
}

// ─────────────────────────────────────────────────────────────────────────────
// SUBCOMPONENTS
// ─────────────────────────────────────────────────────────────────────────────

function Card({ children, className = "" }) {
  return (
    <div className={`rounded-3xl border border-gray-100 bg-white shadow-sm ${className}`}>
      {children}
    </div>
  );
}

function ScoreRing({ score }) {
  const pct = clamp(score);
  const radius = 46;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (pct / 100) * circumference;

  const color = pct >= 80 ? "#10b981" : pct >= 60 ? "#f59e0b" : "#ef4444";
  const label = pct >= 80 ? "Excellent" : pct >= 60 ? "Correct" : "Faible";

  return (
    <div className="flex flex-col items-center gap-2">
      <svg width="120" height="120">
        <circle cx="60" cy="60" r={radius} fill="none" stroke="#f1f5f9" strokeWidth="10" />
        <circle
          cx="60"
          cy="60"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform="rotate(-90 60 60)"
          style={{ transition: "stroke-dashoffset .8s cubic-bezier(.4,0,.2,1)" }}
        />
        <text x="60" y="56" textAnchor="middle" fontSize="24" fontWeight="700" fill={color}>
          {pct}
        </text>
        <text x="60" y="76" textAnchor="middle" fontSize="11" fill="#94a3b8">
          / 100
        </text>
      </svg>
      <span
        className="rounded-full px-3 py-1 text-xs font-semibold"
        style={{ background: `${color}20`, color }}
      >
        {label}
      </span>
    </div>
  );
}

function DimensionRow({ dimension, score }) {
  const { label, icon: Icon, accent, track, description } = dimension;
  const pct = clamp(score);
  const [showTip, setShowTip] = useState(false);

  return (
    <div className="group">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex min-w-0 items-center gap-2">
          <div
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-xl"
            style={{ background: track }}
          >
            <Icon size={13} style={{ color: accent }} />
          </div>
          <span className="truncate text-xs font-semibold text-gray-700">{label}</span>
          <button
            onMouseEnter={() => setShowTip(true)}
            onMouseLeave={() => setShowTip(false)}
            className="shrink-0 text-gray-300 opacity-0 transition-opacity group-hover:opacity-100 hover:text-gray-500"
            aria-label={`Info: ${label}`}
          >
            <Info size={11} />
          </button>
        </div>
        <span className="text-xs font-bold tabular-nums" style={{ color: accent }}>
          {pct}
        </span>
      </div>

      {showTip && (
        <div className="mb-2 rounded-xl bg-gray-900 px-3 py-2 text-xs leading-relaxed text-white">
          {description}
        </div>
      )}

      <div className="h-2 overflow-hidden rounded-full" style={{ background: track }}>
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, background: accent }}
        />
      </div>
    </div>
  );
}

function KeywordChip({ word, matched }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-xs font-medium ${
        matched
          ? "border-emerald-200 bg-emerald-50 text-emerald-700"
          : "border-red-200 bg-red-50 text-red-600"
      }`}
    >
      {matched ? <CheckCircle2 size={10} /> : <XCircle size={10} />}
      {word}
    </span>
  );
}

function ClusterBadge({ name }) {
  const icon = CLUSTER_ICONS[name?.toLowerCase()] ?? "🔧";
  return (
    <span className="inline-flex items-center gap-2 rounded-2xl border border-indigo-100 bg-indigo-50 px-3 py-1.5 text-xs font-semibold text-indigo-700">
      {icon} {name}
    </span>
  );
}

function StatusState({ icon: Icon, iconClass, title, subtitle }) {
  return (
    <div className="py-10 text-center">
      <Icon size={18} className={`mx-auto mb-3 ${iconClass}`} />
      <p className="text-sm font-medium text-gray-700">{title}</p>
      {subtitle && <p className="mt-1 text-xs text-gray-400">{subtitle}</p>}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN COMPONENT
// ─────────────────────────────────────────────────────────────────────────────

export default function ScorePanel({ candidate }) {
  const [feedbackSent, setFeedbackSent] = useState(null);
  const [loadingFeedback, setLoadingFeedback] = useState(false);
  const { openCV, isOpeningCV } = useOpenCV();

  // Reset feedback state when candidate changes
  useEffect(() => {
    setFeedbackSent(null);
    setLoadingFeedback(false);
  }, [candidate?.id]);

  // ── Derived data ────────────────────────────────────────────────────────────

  const aiData = useMemo(() => safeParse(candidate?.ai_extracted_data), [candidate]);

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

  const coveredClusters = useMemo(() => {
    const explicit = safeParseArray(candidate?.covered_clusters ?? aiData?.covered_clusters);
    if (explicit.length > 0) return explicit;

    // Fallback: derive from skills list using CLUSTER_ICONS keys as signal
    const skills = safeParseArray(candidate?.skills ?? aiData?.skills);
    return Object.keys(CLUSTER_ICONS).filter((cluster) =>
      skills.some((s) => String(s).toLowerCase().includes(cluster))
    );
  }, [candidate, aiData]);

  const score = candidate?.score ?? aiData?.score ?? null;
  const confidence = normalizeConfidence(
    candidate?.score_confidence ?? aiData?.score_confidence
  );
  const reasoning = candidate?.score_reasoning ?? aiData?.score_reasoning ?? null;
  const processingStatus = candidate?.processing_status ?? null;

  const hasData = Object.keys(dims).length > 0;
  const isPending = processingStatus === "queued";
  const isProcessing = processingStatus === "processing";
  const isFailed = processingStatus === "failed";
  // Score exists but dimension detail is missing (partial pipeline run)
  const isPartial = !hasData && score !== null && !isPending && !isProcessing && !isFailed;

  // ── Actions ─────────────────────────────────────────────────────────────────

  async function sendFeedback(type) {
    if (feedbackSent || loadingFeedback) return;
    setLoadingFeedback(true);
    try {
      await axiosClient.post(`/feedback/${candidate.id}/${type}`);
      setFeedbackSent(type);
      toast.success(type === "like" ? "👍 Feedback enregistré" : "👎 Feedback enregistré");
    } catch (err) {
      console.error("[ScorePanel] sendFeedback error:", err);
      toast.error("Erreur lors de l'envoi du feedback");
    } finally {
      setLoadingFeedback(false);
    }
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-4">
      {/* ── Score card ─────────────────────────────────────────────────────── */}
      <Card className="overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-2 border-b border-gray-50 px-5 py-4">
          <Sparkles size={15} className="text-indigo-400" />
          <h2 className="flex-1 text-sm font-bold text-gray-900">Score ATS Intelligent</h2>
          {confidence !== null && (
            <span className="text-xs text-gray-400">
              Confiance{" "}
              <span className="font-semibold text-gray-700">{confidence}%</span>
            </span>
          )}
        </div>

        {/* Body */}
        <div className="px-5 py-6">
          {score !== null && (
            <div className="mb-7 flex justify-center">
              <ScoreRing score={score} />
            </div>
          )}

          {hasData ? (
            <div className="space-y-4">
              {DIMENSIONS.map((dim) => (
                <DimensionRow
                  key={dim.key}
                  dimension={dim}
                  score={dims[dim.key] ?? 0}
                />
              ))}
            </div>
          ) : isPartial ? (
            <div className="py-6 text-center">
              <AlertTriangle size={16} className="mx-auto mb-2 text-amber-400" />
              <p className="text-xs text-gray-500">Détail des dimensions non disponible</p>
            </div>
          ) : isPending ? (
            <StatusState
              icon={Clock}
              iconClass="text-amber-400 animate-pulse"
              title="Analyse IA en attente"
              subtitle="Les scores seront disponibles bientôt"
            />
          ) : isProcessing ? (
            <StatusState
              icon={Brain}
              iconClass="text-blue-400 animate-pulse"
              title="Analyse en cours…"
              subtitle="L'IA traite actuellement ce CV"
            />
          ) : isFailed ? (
            <StatusState
              icon={AlertTriangle}
              iconClass="text-red-400"
              title="Échec de l'analyse"
              subtitle="Impossible de traiter ce CV"
            />
          ) : (
            <StatusState
              icon={Brain}
              iconClass="text-gray-300"
              title="Aucune donnée disponible"
            />
          )}
        </div>

        {/* AI reasoning */}
        {reasoning && (
          <div className="mx-5 mb-5 rounded-2xl border border-gray-100 bg-gray-50 px-4 py-3">
            <div className="flex items-start gap-2">
              <Brain size={13} className="mt-0.5 shrink-0 text-gray-400" />
              <p className="text-xs leading-relaxed text-gray-600">{reasoning}</p>
            </div>
          </div>
        )}
      </Card>

      {/* ── CV button ──────────────────────────────────────────────────────── */}
      {candidate?.cv_file_url && (
        <Card className="p-4">
          <button
            onClick={() => openCV(candidate.cv_file_url)}
            disabled={isOpeningCV}
            className="flex w-full items-center justify-center gap-2 rounded-2xl border border-gray-200 bg-white px-4 py-3 text-sm font-medium text-gray-700 transition-all hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <ExternalLink size={16} />
            {isOpeningCV ? "Ouverture…" : "Voir le CV"}
          </button>
        </Card>
      )}

      {/* ── Feedback ───────────────────────────────────────────────────────── */}
      <Card className="px-5 py-4">
        <p className="mb-1 text-sm font-bold text-gray-900">Ce candidat vous convient ?</p>
        <p className="mb-4 text-xs text-gray-400">Votre retour améliore le scoring ATS.</p>
        <div className="flex gap-2.5">
          {FEEDBACK_BUTTONS.map(({ type, label, icon: Icon, activeClass, idleClass }) => (
            <button
              key={type}
              onClick={() => sendFeedback(type)}
              disabled={!!feedbackSent || loadingFeedback}
              className={`flex flex-1 items-center justify-center gap-2 rounded-2xl border py-2.5 text-sm font-semibold transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-60 ${
                feedbackSent === type ? activeClass : idleClass
              }`}
            >
              <Icon size={14} />
              {label}
            </button>
          ))}
        </div>
      </Card>

      {/* ── Clusters ───────────────────────────────────────────────────────── */}
      {coveredClusters.length > 0 && (
        <Card className="px-5 py-4">
          <div className="mb-3 flex items-center gap-2">
            <Layers size={14} className="text-indigo-400" />
            <h2 className="text-sm font-bold text-gray-900">Écosystèmes maîtrisés</h2>
          </div>
          <div className="flex flex-wrap gap-2">
            {coveredClusters.map((cluster) => (
              <ClusterBadge key={cluster} name={cluster} />
            ))}
          </div>
        </Card>
      )}

      {/* ── Keywords ───────────────────────────────────────────────────────── */}
      {(matched.length > 0 || missing.length > 0) && (
        <Card className="px-5 py-4">
          <h2 className="mb-4 text-sm font-bold text-gray-900">Analyse mots-clés</h2>

          {matched.length > 0 && (
            <div className="mb-4">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-emerald-600">
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
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-red-500">
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