// frontend/src/pages/Dashboard.jsx

import { useState, useMemo } from "react";
import { RefreshCw, Upload, ChevronDown, ChevronRight } from "lucide-react";

import { useCandidates, useDriveSync } from "../hooks/useCandidates";
import { useJobs } from "../hooks/useJobs";
import KanbanBoard from "../components/KanbanBoard";
import UploadCVModal from "../components/UploadCVModal";
import ScoreBadge from "../components/ScoreBadge";
import ScorePanel from "../components/Scorepanel";

import { JOB_DOMAINS } from "./JobList";
import { classifyCandidate } from "../utils/domainClassifier";

// ─── Domain label lookup ──────────────────────────────────────────────────────

function domainLabel(key) {
  return JOB_DOMAINS.find((d) => d.value === key)?.label ?? "Non classifié";
}

// ─── Stat Card ────────────────────────────────────────────────────────────────

function StatCard({ label, value }) {
  return (
    <div className="border border-gray-200 rounded-lg p-5 bg-white">
      <p className="text-xs font-medium text-gray-400 uppercase tracking-widest mb-3">{label}</p>
      <p className="text-4xl font-semibold text-gray-900 tabular-nums">{value}</p>
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
        isSelected ? "bg-gray-100" : "hover:bg-gray-50"
      }`}
    >
      <span className="text-xs text-gray-300 w-4 text-right shrink-0 tabular-nums">{index + 1}</span>
      <div className="h-7 w-7 rounded-full bg-gray-100 border border-gray-200 flex items-center justify-center text-xs font-semibold text-gray-600 shrink-0">
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
      className={`flex flex-col gap-2 rounded-lg border p-3.5 text-left transition-colors ${
        isActive
          ? "border-gray-900 bg-gray-900 text-white"
          : "border-gray-200 bg-white hover:border-gray-400"
      }`}
    >
      <div className="flex items-center justify-between">
        <span
          className={`text-xs font-semibold rounded px-1.5 py-0.5 tabular-nums ${
            isActive ? "bg-white/10 text-white" : "bg-gray-100 text-gray-500"
          }`}
        >
          {candidateCount}
        </span>
      </div>
      <p className={`text-xs font-medium leading-snug ${isActive ? "text-white" : "text-gray-700"}`}>
        {job.title}
      </p>
    </button>
  );
}

// ─── Domain Folder ────────────────────────────────────────────────────────────

function DomainFolder({ domainKey, candidates, jobs, onSelectCandidate, selectedCandidateId }) {
  const [open, setOpen] = useState(false);
  const label    = domainLabel(domainKey);
  const sorted   = [...candidates].sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
  const jobCount = jobs.filter((j) => j.domain === domainKey).length;

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-3 px-4 py-3 bg-white hover:bg-gray-50 transition-colors text-left"
      >
        {open
          ? <ChevronDown size={13} className="text-gray-400 shrink-0" />
          : <ChevronRight size={13} className="text-gray-400 shrink-0" />
        }
        <span className="flex-1 text-sm font-medium text-gray-800 truncate">{label}</span>
        {jobCount > 0 && (
          <span className="text-xs text-gray-400 shrink-0">{jobCount} poste{jobCount > 1 ? "s" : ""}</span>
        )}
        <span className="text-xs font-semibold text-gray-500 shrink-0 tabular-nums ml-2">
          {candidates.length}
        </span>
      </button>

      {open && (
        <div className="border-t border-gray-100 divide-y divide-gray-50 bg-white">
          {sorted.map((c) => {
            const initials = (c.full_name ?? "?")
              .split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();
            const linkedJob = jobs.find((j) => j.id === c.job_id);
            return (
              <button
                key={c.id}
                onClick={() => onSelectCandidate(c)}
                className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors ${
                  selectedCandidateId === c.id ? "bg-gray-100" : "hover:bg-gray-50"
                }`}
              >
                <div className="h-6 w-6 rounded-full bg-gray-100 border border-gray-200 flex items-center justify-center text-xs font-semibold text-gray-600 shrink-0">
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
      {/* Section Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 flex items-center justify-center rounded-xl bg-blue-50 text-xl shadow-sm">
          📁
        </div>

        <div>
          <h2 className="text-sm font-semibold text-gray-900">
            Dossiers par secteur
          </h2>

          <p className="text-xs text-gray-400">
            classement automatique par poste
          </p>
        </div>
      </div>

      {/* Domain Folders */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
        {grouped.map(([domainKey, domainCandidates]) => (
          <div
            key={domainKey}
            className="bg-white border border-gray-200 rounded-2xl p-4 hover:border-blue-300 hover:shadow-md transition-all duration-200"
          >
            {/* Folder Header */}
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 flex items-center justify-center rounded-xl bg-blue-50 text-lg">
                  📁
                </div>

                <div>
                  {/* <h3 className="text-sm font-semibold text-gray-900 capitalize">
                    {domainKey}
                  </h3> */}

                  {/* <p className="text-xs text-gray-400">
                    {domainCandidates.length} candidats
                  </p> */}
                </div>
              </div>
            </div>

            {/* Folder Content */}
            <DomainFolder
              domainKey={domainKey}
              candidates={domainCandidates}
              jobs={jobs}
              onSelectCandidate={onSelectCandidate}
              selectedCandidateId={selectedCandidateId}
            />
          </div>
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
      <div className="fixed inset-0 bg-black/30 z-30 lg:hidden" onClick={onClose} />
      <aside className="fixed right-0 top-0 bottom-0 z-40 w-full max-w-sm bg-white border-l border-gray-200 overflow-y-auto shadow-xl lg:static lg:w-80 lg:shadow-none lg:z-auto">
        <div className="sticky top-0 z-10 flex items-center justify-between px-5 py-4 border-b border-gray-100 bg-white">
          <div>
            <p className="text-sm font-semibold text-gray-900">{candidate.full_name ?? "Candidate"}</p>
            <p className="text-xs text-gray-400">{candidate.current_position ?? ""}</p>
          </div>
          <button
            onClick={onClose}
            className="text-xs font-medium text-gray-400 hover:text-gray-700 transition-colors px-2 py-1 rounded border border-gray-200 hover:border-gray-300"
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
  const { data: jobs = [] }       = useJobs();
  const { mutate: syncDrive, isPending: isSyncing } = useDriveSync();

  const [showUpload, setShowUpload]               = useState(false);
  const [activeJob, setActiveJob]                 = useState(null);
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
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 lg:px-8 py-4 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-sm font-semibold text-gray-900">Dashboard</h1>
          <p className="text-xs text-gray-400">Pipeline de recrutement</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => syncDrive()}
            disabled={isSyncing}
            className="flex items-center gap-2 rounded-md border border-orange-400 bg-orange-50 px-3 py-1.5 text-xs font-medium text-orange-700 hover:bg-orange-100 hover:border-orange-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <RefreshCw size={12} className={isSyncing ? "animate-spin" : ""} />
            {isSyncing ? "Sync…" : "Sync Drive"}
          </button>
          <button
            onClick={() => setShowUpload(true)}
            className="flex items-center gap-2 rounded-md bg-gray-900 hover:bg-gray-700 px-3 py-1.5 text-xs font-medium text-white transition-colors"
          >
            <Upload size={12} />
            Uploader un CV
          </button>
        </div>
      </header>

      <div className={selectedCandidate ? "lg:grid lg:grid-cols-[1fr_320px]" : ""}>
        <main className="min-w-0 px-6 lg:px-8 py-6 space-y-8">

          {/* Stats */}
          <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
            {statItems.map((s) => (
              <StatCard key={s.label} label={s.label} value={s.value} />
            ))}
          </div>

          {/* Top 5 */}
          <section>
            <div className="flex items-baseline gap-3 mb-4">
              <h2 className="text-sm font-semibold text-gray-900">Top 5 candidats</h2>
              <span className="text-xs text-gray-400">par score ATS</span>
            </div>
            {topCandidates.length === 0 ? (
              <p className="text-sm text-gray-400">Aucun candidat scoré pour l'instant.</p>
            ) : (
              <div className="bg-white rounded-lg border border-gray-200 divide-y divide-gray-100 overflow-hidden">
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
              <p className="mt-2 text-xs text-gray-500">
                Analyse ouverte → <span className="font-medium text-gray-700">{selectedCandidate.full_name}</span>
              </p>
            )}
          </section>

          {/* Domain Folders */}
          <DomainFoldersSection
            candidates={candidates}
            jobs={jobs}
            onSelectCandidate={handleCandidateSelect}
            selectedCandidateId={selectedCandidate?.id}
          />

          {/* Open Positions */}
          {jobs.length > 0 && (
            <section>
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-baseline gap-3">
                  <h2 className="text-sm font-semibold text-gray-900">Postes ouverts</h2>
                  <span className="text-xs text-gray-400">cliquez pour filtrer</span>
                </div>
                {activeJob && (
                  <button
                    onClick={() => setActiveJob(null)}
                    className="text-xs text-gray-400 hover:text-gray-700 transition-colors"
                  >
                    Effacer le filtre
                  </button>
                )}
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2 ">
                {jobs.map((job) => (
                  <JobChip
                    key={job.id}
                    job={job}
                    isActive={activeJob?.id === job.id}
                    candidateCount={candidates.filter((c) => c.job_id === job.id).length}
                    onClick={() => handleJobClick(job)}
                  />
                ))}
              </div>
            </section>
          )}

          {/* Kanban */}
          <section>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-sm font-semibold text-gray-900">Pipeline Kanban</h2>
                <p className="text-xs text-gray-400 mt-0.5">Suivi des candidats par étape</p>
              </div>
              {activeJob && (
                <span className="inline-flex items-center gap-1.5 rounded border border-gray-300 bg-white px-2.5 py-1 text-xs font-medium text-gray-700">
                  {activeJob.title}
                </span>
              )}
            </div>
            <div className="rounded-lg border border-gray-200 overflow-hidden">
              <KanbanBoard candidates={candidates} filterJobId={activeJob?.id ?? null} />
            </div>
          </section>

        </main>

        {selectedCandidate && (
          <ScorePanelDrawer candidate={selectedCandidate} onClose={() => setSelectedCandidate(null)} />
        )}
      </div>

      {showUpload && <UploadCVModal onClose={() => setShowUpload(false)} />}
    </div>
  );
}