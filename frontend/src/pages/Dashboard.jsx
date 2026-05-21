import { useState } from "react";
import {
  Users,
  Briefcase,
  TrendingUp,
  CheckCircle,
  RefreshCw,
  Upload,
  Sparkles,
} from "lucide-react";

import {
  useCandidates,
  useDriveSync,
} from "../hooks/useCandidates";

import { useJobs } from "../hooks/useJobs";

import KanbanBoard from "../components/KanbanBoard";
import UploadCVModal from "../components/UploadCVModal";

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
          <p className="text-sm text-gray-500 font-medium">
            {label}
          </p>

          <h3 className="text-3xl font-bold text-gray-900 mt-2">
            {value}
          </h3>
        </div>

        <div
          className={`
            p-4 rounded-2xl
            ${color}
            shadow-lg
          `}
        >
          <Icon size={24} className="text-white" />
        </div>
      </div>

      <div
        className={`
          absolute -right-6 -bottom-6
          w-24 h-24 rounded-full blur-2xl opacity-20
          ${lightColor}
        `}
      />
    </div>
  );
}

export default function Dashboard() {
  const { data: candidates = [] } = useCandidates();

  const { data: jobs = [] } = useJobs();

  const {
    mutate: syncDrive,
    isPending: isSyncing,
  } = useDriveSync();

  const [showUpload, setShowUpload] =
    useState(false);

  const [activeJob, setActiveJob] =
    useState(null);

  const stats = {
    total: candidates.length,

    inProgress: candidates.filter((c) =>
      ["screening", "interview", "offer"].includes(
        c.status
      )
    ).length,

    hired: candidates.filter(
      (c) => c.status === "hired"
    ).length,

    activeJobs: jobs.length,
  };

  function handleJobClick(job) {
    setActiveJob((prev) =>
      prev?.id === job.id ? null : job
    );
  }

  return (
    <div className="p-8 bg-gray-50 min-h-screen">
      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-5 mb-8">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <div className="p-2 rounded-xl bg-indigo-100">
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

          <p className="text-gray-500 mt-2 text-sm">
            Vue d'ensemble du pipeline de
            recrutement
          </p>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-3">
          {/* Sync Button */}
          <button
            onClick={() => syncDrive()}
            disabled={isSyncing}
            className="
              group relative overflow-hidden
              flex items-center gap-2
              px-5 py-3
              rounded-2xl
              bg-linear-to-r from-indigo-600 to-blue-600
              text-white text-sm font-semibold
              shadow-md hover:shadow-xl
              transition-all duration-300
              hover:-translate-y-0.5
              active:scale-[0.98]
              disabled:opacity-70 disabled:cursor-not-allowed
            "
          >
            <span className="absolute inset-0 bg-white/10 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />

            <div className="relative z-10 p-1 rounded-lg bg-white/15">
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

          {/* Upload Button */}
          <button
            onClick={() =>
              setShowUpload(true)
            }
            className="
              group
              flex items-center gap-2
              px-5 py-3
              rounded-2xl
              border border-gray-200
              bg-white
              text-gray-700 text-sm font-semibold
              shadow-sm hover:shadow-lg
              hover:border-indigo-300
              hover:bg-indigo-50
              hover:text-indigo-700
              transition-all duration-300
              hover:-translate-y-0.5
              active:scale-[0.98]
            "
          >
            <div className="p-1 rounded-lg bg-gray-100 group-hover:bg-indigo-100 transition-colors">
              <Upload
                size={16}
                className="group-hover:-translate-y-0.5 transition-transform"
              />
            </div>

            <span>Uploader un CV</span>
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-5 mb-8">
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

      {/* Jobs */}
      {jobs.length > 0 && (
        <div className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-xl font-bold text-gray-900">
                Postes ouverts
              </h2>

              <p className="text-sm text-gray-500 mt-1">
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
                  px-4 py-2
                  rounded-xl
                  bg-white
                  border border-gray-200
                  text-sm font-medium text-gray-600
                  hover:bg-gray-50
                  hover:text-gray-900
                  transition-all
                "
              >
                Effacer le filtre
              </button>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {jobs.map((job) => {
              const isActive =
                activeJob?.id === job.id;

              const jobCandidates =
                candidates.filter(
                  (c) => c.job_id === job.id
                );

              return (
                <button
                  key={job.id}
                  onClick={() =>
                    handleJobClick(job)
                  }
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
                  {/* Glow */}
                  {isActive && (
                    <div className="absolute -top-10 -right-10 w-24 h-24 bg-indigo-400/20 rounded-full blur-2xl" />
                  )}

                  <div className="relative">
                    <div className="flex items-start justify-between">
                      <div>
                        <h3 className="font-semibold text-gray-900 text-sm">
                          {job.title}
                        </h3>

                        {job.description && (
                          <p className="text-xs text-gray-500 mt-1 line-clamp-2">
                            {job.description}
                          </p>
                        )}
                      </div>

                      <div
                        className={`
                          p-2 rounded-xl
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
                          px-2.5 py-1
                          rounded-lg
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
            })}
          </div>
        </div>
      )}

      {/* Kanban */}
      <div className="rounded-3xl border border-gray-200 bg-white shadow-sm overflow-hidden">
        {/* Header */}
        <div className="border-b border-gray-100 px-6 py-5">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div>
              <h2 className="text-xl font-bold text-gray-900">
                Pipeline Kanban
              </h2>

              <p className="text-sm text-gray-500 mt-1">
                Suivi des candidats par étape
              </p>
            </div>

            {activeJob && (
              <div className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-100 text-indigo-700 text-sm font-medium">
                <Briefcase size={15} />
                {activeJob.title}
              </div>
            )}
          </div>
        </div>

        {/* Board */}
        <div className="p-6">
          <KanbanBoard
            candidates={candidates}
            filterJobId={
              activeJob?.id ?? null
            }
          />
        </div>
      </div>

      {/* Upload Modal */}
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