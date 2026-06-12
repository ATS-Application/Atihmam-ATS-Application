// frontend/src/pages/CandidateDetail.jsx
// Aligned with scoring_service.py v2.1 — hierarchical ATS scorer
import { useState, useMemo, useEffect, useCallback, useRef } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  GitBranch,
  Mail,
  Phone,
  Briefcase,
  FileText,
  Sparkles,
  Target,
  Zap,
  GraduationCap,
  Award,
  TrendingUp,
  Languages,
  Layers,
  Info,
  Brain,
  AlertTriangle,
  Clock,
  CheckCircle2,
  XCircle,
  ThumbsUp,
  ThumbsDown,
  Trash2,
  ShieldAlert,
} from "lucide-react";

import toast from "react-hot-toast";
import axiosClient from "../api/axiosClient";
import { useOpenCV } from "../hooks/useOpenCV";
import { useCandidateWithPolling, useDeleteCandidate } from "../hooks/useCandidates";
import { useJobs } from "../hooks/useJobs";
import StatusBadge from "../components/StatusBadge";
import ScoreBadge from "../components/ScoreBadge";
import StatusTransitionModal from "../components/StatusTransitionModal";

// ─────────────────────────────────────────────────────────────────────────────
// CONFIG — mirrors score_to_dict() "dimensions" keys from scoring_service.py
// ─────────────────────────────────────────────────────────────────────────────

// The backend compute_candidate_score() compat shim writes both canonical keys
// (e.g. "experience") and frontend alias keys (e.g. "experience_score") into
// dimension_scores. We read the canonical keys from dimension_scores and fall
// back to the alias keys that may be stored directly on the candidate row.
const DIMENSIONS = [
  {
    key: "keywords",
    alias: "keyword_score",
    label: "Mots-clés",
    icon: Target,
    accent: "#f97316",
    track: "#fff7ed",
    description:
      "Ratio des mots-clés requis (ou compétences du domaine) détectés dans le CV.",
  },
  {
    key: "semantic",
    alias: "semantic_score",
    label: "Correspondance métier",
    icon: Zap,
    accent: "#8b5cf6",
    track: "#f5f3ff",
    description:
      "Similarité lexicale entre le CV et la fiche de poste (Jaccard) + couverture des compétences du domaine détecté.",
  },
  {
    key: "experience",
    alias: "experience_score",
    label: "Expérience",
    icon: Briefcase,
    accent: "#3b82f6",
    track: "#eff6ff",
    description:
      "Années d'expérience détectées rapportées aux années requises pour le poste et le niveau hiérarchique.",
  },
  {
    key: "complexity",
    alias: "project_complexity_score",
    label: "Maîtrise du domaine",
    icon: Layers,
    accent: "#10b981",
    track: "#ecfdf5",
    description:
      "Couverture des compétences clés du domaine détecté et diversité des domaines maîtrisés, pondérée par le niveau hiérarchique.",
  },
  {
    key: "education",
    alias: "education_score",
    label: "Formation",
    icon: GraduationCap,
    accent: "#ec4899",
    track: "#fdf2f8",
    description:
      "Niveau d'études détecté (CAP → Doctorat) comparé au minimum requis pour le niveau hiérarchique du poste.",
  },
  {
    key: "certifications",
    alias: "certification_score",
    label: "Certifications",
    icon: Award,
    accent: "#f59e0b",
    track: "#fffbeb",
    description:
      "Certifications reconnues détectées (OHADA, IFRS, PMP, AWS, etc.), pondérées par leur pertinence pour le domaine et le niveau.",
  },
  {
    key: "leadership",
    alias: "leadership_score",
    label: "Leadership",
    icon: TrendingUp,
    accent: "#6366f1",
    track: "#eef2ff",
    description:
      "Verbes d'action managériaux détectés (dirigé, piloté, encadré…) et niveaux hiérarchiques des postes précédents.",
  },
  {
    key: "language",
    alias: "language_score",
    label: "Qualité rédactionnelle",
    icon: Languages,
    accent: "#14b8a6",
    track: "#f0fdfa",
    description:
      "Richesse lexicale, détection de langue (FR/EN), couverture des sections standards du CV et longueur du document.",
  },
];

const HIERARCHY_LABELS = {
  collaborateur:         "Collaborateur",
  manager_intermediaire: "Manager intermédiaire",
  manager_senior:        "Manager senior",
  direction:             "Direction",
};

const DOMAIN_LABELS = {
  tech:          "Technologie",
  legal:         "Juridique",
  health:        "Santé",
  hr:            "RH",
  finance:       "Finance",
  marketing:     "Marketing",
  sales:         "Commercial",
  education:     "Éducation",
  agriculture:   "Agriculture",
  construction:  "BTP",
  logistics:     "Logistique",
  telecom:       "Télécom",
  energy:        "Énergie",
  mining:        "Mines",
  hospitality:   "Hôtellerie",
  media:         "Médias",
  insurance:     "Assurance",
  real_estate:   "Immobilier",
  consulting:    "Conseil",
  public_admin:  "Administration",
  ngo:           "ONG",
  pharma:        "Pharma",
  retail:        "Distribution",
  transport:     "Transport",
  environment:   "Environnement",
  craftsmanship: "Artisanat",
  security:      "Sécurité",
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

function clamp(n) {
  if (n == null || isNaN(Number(n))) return 0;
  const v = Number(n);
  // Backend stores scores as 0–1 floats; frontend expects 0–100
  return Math.max(0, Math.min(100, Math.round(v > 1 ? v : v * 100)));
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

function PenaltyChip({ penalty }) {
  return (
    <div className="flex items-start gap-2 rounded-xl border border-red-100 bg-red-50 px-3 py-2">
      <ShieldAlert size={13} className="mt-0.5 shrink-0 text-red-400" />
      <div className="min-w-0">
        <p className="text-xs font-semibold text-red-700">{penalty.description}</p>
        <p className="mt-0.5 text-xs text-red-400 tabular-nums">
          Score dimension : {Math.round(penalty.score * 100)} — Seuil : {Math.round(penalty.threshold * 100)} — Malus : −{Math.round(penalty.penalty_applied * 100)}
        </p>
      </div>
    </div>
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
  const location = useLocation();

  // ── ALL hooks at the top ──────────────────────────────────────────────────
  const [showTransition, setShowTransition] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [feedbackSent, setFeedbackSent] = useState(null);
  const [loadingFeedback, setLoadingFeedback] = useState(false);
  const { openCV, isOpeningCV } = useOpenCV();

  const { data: candidate, isLoading, isPending } = useCandidateWithPolling(id, {
    pollUntilScored: true,
  });

  const { data: jobs = [] } = useJobs();
  const { mutate: deleteCandidate, isPending: isDeleting } = useDeleteCandidate();

  const candidateIds = location.state?.candidateIds ?? null;
  const currentIndex = candidateIds ? candidateIds.indexOf(id) : -1;
  const prevId = candidateIds && currentIndex > 0 ? candidateIds[currentIndex - 1] : null;
  const nextId =
    candidateIds && currentIndex >= 0 && currentIndex < candidateIds.length - 1
      ? candidateIds[currentIndex + 1]
      : null;

  const goTo = useCallback(
    (targetId) => {
      if (!targetId) return;
      navigate(`/candidates/${targetId}`, { state: { candidateIds } });
    },
    [navigate, candidateIds]
  );

  // FIX: stable ref so the keydown handler never captures a stale goTo closure
  const goToRef = useRef(goTo);
  useEffect(() => { goToRef.current = goTo; }, [goTo]);

  // FIX: reset on route param `id`, not on candidate?.id, to avoid stale-data
  // flicker when the polling response hasn't settled yet on navigation
  useEffect(() => {
    setFeedbackSent(null);
    setLoadingFeedback(false);
  }, [id]);

  // FIX: use goToRef.current inside the listener so it always calls the latest
  // version of goTo without re-registering the event listener on every render
  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === "ArrowLeft" && prevId) goToRef.current(prevId);
      if (e.key === "ArrowRight" && nextId) goToRef.current(nextId);
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [prevId, nextId]);

  const linkedJob = useMemo(() => {
    if (!candidate?.job_id) return null;
    return jobs.find((j) => j.id === candidate.job_id) ?? null;
  }, [jobs, candidate]);

  const aiData = useMemo(() => safeParse(candidate?.ai_extracted_data), [candidate]);

  // ── Dimension scores ───────────────────────────────────────────────────────
  // The scoring result from compute_candidate_score() can land in several
  // places depending on which code path wrote it:
  //
  //   A) ai_extracted_data.dimension_scores  — compat shim result merged into CV data
  //   B) ai_extracted_data.full_details.dimensions — score_to_dict() nested result
  //   C) candidate.<alias_col>  — direct DB columns (keyword_score, semantic_score…)
  //   D) candidate.dimension_scores — a dedicated JSONB column
  //
  // We try all four sources and take the first non-null value per dimension.
  const dims = useMemo(() => {
    const parseObj = (v) => {
      if (!v || typeof v !== "object" || Array.isArray(v)) return {};
      return v;
    };

    // Source A: dimension_scores nested in ai_extracted_data
    const srcA = parseObj(
      typeof aiData?.dimension_scores === "string"
        ? (() => { try { return JSON.parse(aiData.dimension_scores); } catch { return {}; } })()
        : aiData?.dimension_scores
    );

    // Source B: score_to_dict().dimensions inside full_details
    const srcB = parseObj(aiData?.full_details?.dimensions);

    // Source C/D: candidate row — either a dimension_scores JSONB column or
    //             individual alias columns like keyword_score, semantic_score…
    const srcCD = parseObj(
      typeof candidate?.dimension_scores === "string"
        ? (() => { try { return JSON.parse(candidate.dimension_scores); } catch { return {}; } })()
        : candidate?.dimension_scores
    );

    const resolved = {};
    for (const dim of DIMENSIONS) {
      const v =
        srcA[dim.key]      ??  // A: canonical key in ai_extracted_data.dimension_scores
        srcA[dim.alias]    ??  // A: alias key in ai_extracted_data.dimension_scores
        srcB[dim.key]      ??  // B: canonical key in full_details.dimensions
        srcCD[dim.key]     ??  // C/D: canonical key in candidate.dimension_scores
        srcCD[dim.alias]   ??  // C/D: alias key in candidate.dimension_scores
        candidate?.[dim.alias] ?? // E: alias stored as a direct top-level column
        null;
      resolved[dim.key] = v;
    }
    return resolved;
  }, [candidate, aiData]);

  // DEV — uncomment to diagnose a blank score panel:
  // useEffect(() => {
  //   if (!candidate) return;
  //   console.group("[CandidateDetail] dim resolution");
  //   console.log("aiData keys:", Object.keys(aiData ?? {}));
  //   console.log("aiData.dimension_scores:", aiData?.dimension_scores);
  //   console.log("aiData.full_details?.dimensions:", aiData?.full_details?.dimensions);
  //   console.log("candidate.dimension_scores:", candidate?.dimension_scores);
  //   console.log("candidate.keyword_score:", candidate?.keyword_score);
  //   console.log("resolved dims:", dims);
  //   console.groupEnd();
  // }, [candidate, aiData, dims]);

  // True when at least 4 dimensions have a non-null score
  const hasData = useMemo(
    () => Object.values(dims).filter((v) => v != null).length >= 4,
    [dims]
  );

  // ── Keyword analysis ───────────────────────────────────────────────────────
  const matched = useMemo(
    () => safeParseArray(candidate?.matched_keywords ?? aiData?.matched_keywords),
    [candidate, aiData]
  );
  const missing = useMemo(
    () => safeParseArray(candidate?.missing_keywords ?? aiData?.missing_keywords),
    [candidate, aiData]
  );

  // ── Penalty details from compute_careness_penalty() ───────────────────────
  const penaltyDetails = useMemo(() => {
    const fullDetails = aiData?.full_details ?? {};
    return safeParseArray(fullDetails?.penalty_details ?? candidate?.penalty_details);
  }, [candidate, aiData]);

  // ── Hierarchy & domain context from score_to_dict() ───────────────────────
  const hierarchyLevel = useMemo(() => {
    return (
      aiData?.hierarchy_level ??
      aiData?.full_details?.hierarchy_level ??
      candidate?.hierarchy_level ??
      null
    );
  }, [candidate, aiData]);

  const domain = useMemo(() => {
    return (
      aiData?.domain ??
      aiData?.full_details?.domain ??
      candidate?.domain ??
      null
    );
  }, [candidate, aiData]);

  // ── Detected education level ───────────────────────────────────────────────
  const detectedEducation = useMemo(() => {
    return (
      aiData?.full_details?.detected_education ??
      candidate?.detected_education ??
      null
    );
  }, [candidate, aiData]);

  // ── AI summary ─────────────────────────────────────────────────────────────
  const aiSummary = useMemo(() => {
    if (typeof aiData?.summary === "string" && aiData.summary.trim()) {
      return aiData.summary;
    }
    return null;
  }, [aiData]);

  // ── Raw extracted data (excluding scoring artifacts) ───────────────────────
  const aiRawDisplay = useMemo(() => {
    if (!candidate?.ai_extracted_data) return null;
    const { summary, dimension_scores, full_details, ...rest } = safeParse(candidate.ai_extracted_data);
    return Object.keys(rest).length > 0 ? rest : null;
  }, [candidate]);

  // ── Early returns AFTER all hooks ─────────────────────────────────────────
  // FIX: replaced `fetchStatus === "idle"` guard (flickers between polls in RQ v5)
  // with `isPending` which is only true during the very first fetch with no cached data
  if (isLoading && isPending) {
    return (
      <div className="flex h-full items-center justify-center p-10">
        <p className="animate-pulse text-sm text-gray-400">Chargement du candidat…</p>
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

  // ── Derived values safe after early returns ────────────────────────────────
  const score = candidate?.score ?? aiData?.score ?? null;
  const reasoning = candidate?.score_reasoning ?? aiData?.score_reasoning ?? null;
  const processingStatus = candidate?.processing_status ?? null;

  const isPendingJob  = processingStatus === "queued";
  const isProcessing  = processingStatus === "processing";
  const isFailed      = processingStatus === "failed";

  // FIX: renamed from `isPartial` — describes the actual condition more clearly
  const hasScoreButNoDimensions = !hasData && score !== null && !isPendingJob && !isProcessing && !isFailed;

  const experienceLabel = candidate?.experience_years != null
    ? `${candidate.experience_years} an${candidate.experience_years > 1 ? "s" : ""}`
    : null;

  // ── Actions ───────────────────────────────────────────────────────────────

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

  function confirmDelete() {
    deleteCandidate(candidate.id, {
      onSuccess: () => {
        setShowDeleteModal(false);
        if (nextId) goTo(nextId);
        else if (prevId) goTo(prevId);
        else navigate("/candidates");
      },
      onError: (err) => {
        console.error("[CandidateDetail] delete error:", err);
        toast.error("Erreur lors de la suppression du candidat");
        setShowDeleteModal(false);
      },
    });
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="mx-auto max-w-6xl p-6 lg:p-8">
      {/* Top bar */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-2 text-sm text-gray-500 transition-colors hover:text-gray-900"
        >
          <ArrowLeft size={16} />
          Retour
        </button>

        <div className="flex items-center gap-2">
          {candidateIds && (
            <>
              <button
                onClick={() => goTo(prevId)}
                disabled={!prevId}
                title="Candidat précédent (←)"
                className="flex items-center gap-1.5 rounded-full border border-gray-200 bg-white px-3 py-2 text-xs font-medium text-gray-700 transition-all hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <ChevronLeft size={14} />
                Précédent
              </button>

              <span className="px-2 text-xs text-gray-400 tabular-nums">
                {currentIndex + 1} / {candidateIds.length}
              </span>

              <button
                onClick={() => goTo(nextId)}
                disabled={!nextId}
                title="Candidat suivant (→)"
                className="flex items-center gap-1.5 rounded-full border border-gray-200 bg-white px-3 py-2 text-xs font-medium text-gray-700 transition-all hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Suivant
                <ChevronRight size={14} />
              </button>
            </>
          )}

          <button
            onClick={() => setShowDeleteModal(true)}
            className="flex items-center gap-2 rounded-full border border-red-200 bg-white px-4 py-2 text-xs font-medium text-red-600 transition-all hover:border-red-300 hover:bg-red-50"
          >
            <Trash2 size={14} />
            Supprimer
          </button>
        </div>
      </div>

      {/* ── Header card ───────────────────────────────────────────────────── */}
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

              <div className="mt-3 flex flex-wrap gap-2">
                {linkedJob && (
                  <div className="inline-flex items-center gap-1.5 rounded-full bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-700">
                    <Briefcase size={12} />
                    {linkedJob.title}
                  </div>
                )}
                {hierarchyLevel && (
                  <div className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
                    {HIERARCHY_LABELS[hierarchyLevel] ?? hierarchyLevel}
                  </div>
                )}
                {domain && (
                  <div className="inline-flex items-center gap-1.5 rounded-full bg-violet-50 px-3 py-1 text-xs font-semibold text-violet-600">
                    {DOMAIN_LABELS[domain] ?? domain}
                  </div>
                )}
              </div>
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

      {/* ── Content grid ──────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">

        {/* ── LEFT COLUMN ───────────────────────────────────────────────── */}
        <div className="space-y-6">

          {/* Contact & meta */}
          <SectionCard className="p-5">
            <SectionTitle>Informations</SectionTitle>
            <div className="space-y-4">
              <InfoRow icon={Mail}          label="Email"      value={candidate.email} />
              <InfoRow icon={Phone}         label="Téléphone"  value={candidate.phone} />
              <InfoRow icon={Briefcase}     label="Expérience" value={experienceLabel} />
              <InfoRow icon={GraduationCap} label="Formation détectée"
                value={detectedEducation
                  ? detectedEducation.replace(/_/g, " ").replace("bac+", "Bac+")
                  : null}
              />
              {linkedJob && (
                <InfoRow icon={Briefcase} label="Poste ciblé" value={linkedJob.title} />
              )}
            </div>

            {candidate.cv_file_url && (
              <button
                onClick={() => openCV(candidate.cv_file_url)}
                disabled={isOpeningCV}
                className="mt-6 flex w-full items-center justify-center gap-2 rounded-2xl border border-gray-200 bg-white px-4 py-3 text-sm font-medium text-gray-700 transition-all hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-700 disabled:opacity-50"
              >
                <ExternalLink size={16} />
                {isOpeningCV ? "Ouverture..." : "Voir le CV"}
              </button>
            )}
          </SectionCard>

          {/* ── Score ATS ───────────────────────────────────────────────── */}
          <SectionCard className="overflow-hidden">
            <div className="flex items-center gap-2 border-b border-gray-50 px-5 py-4">
              <Sparkles size={15} className="text-indigo-400" />
              <h2 className="flex-1 text-sm font-bold text-gray-900">Score ATS</h2>
            </div>

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
                      score={dims[dim.key]}
                    />
                  ))}
                </div>
              ) : hasScoreButNoDimensions ? (
                <div className="py-6 text-center">
                  <AlertTriangle size={16} className="mx-auto mb-2 text-amber-400" />
                  <p className="text-xs text-gray-500">Détail des dimensions non disponible</p>
                </div>
              ) : isPendingJob ? (
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

          {/* ── Penalty alerts ──────────────────────────────────────────── */}
          {penaltyDetails.length > 0 && (
            <SectionCard className="px-5 py-4">
              <div className="mb-3 flex items-center gap-2">
                <ShieldAlert size={14} className="text-red-400" />
                <h2 className="text-sm font-bold text-gray-900">Alertes de carence</h2>
              </div>
              <div className="space-y-2">
                {penaltyDetails.map((p, i) => (
                  <PenaltyChip key={i} penalty={p} />
                ))}
              </div>
            </SectionCard>
          )}

          {/* ── Feedback ────────────────────────────────────────────────── */}
          <SectionCard className="px-5 py-4">
            <p className="mb-1 text-sm font-bold text-gray-900">Ce candidat vous convient ?</p>
            <p className="mb-4 text-xs text-gray-400">
              Votre retour affine les poids du scorer via gradient descent.
            </p>
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

          {/* ── Keyword analysis ────────────────────────────────────────── */}
          {(matched.length > 0 || missing.length > 0) && (
            <SectionCard className="px-5 py-4">
              <h2 className="mb-4 text-sm font-bold text-gray-900">Mots-clés détectés</h2>

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

        {/* ── RIGHT COLUMN ──────────────────────────────────────────────── */}
        <div className="space-y-6 lg:col-span-2">

          {/* AI summary */}
          {aiSummary && (
            <SectionCard className="p-6">
              <div className="mb-3 flex items-center gap-2">
                <Sparkles size={15} className="text-indigo-400" />
                <h2 className="text-sm font-semibold text-gray-900">Résumé IA</h2>
              </div>
              <p className="whitespace-pre-line text-sm leading-relaxed text-gray-600">
                {aiSummary}
              </p>
            </SectionCard>
          )}

          {/* Raw extracted data */}
          <SectionCard className="p-6">
            <div className="mb-4 flex items-center gap-2">
              <FileText size={15} className="text-gray-400" />
              <h2 className="text-sm font-semibold text-gray-900">Données extraites par l'IA</h2>
            </div>
            {aiRawDisplay ? (
              <pre className="max-h-125 overflow-auto rounded-2xl border border-gray-100 bg-gray-50 p-4 text-xs leading-relaxed text-gray-700">
                {JSON.stringify(aiRawDisplay, null, 2)}
              </pre>
            ) : (
              <p className="text-sm text-gray-400">Aucune donnée structurée disponible.</p>
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

      {/* Delete confirmation modal */}
      {showDeleteModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
          onClick={() => !isDeleting && setShowDeleteModal(false)}
        >
          <div
            className="w-full max-w-sm rounded-xl border border-gray-200 bg-white p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="mb-1 text-sm font-semibold text-gray-900">
              Supprimer le candidat
            </h2>
            <p className="mb-6 text-xs text-gray-500">
              <span className="font-medium text-gray-700">{candidate.full_name}</span>
              {" "}sera définitivement supprimé. Cette action est irréversible.
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setShowDeleteModal(false)}
                disabled={isDeleting}
                className="h-9 flex-1 rounded-lg border border-gray-200 bg-white text-xs font-medium text-gray-600 transition-colors hover:bg-gray-50 disabled:opacity-50"
              >
                Annuler
              </button>
              <button
                onClick={confirmDelete}
                disabled={isDeleting}
                className="h-9 flex-1 rounded-lg bg-red-600 text-xs font-medium text-white transition-colors hover:bg-red-700 disabled:opacity-50"
              >
                {isDeleting ? "Suppression…" : "Supprimer"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}