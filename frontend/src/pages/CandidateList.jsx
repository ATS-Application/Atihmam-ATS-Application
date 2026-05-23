import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Search,
  Upload,
  RefreshCw,
  Trash2,
  Briefcase,
  Trophy,
  AlertTriangle,
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

  const [search, setSearch] =
    useState("");

  const [statusFilter, setStatusFilter] =
    useState("");

  const [jobFilter, setJobFilter] =
    useState("");

  const [showUpload, setShowUpload] =
    useState(false);

  // DELETE MODAL
  const [
    showDeleteModal,
    setShowDeleteModal,
  ] = useState(false);

  const [
    candidateToDelete,
    setCandidateToDelete,
  ] = useState(null);

  // FETCH DATA
  const {
    data: candidates = [],
    isLoading,
  } = useCandidates(
    statusFilter
      ? { status: statusFilter }
      : {}
  );

  const { data: jobs = [] } =
    useJobs();

  const { mutate: deleteCandidate } =
    useDeleteCandidate();

  const {
    mutate: syncDrive,
    isPending: isSyncing,
  } = useDriveSync();

  // FILTER + SORT BY SCORE
  const filtered = candidates
    .filter((c) => {
      const q =
        search.toLowerCase();

      const matchesSearch =
        !q ||
        c.full_name
          ?.toLowerCase()
          .includes(q) ||
        c.email
          ?.toLowerCase()
          .includes(q) ||
        c.current_position
          ?.toLowerCase()
          .includes(q) ||
        (c.skills ?? []).some(
          (s) =>
            s
              .toLowerCase()
              .includes(q)
        );

      const matchesJob =
        !jobFilter ||
        c.job_id === jobFilter;

      return (
        matchesSearch &&
        matchesJob
      );
    })
    .sort(
      (a, b) =>
        (b.score || 0) -
        (a.score || 0)
    );

  // TOP 5
  const topCandidates =
    filtered.slice(0, 5);

  // DELETE
  const handleDelete = (
    e,
    candidate
  ) => {
    e.stopPropagation();

    setCandidateToDelete(
      candidate
    );

    setShowDeleteModal(true);
  };

  const confirmDelete = () => {
    if (candidateToDelete) {
      deleteCandidate(
        candidateToDelete.id
      );
    }

    setShowDeleteModal(false);

    setCandidateToDelete(null);
  };

  const closeDeleteModal = () => {
    setShowDeleteModal(false);

    setCandidateToDelete(null);
  };

  return (
    <div className="p-8">
      {/* HEADER */}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-5 mb-7">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <div className="p-2 rounded-xl bg-indigo-100">
              <Trophy
                size={18}
                className="text-indigo-600"
              />
            </div>

            <span className="text-sm font-medium text-indigo-600">
              Talent Pipeline
            </span>
          </div>

          <h1 className="text-4xl font-bold text-gray-900 tracking-tight">
            Candidats
          </h1>

          <p className="text-sm text-gray-500 mt-2">
            Top 5 candidats
            classés par score ATS
          </p>
        </div>

        {/* ACTIONS */}
        <div className="flex items-center gap-3">
          {/* SYNC */}
          <button
            onClick={() =>
              syncDrive()
            }
            disabled={isSyncing}
            className="
              group relative overflow-hidden
              flex items-center gap-2
              px-5 py-3
              rounded-2xl
              bg-linear-to-r
              from-indigo-600
              to-blue-600
              text-white
              text-sm font-semibold
              shadow-md hover:shadow-xl
              transition-all duration-300
              hover:-translate-y-0.5
              active:scale-[0.98]
            "
          >
            <div className="p-1 rounded-lg bg-white/15">
              <RefreshCw
                size={16}
                className={
                  isSyncing
                    ? "animate-spin"
                    : ""
                }
              />
            </div>

            <span>
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
              px-5 py-3
              rounded-2xl
              border border-gray-200
              bg-white
              text-gray-700
              text-sm font-semibold
              shadow-sm hover:shadow-lg
              hover:border-indigo-300
              hover:bg-indigo-50
              hover:text-indigo-700
              transition-all duration-300
              hover:-translate-y-0.5
            "
          >
            <div className="p-1 rounded-lg bg-gray-100 group-hover:bg-indigo-100 transition-colors">
              <Upload
                size={16}
              />
            </div>

            <span>
              Uploader un CV
            </span>
          </button>
        </div>
      </div>

      {/* FILTERS */}
      <div className="flex flex-wrap gap-3 mb-6">
        {/* SEARCH */}
        <div className="relative flex-1 min-w-65 max-w-md">
          <Search
            size={17}
            className="
              absolute left-4 top-1/2
              -translate-y-1/2
              text-gray-400
            "
          />

          <input
            type="text"
            placeholder="Nom, email, poste, compétence..."
            value={search}
            onChange={(e) =>
              setSearch(
                e.target.value
              )
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
              focus:ring-4
              focus:ring-indigo-100
              focus:border-indigo-400
            "
          />
        </div>

        {/* STATUS */}
        <select
          value={statusFilter}
          onChange={(e) =>
            setStatusFilter(
              e.target.value
            )
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
            focus:ring-4
            focus:ring-indigo-100
            focus:border-indigo-400
          "
        >
          {STATUS_OPTIONS.map(
            (option) => (
              <option
                key={option.value}
                value={
                  option.value
                }
              >
                {option.label}
              </option>
            )
          )}
        </select>

        {/* JOB */}
        <div className="relative">
          <Briefcase
            size={16}
            className="
              absolute left-4 top-1/2
              -translate-y-1/2
              text-gray-400
            "
          />

          <select
            value={jobFilter}
            onChange={(e) =>
              setJobFilter(
                e.target.value
              )
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
              focus:ring-4
              focus:ring-indigo-100
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

      {/* TABLE */}
      <div className="overflow-hidden rounded-3xl border border-gray-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              {[
                "RANK",
                "NOM",
                "POSTE ACTUEL",
                "COMPÉTENCES",
                "STATUT",
                "SCORE",
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
                  colSpan={7}
                  className="py-14 text-center text-gray-400"
                >
                  Chargement...
                </td>
              </tr>
            ) : topCandidates.length ===
              0 ? (
              <tr>
                <td
                  colSpan={7}
                  className="py-14 text-center text-gray-400"
                >
                  Aucun candidat
                </td>
              </tr>
            ) : (
              topCandidates.map(
                (c, index) => (
                  <tr
                    key={c.id}
                    onClick={() =>
                      navigate(
                        `/candidates/${c.id}`
                      )
                    }
                    className="
                      cursor-pointer
                      transition-all
                      hover:bg-indigo-50/40
                    "
                  >
                    {/* RANK */}
                    <td className="px-5 py-4">
                      <div
                        className="
                          w-8 h-8
                          rounded-full
                          bg-indigo-100
                          text-indigo-700
                          flex items-center justify-center
                          text-xs font-bold
                        "
                      >
                        #
                        {index + 1}
                      </div>
                    </td>

                    {/* NAME */}
                    <td className="px-5 py-4">
                      <div>
                        <p className="font-semibold text-gray-900">
                          {c.full_name ||
                            "—"}
                        </p>

                        <p className="text-xs text-gray-400 mt-1">
                          {c.email ||
                            "—"}
                        </p>
                      </div>
                    </td>

                    {/* POSITION */}
                    <td className="px-5 py-4 text-gray-600">
                      {c.current_position ||
                        "—"}
                    </td>

                    {/* SKILLS */}
                    <td className="px-5 py-4">
                      <div className="flex flex-wrap gap-2">
                        {(
                          c.skills ??
                          []
                        )
                          .slice(0, 3)
                          .map(
                            (
                              skill
                            ) => (
                              <span
                                key={
                                  skill
                                }
                                className="
                                  px-2.5 py-1
                                  rounded-lg
                                  bg-gray-100
                                  text-gray-600
                                  text-xs
                                  font-medium
                                "
                              >
                                {
                                  skill
                                }
                              </span>
                            )
                          )}

                        {(
                          c.skills ??
                          []
                        ).length >
                          3 && (
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
                            {c.skills
                              .length -
                              3}
                          </span>
                        )}
                      </div>
                    </td>

                    {/* STATUS */}
                    <td className="px-5 py-4">
                      <StatusBadge
                        status={
                          c.status
                        }
                      />
                    </td>

                    {/* SCORE */}
                    <td className="px-5 py-4">
                      <ScoreBadge
                        score={
                          c.score
                        }
                      />
                    </td>

                    {/* DELETE */}
                    <td className="px-5 py-4">
                      <button
                        onClick={(
                          e
                        ) =>
                          handleDelete(
                            e,
                            c
                          )
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
                        <Trash2
                          size={16}
                        />
                      </button>
                    </td>
                  </tr>
                )
              )
            )}
          </tbody>
        </table>
      </div>

      {/* DELETE MODAL */}
      {showDeleteModal && (
        <div
          className="
            fixed inset-0 z-50
            flex items-center justify-center
            bg-black/50 backdrop-blur-sm
            px-4
          "
          onClick={
            closeDeleteModal
          }
        >
          <div
            className="
              w-full max-w-md
              rounded-3xl
              bg-white
              p-6
              shadow-2xl
            "
            onClick={(e) =>
              e.stopPropagation()
            }
          >
            <div className="flex justify-center mb-5">
              <div
                className="
                  flex items-center justify-center
                  w-16 h-16
                  rounded-2xl
                  bg-red-100
                "
              >
                <AlertTriangle
                  size={30}
                  className="text-red-600"
                />
              </div>
            </div>

            <div className="text-center">
              <h2 className="text-2xl font-bold text-gray-900">
                Supprimer le candidat
              </h2>

              <p className="mt-3 text-sm text-gray-500">
                Êtes-vous sûr ?
              </p>
            </div>

            <div className="flex gap-3 mt-8">
              <button
                onClick={
                  closeDeleteModal
                }
                className="
                  flex-1 py-3
                  rounded-2xl
                  border border-gray-200
                  bg-white
                  text-gray-700
                "
              >
                Annuler
              </button>

              <button
                onClick={
                  confirmDelete
                }
                className="
                  flex-1 py-3
                  rounded-2xl
                  bg-red-600
                  text-white
                "
              >
                Supprimer
              </button>
            </div>
          </div>
        </div>
      )}

      {/* UPLOAD */}
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