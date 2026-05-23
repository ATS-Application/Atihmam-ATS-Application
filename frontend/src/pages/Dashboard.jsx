// ======================================================
// DASHBOARD.jsx
// ======================================================

import { useState, useMemo } from "react";
import {
  Users,
  Briefcase,
  TrendingUp,
  CheckCircle,
  RefreshCw,
  Upload,
  Sparkles,
  Trophy,
} from "lucide-react";

import {
  useCandidates,
  useDriveSync,
} from "../hooks/useCandidates";

import { useJobs } from "../hooks/useJobs";

import KanbanBoard from "../components/KanbanBoard";
import UploadCVModal from "../components/UploadCVModal";
import ScoreBadge from "../components/ScoreBadge";

// ======================================================
// STAT CARD
// ======================================================

function StatCard({
  label,
  value,
  icon: Icon,
  color,
  lightColor,
}) {
  return (
    <div
      className="
        group
        relative overflow-hidden
        rounded-3xl
        border border-gray-200
        bg-white
        p-5
        shadow-sm
        hover:shadow-xl
        transition-all duration-300
        hover:-translate-y-1
      "
    >
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500">
            {label}
          </p>

          <h3 className="mt-2 text-3xl font-bold text-gray-900">
            {value}
          </h3>
        </div>

        <div
          className={`
            rounded-2xl p-4 shadow-lg
            ${color}
          `}
        >
          <Icon size={24} className="text-white" />
        </div>
      </div>

      <div
        className={`
          absolute -right-6 -bottom-6
          h-24 w-24 rounded-full blur-2xl opacity-20
          ${lightColor}
        `}
      />
    </div>
  );
}

// ======================================================
// TOP CANDIDATE CARD
// ======================================================

function TopCandidateCard({
  candidate,
  index,
}) {
  return (
    <div
      className="
        flex items-center justify-between
        rounded-2xl
        border border-gray-100
        p-4
        transition-all duration-200
        hover:border-indigo-200
        hover:bg-indigo-50/40
      "
    >
      <div className="flex items-center gap-4">
        <div
          className="
            flex h-10 w-10 items-center justify-center
            rounded-2xl
            bg-linear-to-br
            from-indigo-500
            to-blue-600
            text-sm font-bold text-white
            shadow-md
          "
        >
          #{index + 1}
        </div>

        <div>
          <p className="font-semibold text-gray-900">
            {candidate.full_name || "Unknown Candidate"}
          </p>

          <p className="text-sm text-gray-500">
            {candidate.current_position || "No position"}
          </p>
        </div>
      </div>

      <ScoreBadge score={candidate.score} />
    </div>
  );
}

// ======================================================
// JOB CARD
// ======================================================

function JobCard({
  job,
  isActive,
  candidates,
  onClick,
}) {
  const jobCandidates = candidates.filter(
    (candidate) => candidate.job_id === job.id
  );

  return (
    <button
      onClick={onClick}
      className={`
        relative overflow-hidden
        rounded-3xl
        border
        p-5
        text-left
        transition-all duration-300
        hover:-translate-y-1
        hover:shadow-xl

        ${
          isActive
            ? `
              border-indigo-300
              bg-linear-to-br
              from-indigo-50
              to-blue-50
              ring-2 ring-indigo-500
            `
            : `
              border-gray-200
              bg-white
              hover:border-indigo-200
            `
        }
      `}
    >
      {isActive && (
        <div
          className="
            absolute -right-10 -top-10
            h-24 w-24
            rounded-full
            bg-indigo-400/20
            blur-2xl
          "
        />
      )}

      <div className="relative">
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-sm font-semibold text-gray-900">
              {job.title}
            </h3>

            {job.description && (
              <p className="mt-1 line-clamp-2 text-xs text-gray-500">
                {job.description}
              </p>
            )}
          </div>

          <div
            className={`
              rounded-xl p-2
              ${
                isActive
                  ? "bg-indigo-100"
                  : "bg-gray-100"
              }
            `}
          >
            <Briefcase
              size={16}
              className={
                isActive
                  ? "text-indigo-600"
                  : "text-gray-500"
              }
            />
          </div>
        </div>

        <div className="mt-4 flex items-center justify-between">
          <span className="text-xs text-gray-500">
            Candidats
          </span>

          <span
            className={`
              rounded-lg
              px-2.5 py-1
              text-xs font-semibold

              ${
                isActive
                  ? `
                    bg-indigo-100
                    text-indigo-700
                  `
                  : `
                    bg-gray-100
                    text-gray-700
                  `
              }
            `}
          >
            {jobCandidates.length}
          </span>
        </div>
      </div>
    </button>
  );
}

// ======================================================
// MAIN COMPONENT
// ======================================================

export default function Dashboard() {
  // ======================================================
  // DATA
  // ======================================================

  const { data: candidates = [] } =
    useCandidates();

  const { data: jobs = [] } = useJobs();

  const {
    mutate: syncDrive,
    isPending: isSyncing,
  } = useDriveSync();

  // ======================================================
  // STATE
  // ======================================================

  const [showUpload, setShowUpload] =
    useState(false);

  const [activeJob, setActiveJob] =
    useState(null);

  // ======================================================
  // MEMOIZED DATA
  // ======================================================

  const stats = useMemo(() => {
    return {
      total: candidates.length,

      inProgress: candidates.filter((c) =>
        [
          "screening",
          "interview",
          "offer",
        ].includes(c.status)
      ).length,

      hired: candidates.filter(
        (c) => c.status === "hired"
      ).length,

      activeJobs: jobs.length,
    };
  }, [candidates, jobs]);

  const topCandidates = useMemo(() => {
    return [...candidates]
      .filter(
        (candidate) =>
          candidate.score !== null &&
          candidate.score !== undefined
      )
      .sort((a, b) => b.score - a.score)
      .slice(0, 5);
  }, [candidates]);

  // ======================================================
  // HANDLERS
  // ======================================================

  function handleJobClick(job) {
    setActiveJob((prev) =>
      prev?.id === job.id ? null : job
    );
  }

  // ======================================================
  // UI
  // ======================================================

  return (
    <div className="min-h-screen bg-gray-50 p-6 lg:p-8">
      {/* HEADER */}

      <div className="mb-8 flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
        {/* LEFT */}

        <div>
          <div className="mb-2 flex items-center gap-2">
            <div className="rounded-xl bg-indigo-100 p-2">
              <Sparkles
                size={18}
                className="text-indigo-600"
              />
            </div>

            <span className="text-sm font-medium text-indigo-600">
              Recruitment Analytics
            </span>
          </div>

          <h1 className="text-4xl font-bold tracking-tight text-gray-900">
            Dashboard
          </h1>

          <p className="mt-2 text-sm text-gray-500">
            Vue d'ensemble du pipeline de
            recrutement
          </p>
        </div>

        {/* ACTIONS */}

        <div className="flex flex-wrap items-center gap-3">
          {/* SYNC */}

          <button
            onClick={() => syncDrive()}
            disabled={isSyncing}
            className="
              group relative overflow-hidden
              flex items-center gap-2
              rounded-2xl
              bg-linear-to-r from-indigo-600 to-blue-600
              px-5 py-3
              text-sm font-semibold text-white
              shadow-md
              transition-all duration-300
              hover:-translate-y-0.5
              hover:shadow-xl
              active:scale-[0.98]
              disabled:cursor-not-allowed
              disabled:opacity-70
            "
          >
            <span
              className="
                absolute inset-0
                bg-white/10
                opacity-0
                transition-opacity duration-300
                group-hover:opacity-100
              "
            />

            <div className="relative z-10 rounded-lg bg-white/15 p-1">
              <RefreshCw
                size={16}
                className={
                  isSyncing
                    ? "animate-spin"
                    : ""
                }
              />
            </div>

            <span className="relative z-10">
              {isSyncing
                ? "Synchronisation..."
                : "Sync Drive"}
            </span>
          </button>

          {/* UPLOAD */}

          <button
            onClick={() =>
              setShowUpload(true)
            }
            className="
              group
              flex items-center gap-2
              rounded-2xl
              border border-gray-200
              bg-white
              px-5 py-3
              text-sm font-semibold text-gray-700
              shadow-sm
              transition-all duration-300
              hover:-translate-y-0.5
              hover:border-indigo-300
              hover:bg-indigo-50
              hover:text-indigo-700
              hover:shadow-lg
              active:scale-[0.98]
            "
          >
            <div
              className="
                rounded-lg bg-gray-100 p-1
                transition-colors
                group-hover:bg-indigo-100
              "
            >
              <Upload
                size={16}
                className="
                  transition-transform
                  group-hover:-translate-y-0.5
                "
              />
            </div>

            <span>Uploader un CV</span>
          </button>
        </div>
      </div>

      {/* STATS */}

      <div className="mb-8 grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Total candidats"
          value={stats.total}
          icon={Users}
          color="bg-gradient-to-br from-blue-500 to-indigo-600"
          lightColor="bg-blue-400"
        />

        <StatCard
          label="En cours"
          value={stats.inProgress}
          icon={TrendingUp}
          color="bg-gradient-to-br from-yellow-400 to-orange-500"
          lightColor="bg-yellow-400"
        />

        <StatCard
          label="Embauchés"
          value={stats.hired}
          icon={CheckCircle}
          color="bg-gradient-to-br from-green-500 to-emerald-600"
          lightColor="bg-green-400"
        />

        <StatCard
          label="Postes actifs"
          value={stats.activeJobs}
          icon={Briefcase}
          color="bg-gradient-to-br from-purple-500 to-fuchsia-600"
          lightColor="bg-purple-400"
        />
      </div>

      {/* TOP CANDIDATES */}

      <div className="mb-8">
        <div
          className="
            rounded-3xl
            border border-gray-200
            bg-white
            p-6
            shadow-sm
          "
        >
          <div className="mb-5 flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2">
                <div className="rounded-xl bg-yellow-100 p-2">
                  <Trophy
                    size={16}
                    className="text-yellow-600"
                  />
                </div>

                <h2 className="text-xl font-bold text-gray-900">
                  Top 5 Candidates
                </h2>
              </div>

              <p className="mt-2 text-sm text-gray-500">
                Highest ATS scores
              </p>
            </div>
          </div>

          {topCandidates.length === 0 ? (
            <p className="text-sm text-gray-400">
              No scored candidates yet.
            </p>
          ) : (
            <div className="space-y-3">
              {topCandidates.map(
                (candidate, index) => (
                  <TopCandidateCard
                    key={candidate.id}
                    candidate={candidate}
                    index={index}
                  />
                )
              )}
            </div>
          )}
        </div>
      </div>

      {/* JOBS */}

      {jobs.length > 0 && (
        <div className="mb-8">
          <div className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-xl font-bold text-gray-900">
                Postes ouverts
              </h2>

              <p className="mt-1 text-sm text-gray-500">
                Cliquez sur un poste pour
                filtrer le pipeline
              </p>
            </div>

            {activeJob && (
              <button
                onClick={() =>
                  setActiveJob(null)
                }
                className="
                  rounded-xl
                  border border-gray-200
                  bg-white
                  px-4 py-2
                  text-sm font-medium text-gray-600
                  transition-all
                  hover:bg-gray-50
                  hover:text-gray-900
                "
              >
                Effacer le filtre
              </button>
            )}
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {jobs.map((job) => (
              <JobCard
                key={job.id}
                job={job}
                candidates={candidates}
                isActive={
                  activeJob?.id === job.id
                }
                onClick={() =>
                  handleJobClick(job)
                }
              />
            ))}
          </div>
        </div>
      )}

      {/* KANBAN */}

      <div
        className="
          overflow-hidden
          rounded-3xl
          border border-gray-200
          bg-white
          shadow-sm
        "
      >
        <div className="border-b border-gray-100 px-6 py-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-xl font-bold text-gray-900">
                Pipeline Kanban
              </h2>

              <p className="mt-1 text-sm text-gray-500">
                Suivi des candidats par étape
              </p>
            </div>

            {activeJob && (
              <div
                className="
                  inline-flex items-center gap-2
                  rounded-xl
                  bg-indigo-100
                  px-4 py-2
                  text-sm font-medium text-indigo-700
                "
              >
                <Briefcase size={15} />
                {activeJob.title}
              </div>
            )}
          </div>
        </div>

        <div className="p-6">
          <KanbanBoard
            candidates={candidates}
            filterJobId={
              activeJob?.id ?? null
            }
          />
        </div>
      </div>

      {/* MODAL */}

      {showUpload && (
        <UploadCVModal
          onClose={() =>
            setShowUpload(false)
          }
        />
      )}
    </div>
  );
}