// frontend/src/pages/Dashboard.jsx

import { useState, useMemo } from "react";
import { RefreshCw, Upload, ChevronDown, ChevronRight, Briefcase, Users, TrendingUp, CheckCircle, CheckCircle2, AlertTriangle, X, Sparkles } from "lucide-react";

import { useCandidates, useDriveSync, useDriveSyncStatus } from "../hooks/useCandidates";
import { useJobs } from "../hooks/useJobs";
import KanbanBoard from "../components/KanbanBoard";
import UploadCVModal from "../components/UploadCVModal";
import AIProcessingModal from "../components/AIProcessingModal";
import DriveImportModal from "../components/DriveImportModal";
import ScoreBadge from "../components/ScoreBadge";
import ScorePanel from "../components/Scorepanel";

import { JOB_DOMAINS } from "./JobList";
import { classifyCandidate } from "../utils/domainClassifier";

// ─── Domain label lookup ──────────────────────────────────────────────────────

function domainLabel(key) {
  return JOB_DOMAINS.find((d) => d.value === key)?.label ?? "Non classifié";
}

// ─── Stat Card ────────────────────────────────────────────────────────────────

const STAT_ICONS = {
  "Total candidats": Users,
  "En cours": TrendingUp,
  "Embauchés": CheckCircle,
  "Postes actifs": Briefcase,
};

function StatCard({ label, value }) {
  const Icon = STAT_ICONS[label] ?? Users;
  return (
    <div className="bg-white border border-gray-100 rounded-2xl p-5 flex items-center gap-4 shadow-sm hover:shadow-md transition-shadow">
      <div className="w-10 h-10 rounded-xl bg-gray-50 flex items-center justify-center shrink-0">
        <Icon size={18} className="text-gray-400" />
      </div>
      <div>
        <p className="text-2xl font-bold text-gray-900 tabular-nums leading-none mb-1">{value}</p>
        <p className="text-xs text-gray-400 font-medium">{label}</p>
      </div>
    </div>
  );
}

// ─── Section Header ───────────────────────────────────────────────────────────

function SectionHeader({ title, subtitle, action }) {
  return (
    <div className="flex items-end justify-between mb-4">
      <div>
        <h2 className="text-sm font-semibold text-gray-900">{title}</h2>
        {subtitle && <p className="text-xs text-gray-400 mt-0.5">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

// ─── Top Candidate Row ────────────────────────────────────────────────────────

function TopCandidateRow({ candidate, index, onSelect, isSelected }) {
  const initials = (candidate.full_name ?? "?")
    .split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();

  return (
    <button
      onClick={() => onSelect(candidate)}
      className={`w-full flex items-center gap-4 px-4 py-3 text-left transition-colors ${
        isSelected ? "bg-gray-50" : "hover:bg-gray-50"
      }`}
    >
      <span className="text-xs text-gray-300 w-4 text-right shrink-0 tabular-nums">{index + 1}</span>
      <div className="h-8 w-8 rounded-full bg-linear-to-br from-gray-100 to-gray-200 border border-gray-200 flex items-center justify-center text-xs font-semibold text-gray-600 shrink-0">
        {initials}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-900 truncate">{candidate.full_name ?? "Unknown"}</p>
        <p className="text-xs text-gray-400 truncate">{candidate.current_position ?? "—"}</p>
      </div>
      <ScoreBadge score={candidate.score} />
    </button>
  );
}

// ─── Job Chip ─────────────────────────────────────────────────────────────────

function JobChip({ job, isActive, candidateCount, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`flex flex-col gap-2 rounded-xl border p-3.5 text-left transition-all ${
        isActive
          ? "border-gray-900 bg-gray-900 text-white shadow-md"
          : "border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm"
      }`}
    >
      <span
        className={`text-xs font-semibold rounded-md px-1.5 py-0.5 tabular-nums w-fit ${
          isActive ? "bg-white/15 text-white" : "bg-gray-100 text-gray-500"
        }`}
      >
        {candidateCount} candidat{candidateCount !== 1 ? "s" : ""}
      </span>
      <p className={`text-xs font-medium leading-snug ${isActive ? "text-white" : "text-gray-700"}`}>
        {job.title}
      </p>
    </button>
  );
}

// ─── Domain Folder ────────────────────────────────────────────────────────────

function DomainFolder({ domainKey, candidates, jobs, onSelectCandidate, selectedCandidateId }) {
  const [open, setOpen] = useState(false);
  const label = domainLabel(domainKey);
  const sorted = [...candidates].sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
  const jobCount = jobs.filter((j) => j.domain === domainKey).length;

  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden bg-white">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-gray-50 transition-colors text-left"
      >
        {open
          ? <ChevronDown size={13} className="text-gray-400 shrink-0" />
          : <ChevronRight size={13} className="text-gray-400 shrink-0" />}
        <span className="flex-1 text-sm font-medium text-gray-800 truncate">{label}</span>
        {jobCount > 0 && (
          <span className="text-xs text-gray-400 shrink-0">{jobCount} poste{jobCount > 1 ? "s" : ""}</span>
        )}
        <span className="text-xs font-semibold bg-gray-100 text-gray-500 rounded-full px-2 py-0.5 tabular-nums ml-2">
          {candidates.length}
        </span>
      </button>

      {open && (
        <div className="border-t border-gray-100 divide-y divide-gray-50">
          {sorted.map((c) => {
            const initials = (c.full_name ?? "?")
              .split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();
            const linkedJob = jobs.find((j) => j.id === c.job_id);
            return (
              <button
                key={c.id}
                onClick={() => onSelectCandidate(c)}
                className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors ${
                  selectedCandidateId === c.id ? "bg-gray-50" : "hover:bg-gray-50"
                }`}
              >
                <div className="h-6 w-6 rounded-full bg-linear-to-br from-gray-100 to-gray-200 border border-gray-200 flex items-center justify-center text-xs font-semibold text-gray-600 shrink-0">
                  {initials}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-gray-900 truncate">{c.full_name ?? "Unknown"}</p>
                  <p className="text-xs text-gray-400 truncate">
                    {linkedJob ? linkedJob.title : (c.current_position ?? "—")}
                  </p>
                </div>
                <ScoreBadge score={c.score} />
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─── Domain Folders Section ───────────────────────────────────────────────────

function DomainFoldersSection({ candidates, jobs, onSelectCandidate, selectedCandidateId }) {
  const grouped = useMemo(() => {
    const jobById = {};
    for (const j of jobs) jobById[j.id] = j;

    const map = {};
    for (const c of candidates) {
      const linkedJob = c.job_id ? jobById[c.job_id] : null;
      const domain = classifyCandidate(c, linkedJob);
      if (!map[domain]) map[domain] = [];
      map[domain].push(c);
    }

    return Object.entries(map).sort(([aKey, aList], [bKey, bList]) => {
      if (aKey === "unknown") return 1;
      if (bKey === "unknown") return -1;
      return bList.length - aList.length;
    });
  }, [candidates, jobs]);

  if (grouped.length === 0) return null;

  return (
    <section>
      <SectionHeader
        title="🗂️ Dossiers par secteur"
        subtitle="Classement automatique par poste"
      />
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
        {grouped.map(([domainKey, domainCandidates]) => (
          <DomainFolder
            key={domainKey}
            domainKey={domainKey}
            candidates={domainCandidates}
            jobs={jobs}
            onSelectCandidate={onSelectCandidate}
            selectedCandidateId={selectedCandidateId}
          />
        ))}
      </div>
    </section>
  );
}

// ─── Score Panel Drawer ───────────────────────────────────────────────────────

function ScorePanelDrawer({ candidate, onClose }) {
  if (!candidate) return null;
  return (
    <>
      <div className="fixed inset-0 bg-black/20 z-30 lg:hidden" onClick={onClose} />
      <aside className="fixed right-0 top-0 bottom-0 z-40 w-full max-w-sm bg-white border-l border-gray-100 overflow-y-auto shadow-2xl lg:static lg:w-80 lg:shadow-none lg:z-auto">
        <div className="sticky top-0 z-10 flex items-center justify-between px-5 py-4 border-b border-gray-100 bg-white/95 backdrop-blur-sm">
          <div>
            <p className="text-sm font-semibold text-gray-900">{candidate.full_name ?? "Candidate"}</p>
            <p className="text-xs text-gray-400">{candidate.current_position ?? ""}</p>
          </div>
          <button
            onClick={onClose}
            className="text-xs font-medium text-gray-400 hover:text-gray-700 transition-colors px-2.5 py-1.5 rounded-lg border border-gray-200 hover:border-gray-300"
          >
            Fermer
          </button>
        </div>
        <div className="p-4">
          <ScorePanel candidate={candidate} />
        </div>
      </aside>
    </>
  );
}

// ─── Main Dashboard ───────────────────────────────────────────────────────────

export default function Dashboard() {
  const { data: candidates = [] } = useCandidates();
  const { data: jobs = [] } = useJobs();

  const [showUpload, setShowUpload] = useState(false);
  const [showAIModal, setShowAIModal] = useState(false);
  const [showDriveModal, setShowDriveModal] = useState(false);
  const [activeJob, setActiveJob] = useState(null);
  const [selectedCandidate, setSelectedCandidate] = useState(null);

  const stats = useMemo(() => ({
    total:      candidates.length,
    inProgress: candidates.filter((c) => ["screening", "interview", "offer"].includes(c.status)).length,
    hired:      candidates.filter((c) => c.status === "hired").length,
    activeJobs: jobs.length,
  }), [candidates, jobs]);

  const topCandidates = useMemo(() =>
    [...candidates].filter((c) => c.score != null).sort((a, b) => b.score - a.score).slice(0, 5),
  [candidates]);

  function handleJobClick(job) {
    setActiveJob((prev) => (prev?.id === job.id ? null : job));
  }
  function handleCandidateSelect(candidate) {
    setSelectedCandidate((prev) => prev?.id === candidate.id ? null : candidate);
  }

  const statItems = [
    { label: "Total candidats", value: stats.total      },
    { label: "En cours",        value: stats.inProgress },
    { label: "Embauchés",       value: stats.hired      },
    { label: "Postes actifs",   value: stats.activeJobs },
  ];

  return (
    <div className="min-h-screen bg-gray-50">

      {/* ── Header ── */}
      <header className="bg-white border-b border-gray-100 px-6 lg:px-8 py-4 flex items-center justify-between gap-4 sticky top-0 z-20">
        <div>
          <h1 className="text-sm font-semibold text-gray-900">Pipeline de recrutement</h1>
          <p className="text-xs text-gray-400">Vue d'ensemble</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowDriveModal(true)}
            className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 hover:border-gray-300 transition-colors"
          >
            <RefreshCw size={12} />
            Import Drive
          </button>
          <button
            onClick={() => setShowUpload(true)}
            className="flex items-center gap-2 rounded-lg bg-gray-900 hover:bg-gray-700 px-3 py-1.5 text-xs font-medium text-white transition-colors"
          >
            <Upload size={12} />
            Charger des CV
          </button>
          <button
            onClick={() => setShowAIModal(true)}
            className="flex items-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50 hover:bg-indigo-100 px-3 py-1.5 text-xs font-medium text-indigo-700 transition-colors"
          >
            <Sparkles size={12} />
            Analyse IA
          </button>
        </div>
      </header>



      <div className={selectedCandidate ? "lg:grid lg:grid-cols-[1fr_320px]" : ""}>
        <main className="min-w-0 px-6 lg:px-8 py-8 space-y-10">

          {/* ── 1. Stats ── */}
          <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
            {statItems.map((s) => (
              <StatCard key={s.label} label={s.label} value={s.value} />
            ))}
          </div>

          {/* ── 2. Top 5 ── */}
          <section>
            <SectionHeader title="Top 5 candidats" subtitle="Par score ATS" />
            {topCandidates.length === 0 ? (
              <div className="bg-white rounded-2xl border border-gray-100 px-5 py-8 text-center">
                <p className="text-sm text-gray-400">Aucun candidat scoré pour l'instant.</p>
              </div>
            ) : (
              <div className="bg-white rounded-2xl border border-gray-100 divide-y divide-gray-50 overflow-hidden shadow-sm">
                {topCandidates.map((c, i) => (
                  <TopCandidateRow
                    key={c.id}
                    candidate={c}
                    index={i}
                    onSelect={handleCandidateSelect}
                    isSelected={selectedCandidate?.id === c.id}
                  />
                ))}
              </div>
            )}
            {selectedCandidate && (
              <p className="mt-2 text-xs text-gray-400">
                Analyse ouverte →{" "}
                <span className="font-medium text-gray-600">{selectedCandidate.full_name}</span>
              </p>
            )}
          </section>

          {/* ── 3. Domain Folders ── */}
          <DomainFoldersSection
            candidates={candidates}
            jobs={jobs}
            onSelectCandidate={handleCandidateSelect}
            selectedCandidateId={selectedCandidate?.id}
          />

          {/* ── 4. Open Positions ── */}
          {jobs.length > 0 && (
            <section>
              <SectionHeader
                title="Postes ouverts"
                subtitle="Sélectionnez un poste pour filtrer le pipeline"
                action={
                  activeJob && (
                    <button
                      onClick={() => setActiveJob(null)}
                      className="text-xs text-gray-400 hover:text-gray-700 transition-colors"
                    >
                      Effacer le filtre
                    </button>
                  )
                }
              />
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
                {jobs.map((job) => (
                  <JobChip
                    key={job.id}
                    job={job}
                    isActive={activeJob?.id === job.id}
                    candidateCount={job.candidate_count ?? 0}
                    onClick={() => handleJobClick(job)}
                  />
                ))}
              </div>
            </section>
          )}

          {/* ── 5. Kanban ── */}
          <section>
            <SectionHeader
              title="Pipeline Kanban"
              subtitle="Suivi des candidats par étape"
              action={
                activeJob && (
                  <span className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1 text-xs font-medium text-gray-700">
                    {activeJob.title}
                  </span>
                )
              }
            />
            <div className="rounded-2xl border border-gray-200 overflow-hidden bg-white">
              <KanbanBoard candidates={candidates} filterJobId={activeJob?.id ?? null} />
            </div>
          </section>

        </main>

        {selectedCandidate && (
          <ScorePanelDrawer candidate={selectedCandidate} onClose={() => setSelectedCandidate(null)} />
        )}
      </div>

      {showUpload && <UploadCVModal onClose={() => setShowUpload(false)} />}
      {showAIModal && <AIProcessingModal onClose={() => setShowAIModal(false)} />}
      {showDriveModal && <DriveImportModal onClose={() => setShowDriveModal(false)} />}
    </div>
  );
}