// frontend/src/pages/CandidateDetail.jsx
import { useState, useMemo, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  ExternalLink,
  GitBranch,
  Mail,
  Phone,
  Briefcase,
  FileText,
  Sparkles,
  Target,
  Zap,
  FolderOpen,
  TrendingUp,
  Info,
  Brain,
  AlertTriangle,
  Clock,
  CheckCircle2,
  XCircle,
  ThumbsUp,
  ThumbsDown,
  Layers,
} from "lucide-react";

import toast from "react-hot-toast";
import axiosClient from "../api/axiosClient";
import { useOpenCV } from "../hooks/useOpenCV";
import { useCandidateWithPolling } from "../hooks/useCandidates";
import { useJobs } from "../hooks/useJobs";
import StatusBadge from "../components/StatusBadge";
import ScoreBadge from "../components/ScoreBadge";
import StatusTransitionModal from "../components/StatusTransitionModal";

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
    description: "Correspondance sémantique (similarité) avec la fiche de poste",
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
  description: "Certifications professionnelles détectées",
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
  word: "📝",
  powerpoint: "📊",
  excel: "📈",
  powerbi: "📉",
  odoo: "🧩",
  microsoft_office: "🪟",
  google_suite: "📧",
  google_docs: "📄",
  google_sheets: "📊",
  google_slides: "📈",
  oracle: "🗄️",
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
// SHARED UI PRIMITIVES
// ─────────────────────────────────────────────────────────────────────────────

function SectionCard({ children, className = "" }) {
  return (
    <div className={`rounded-3xl border border-gray-200 bg-white shadow-sm ${className}`}>
      {children}
    </div>
  );
}

function SectionTitle({ children }) {
  return <h2 className="mb-4 text-sm font-semibold text-gray-900">{children}</h2>;
}

// ─────────────────────────────────────────────────────────────────────────────
// LEFT COLUMN COMPONENTS
// ─────────────────────────────────────────────────────────────────────────────

function CandidateAvatar({ name }) {
  const initials = useMemo(() => {
    if (!name) return "?";
    return name.split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase();
  }, [name]);

  return (
    <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-indigo-100 text-xl font-bold text-indigo-700">
      {initials}
    </div>
  );
}

function InfoRow({ icon: Icon, label, value }) {
  if (value == null || value === "") return null;
  return (
    <div className="flex items-start gap-3">
      {Icon && <Icon size={16} className="mt-0.5 shrink-0 text-gray-400" />}
      <div className="min-w-0">
        <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</p>
        <p className="mt-0.5 wrap-break-word text-sm text-gray-900">{value}</p>
      </div>
    </div>
  );
}

function KeywordBadge({ keyword }) {
  return (
    <span className="rounded-xl bg-green-100 px-3 py-1.5 text-xs font-medium text-green-700">
      {keyword}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// SCORE PANEL COMPONENTS
// ─────────────────────────────────────────────────────────────────────────────

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
          cx="60" cy="60" r={radius}
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

export default function CandidateDetail() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [showTransition, setShowTransition] = useState(false);
  const [feedbackSent, setFeedbackSent] = useState(null);
  const [loadingFeedback, setLoadingFeedback] = useState(false);
  const { openCV, isOpeningCV } = useOpenCV();

  // ── Data fetching ───────────────────────────────────────────────────────────

  const { data: candidate, isLoading } = useCandidateWithPolling(id, {
    pollUntilScored: true,
  });

  const { data: jobs = [] } = useJobs();

  // Reset feedback when candidate changes
  useEffect(() => {
    setFeedbackSent(null);
    setLoadingFeedback(false);
  }, [candidate?.id]);

  const linkedJob = useMemo(() => {
    if (!candidate?.job_id) return null;
    return jobs.find((j) => j.id === candidate.job_id) ?? null;
  }, [jobs, candidate]);

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
    const skills = safeParseArray(candidate?.skills ?? aiData?.skills);
    return Object.keys(CLUSTER_ICONS).filter((cluster) =>
      skills.some((s) => String(s).toLowerCase().includes(cluster))
    );
  }, [candidate, aiData]);

  const aiDataWithoutSummary = useMemo(() => {
    if (!candidate?.ai_extracted_data) return null;
    const { summary, ...rest } = candidate.ai_extracted_data;
    return Object.keys(rest).length > 0 ? rest : null;
  }, [candidate]);

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
  const isPartial = !hasData && score !== null && !isPending && !isProcessing && !isFailed;

  const experienceLabel =
    candidate?.experience_years != null
      ? `${candidate.experience_years} an${candidate.experience_years > 1 ? "s" : ""}`
      : null;

  // ── Actions ─────────────────────────────────────────────────────────────────

  async function sendFeedback(type) {
    if (feedbackSent || loadingFeedback) return;
    setLoadingFeedback(true);
    try {
      await axiosClient.post(`/feedback/${candidate.id}/${type}`);
      setFeedbackSent(type);
      toast.success(type === "like" ? "👍 Feedback enregistré" : "👎 Feedback enregistré");
    } catch (err) {
      console.error("[CandidateDetail] sendFeedback error:", err);
      toast.error("Erreur lors de l'envoi du feedback");
    } finally {
      setLoadingFeedback(false);
    }
  }

  // ── Loading / empty states ──────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center p-10">
        <p className="animate-pulse text-sm text-gray-400">Chargement du candidat...</p>
      </div>
    );
  }

  if (!candidate) {
    return (
      <div className="flex h-full items-center justify-center p-10">
        <p className="text-sm text-gray-400">Candidat introuvable</p>
      </div>
    );
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="mx-auto max-w-6xl p-6 lg:p-8">
      {/* Back button */}
      <button
        onClick={() => navigate(-1)}
        className="mb-6 flex items-center gap-2 text-sm text-gray-500 transition-colors hover:text-gray-900"
      >
        <ArrowLeft size={16} />
        Retour
      </button>

      {/* ── Header card ─────────────────────────────────────────────────────── */}
      <div className="mb-6 rounded-3xl border border-gray-200 bg-white p-6 shadow-sm">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex items-start gap-4">
            <CandidateAvatar name={candidate.full_name} />
            <div>
              <h1 className="text-2xl font-bold text-gray-900">
                {candidate.full_name || "Candidat sans nom"}
              </h1>
              <p className="mt-1 text-sm text-gray-500">
                {candidate.current_position || "Poste non renseigné"}
              </p>
              {linkedJob && (
                <div className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-700">
                  <Briefcase size={12} />
                  Poste ciblé : {linkedJob.title}
                </div>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {candidate.score == null && (
              <span className="animate-pulse text-xs text-gray-400">
                Scoring IA en cours…
              </span>
            )}
            <ScoreBadge score={candidate.score} />
            <StatusBadge status={candidate.status} />
            <button
              onClick={() => setShowTransition(true)}
              className="flex items-center gap-2 rounded-full border border-gray-200 bg-white px-4 py-2 text-xs font-medium text-gray-700 transition-all hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-700"
            >
              <GitBranch size={14} />
              Changer statut
            </button>
          </div>
        </div>
      </div>

      {/* ── Content grid ────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">

        {/* ── LEFT COLUMN ─────────────────────────────────────────────────── */}
        <div className="space-y-6">

          {/* Contact & meta */}
          <SectionCard className="p-5">
            <SectionTitle>Informations</SectionTitle>
            <div className="space-y-4">
              <InfoRow icon={Mail} label="Email" value={candidate.email} />
              <InfoRow icon={Phone} label="Téléphone" value={candidate.phone} />
              <InfoRow icon={Briefcase} label="Expérience" value={experienceLabel} />
              {linkedJob && (
                <InfoRow icon={Briefcase} label="Poste ciblé" value={linkedJob.title} />
              )}
            </div>

            {candidate.cv_file_url && (
              <button
                onClick={() => openCV(candidate.cv_file_url)}
                disabled={isOpeningCV}
                className="mt-6 flex w-full items-center justify-center gap-2 rounded-2xl border border-gray-200 bg-white px-4 py-3 text-sm font-medium text-gray-700 transition-all hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <ExternalLink size={16} />
                {isOpeningCV ? "Ouverture…" : "Voir le CV"}
              </button>
            )}
          </SectionCard>

          {/* ── Score ATS ─────────────────────────────────────────────────── */}
          <SectionCard className="overflow-hidden">
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

            {/* Ring + dimensions */}
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
          </SectionCard>

          {/* ── Feedback ──────────────────────────────────────────────────── */}
          <SectionCard className="px-5 py-4">
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
          </SectionCard>

          {/* ── Clusters ──────────────────────────────────────────────────── */}
          {coveredClusters.length > 0 && (
            <SectionCard className="px-5 py-4">
              <div className="mb-3 flex items-center gap-2">
                <Layers size={14} className="text-indigo-400" />
                <h2 className="text-sm font-bold text-gray-900">Écosystèmes maîtrisés</h2>
              </div>
              <div className="flex flex-wrap gap-2">
                {coveredClusters.map((cluster) => (
                  <ClusterBadge key={cluster} name={cluster} />
                ))}
              </div>
            </SectionCard>
          )}

          {/* ── Keywords analysis ─────────────────────────────────────────── */}
          {(matched.length > 0 || missing.length > 0) && (
            <SectionCard className="px-5 py-4">
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
            </SectionCard>
          )}
        </div>

        {/* ── RIGHT COLUMN ────────────────────────────────────────────────── */}
        <div className="space-y-6 lg:col-span-2">

          {/* AI summary */}
          {candidate.ai_extracted_data?.summary && (
            <SectionCard className="p-6">
              <div className="mb-3 flex items-center gap-2">
                <Sparkles size={15} className="text-indigo-400" />
                <h2 className="text-sm font-semibold text-gray-900">Résumé IA</h2>
              </div>
              <p className="whitespace-pre-line text-sm leading-relaxed text-gray-600">
                {candidate.ai_extracted_data.summary}
              </p>
            </SectionCard>
          )}

          {/* Raw AI data */}
          <SectionCard className="p-6">
            <div className="mb-4 flex items-center gap-2">
              <FileText size={15} className="text-gray-400" />
              <h2 className="text-sm font-semibold text-gray-900">
                Données extraites par l'IA
              </h2>
            </div>
            {aiDataWithoutSummary ? (
              <pre className="max-h-125 overflow-auto rounded-2xl border border-gray-100 bg-gray-50 p-4 text-xs leading-relaxed text-gray-700">
                {JSON.stringify(aiDataWithoutSummary, null, 2)}
              </pre>
            ) : (
              <p className="text-sm text-gray-400">
                Aucune donnée structurée disponible.
              </p>
            )}
          </SectionCard>
        </div>
      </div>

      {/* Status transition modal */}
      {showTransition && (
        <StatusTransitionModal
          candidate={candidate}
          onClose={() => setShowTransition(false)}
        />
      )}
    </div>
  );
}