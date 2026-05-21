import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Search,
  Upload,
  RefreshCw,
  Trash2,
  Briefcase,
} from "lucide-react";

import {
  useCandidates,
  useDeleteCandidate,
  useDriveSync,
} from "../hooks/useCandidates";

import { useJobs } from "../hooks/useJobs";

import StatusBadge from "../components/StatusBadge";
import ScoreBadge from "../components/ScoreBadge";
import UploadCVModal from "../components/UploadCVModal";

const STATUS_OPTIONS = [
  { value: "", label: "Tous les statuts" },
  { value: "applied", label: "Candidature" },
  { value: "screening", label: "Screening" },
  { value: "interview", label: "Entretien" },
  { value: "offer", label: "Offre" },
  { value: "hired", label: "Embauché" },
  { value: "rejected", label: "Refusé" },
];

export default function CandidateList() {
  const navigate = useNavigate();

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [jobFilter, setJobFilter] = useState("");
  const [showUpload, setShowUpload] = useState(false);

  const { data: candidates = [], isLoading } = useCandidates(
    statusFilter ? { status: statusFilter } : {}
  );

  const { data: jobs = [] } = useJobs();

  const { mutate: deleteCandidate } = useDeleteCandidate();

  const { mutate: syncDrive, isPending: isSyncing } = useDriveSync();

  const filtered = candidates.filter((c) => {
    const q = search.toLowerCase();

    const matchesSearch =
      !q ||
      c.full_name?.toLowerCase().includes(q) ||
      c.email?.toLowerCase().includes(q) ||
      c.current_position?.toLowerCase().includes(q) ||
      (c.skills ?? []).some((s) =>
        s.toLowerCase().includes(q)
      );

    const matchesJob =
      !jobFilter || c.job_id === jobFilter;

    return matchesSearch && matchesJob;
  });

  const handleDelete = (e, id) => {
    e.stopPropagation();

    if (confirm("Supprimer ce candidat ?")) {
      deleteCandidate(id);
    }
  };

  return (
    <div className="p-8">
      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-5 mb-7">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 tracking-tight">
            Candidats
          </h1>

          <p className="text-sm text-gray-500 mt-1">
            {filtered.length !== candidates.length
              ? `${filtered.length} / ${candidates.length} candidat(s)`
              : `${candidates.length} candidat(s)`}
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
                className={isSyncing ? "animate-spin" : ""}
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
            onClick={() => setShowUpload(true)}
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

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-6">
        {/* Search */}
        <div className="relative flex-1 min-w-65 max-w-md">
          <Search
            size={17}
            className="
              absolute left-4 top-1/2 -translate-y-1/2
              text-gray-400
            "
          />

          <input
            type="text"
            placeholder="Nom, email, poste, compétence..."
            value={search}
            onChange={(e) =>
              setSearch(e.target.value)
            }
            className="
              w-full
              h-12
              pl-11 pr-4
              rounded-xl
              border border-gray-200
              bg-white
              text-sm
              outline-none
              transition-all
              focus:ring-4 focus:ring-indigo-100
              focus:border-indigo-400
            "
          />
        </div>

        {/* Status Filter */}
        <select
          value={statusFilter}
          onChange={(e) =>
            setStatusFilter(e.target.value)
          }
          className="
            h-12
            px-4
            rounded-xl
            border border-gray-200
            bg-white
            text-sm text-gray-700
            outline-none
            transition-all
            focus:ring-4 focus:ring-indigo-100
            focus:border-indigo-400
          "
        >
          {STATUS_OPTIONS.map((option) => (
            <option
              key={option.value}
              value={option.value}
            >
              {option.label}
            </option>
          ))}
        </select>

        {/* Job Filter */}
        <div className="relative">
          <Briefcase
            size={16}
            className="
              absolute left-4 top-1/2 -translate-y-1/2
              text-gray-400
            "
          />

          <select
            value={jobFilter}
            onChange={(e) =>
              setJobFilter(e.target.value)
            }
            className="
              h-12
              pl-11 pr-4
              rounded-xl
              border border-gray-200
              bg-white
              text-sm text-gray-700
              outline-none
              transition-all
              focus:ring-4 focus:ring-indigo-100
              focus:border-indigo-400
            "
          >
            <option value="">
              Tous les postes
            </option>

            {jobs.map((job) => (
              <option
                key={job.id}
                value={job.id}
              >
                {job.title}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-3xl border border-gray-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              {[
                "Nom",
                "Poste actuel",
                "Compétences",
                "Statut",
                "Score",
                "",
              ].map((header) => (
                <th
                  key={header}
                  className="
                    px-5 py-4
                    text-left
                    text-xs
                    font-semibold
                    uppercase
                    tracking-wider
                    text-gray-500
                  "
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>

          <tbody className="divide-y divide-gray-100">
            {isLoading ? (
              <tr>
                <td
                  colSpan={6}
                  className="py-14 text-center text-gray-400"
                >
                  Chargement...
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td
                  colSpan={6}
                  className="py-14 text-center text-gray-400"
                >
                  {candidates.length === 0
                    ? "Aucun candidat. Uploadez un CV ou synchronisez Drive."
                    : "Aucun candidat ne correspond aux filtres."}
                </td>
              </tr>
            ) : (
              filtered.map((c) => (
                <tr
                  key={c.id}
                  onClick={() =>
                    navigate(`/candidates/${c.id}`)
                  }
                  className="
                    cursor-pointer
                    transition-all
                    hover:bg-indigo-50/40
                  "
                >
                  {/* Candidate */}
                  <td className="px-5 py-4">
                    <div>
                      <p className="font-semibold text-gray-900">
                        {c.full_name || "—"}
                      </p>

                      <p className="text-xs text-gray-400 mt-1">
                        {c.email || "—"}
                      </p>
                    </div>
                  </td>

                  {/* Position */}
                  <td className="px-5 py-4 text-gray-600">
                    {c.current_position || "—"}
                  </td>

                  {/* Skills */}
                  <td className="px-5 py-4">
                    <div className="flex flex-wrap gap-2">
                      {(c.skills ?? [])
                        .slice(0, 3)
                        .map((skill) => (
                          <span
                            key={skill}
                            className="
                              px-2.5 py-1
                              rounded-lg
                              bg-gray-100
                              text-gray-600
                              text-xs
                              font-medium
                            "
                          >
                            {skill}
                          </span>
                        ))}

                      {(c.skills ?? []).length > 3 && (
                        <span
                          className="
                            px-2.5 py-1
                            rounded-lg
                            bg-indigo-100
                            text-indigo-700
                            text-xs
                            font-medium
                          "
                        >
                          +
                          {c.skills.length - 3}
                        </span>
                      )}
                    </div>
                  </td>

                  {/* Status */}
                  <td className="px-5 py-4">
                    <StatusBadge status={c.status} />
                  </td>

                  {/* Score */}
                  <td className="px-5 py-4">
                    <ScoreBadge score={c.score} />
                  </td>

                  {/* Delete */}
                  <td className="px-5 py-4">
                    <button
                      onClick={(e) =>
                        handleDelete(e, c.id)
                      }
                      className="
                        p-2
                        rounded-lg
                        text-gray-400
                        hover:text-red-500
                        hover:bg-red-50
                        transition-colors
                      "
                    >
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Upload Modal */}
      {showUpload && (
        <UploadCVModal
          onClose={() => setShowUpload(false)}
        />
      )}
    </div>
  );
}