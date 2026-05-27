// frontend/src/pages/CandidateList.jsx

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search, Upload, RefreshCw, Trash2, ChevronDown } from "lucide-react";

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
  { value: "",           label: "Tous les statuts" },
  { value: "applied",    label: "Candidature"      },
  { value: "screening",  label: "Screening"        },
  { value: "interview",  label: "Entretien"        },
  { value: "offer",      label: "Offre"            },
  { value: "hired",      label: "Embauché"         },
  { value: "rejected",   label: "Refusé"           },
];

export default function CandidateList() {
  const navigate = useNavigate();

  const [search,          setSearch]          = useState("");
  const [statusFilter,    setStatusFilter]    = useState("");
  const [jobFilter,       setJobFilter]       = useState("");
  const [showUpload,      setShowUpload]      = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [candidateToDelete, setCandidateToDelete] = useState(null);

  const { data: candidates = [], isLoading }        = useCandidates(statusFilter ? { status: statusFilter } : {});
  const { data: jobs = [] }                         = useJobs();
  const { mutate: deleteCandidate }                 = useDeleteCandidate();
  const { mutate: syncDrive, isPending: isSyncing } = useDriveSync();

  const filtered = candidates
    .filter((c) => {
      const q = search.toLowerCase();
      const matchesSearch =
        !q ||
        c.full_name?.toLowerCase().includes(q) ||
        c.email?.toLowerCase().includes(q) ||
        c.current_position?.toLowerCase().includes(q) ||
        (c.skills ?? []).some((s) => s.toLowerCase().includes(q));
      const matchesJob = !jobFilter || c.job_id === jobFilter;
      return matchesSearch && matchesJob;
    })
    .sort((a, b) => (b.score ?? -1) - (a.score ?? -1));

  const top5Ids = new Set(
    [...candidates]
      .filter((c) => c.score != null)
      .sort((a, b) => b.score - a.score)
      .slice(0, 5)
      .map((c) => c.id)
  );

  const handleDelete = (e, candidate) => {
    e.stopPropagation();
    setCandidateToDelete(candidate);
    setShowDeleteModal(true);
  };

  const confirmDelete = () => {
    if (candidateToDelete) deleteCandidate(candidateToDelete.id);
    setShowDeleteModal(false);
    setCandidateToDelete(null);
  };

  const closeDeleteModal = () => {
    setShowDeleteModal(false);
    setCandidateToDelete(null);
  };

  const hasFilters = search || statusFilter || jobFilter;

  return (
    <div className="p-6 lg:p-8 bg-gray-50 min-h-screen">

      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4 mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Candidats</h1>
          <p className="text-sm text-gray-400 mt-0.5">
            {filtered.length} candidat{filtered.length !== 1 ? "s" : ""}
            {hasFilters ? " filtrés" : " au total"}
            {hasFilters && filtered.length !== candidates.length && (
              <span className="ml-1">sur {candidates.length}</span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => syncDrive()}
            disabled={isSyncing}
            className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 hover:border-gray-300 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <RefreshCw size={12} className={isSyncing ? "animate-spin" : ""} />
            {isSyncing ? "Sync…" : "Sync Drive"}
          </button>
          <button
            onClick={() => setShowUpload(true)}
            className="flex items-center gap-2 rounded-lg bg-gray-900 hover:bg-gray-700 px-3 py-1.5 text-xs font-medium text-white transition-colors"
          >
            <Upload size={12} />
            Uploader un CV
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 mb-5">
        <div className="relative flex-1 min-w-56 max-w-sm">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Nom, email, poste, compétence…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full h-9 pl-9 pr-3 rounded-lg border border-gray-200 bg-white text-xs text-gray-900 outline-none focus:border-gray-400 focus:ring-2 focus:ring-gray-100 placeholder:text-gray-300 transition-colors"
          />
        </div>

        <div className="relative">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="h-9 pl-3 pr-8 rounded-lg border border-gray-200 bg-white text-xs text-gray-700 outline-none focus:border-gray-400 appearance-none cursor-pointer"
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <ChevronDown size={11} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
        </div>

        <div className="relative">
          <select
            value={jobFilter}
            onChange={(e) => setJobFilter(e.target.value)}
            className="h-9 pl-3 pr-8 rounded-lg border border-gray-200 bg-white text-xs text-gray-700 outline-none focus:border-gray-400 appearance-none cursor-pointer"
          >
            <option value="">Tous les postes</option>
            {jobs.map((job) => (
              <option key={job.id} value={job.id}>{job.title}</option>
            ))}
          </select>
          <ChevronDown size={11} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
        </div>

        {hasFilters && (
          <button
            onClick={() => { setSearch(""); setStatusFilter(""); setJobFilter(""); }}
            className="h-9 px-3 rounded-lg border border-gray-200 bg-white text-xs text-gray-400 hover:text-gray-700 hover:border-gray-300 transition-colors"
          >
            Effacer
          </button>
        )}
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100">
              {["#", "Nom", "Poste actuel", "Compétences", "Statut", "Score", ""].map((h) => (
                <th
                  key={h}
                  className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-widest"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>

          <tbody className="divide-y divide-gray-50">
            {isLoading ? (
              <tr>
                <td colSpan={7} className="py-16 text-center text-sm text-gray-400">
                  Chargement…
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-16 text-center">
                  <p className="text-sm text-gray-400">Aucun candidat trouvé</p>
                  {hasFilters && (
                    <button
                      onClick={() => { setSearch(""); setStatusFilter(""); setJobFilter(""); }}
                      className="mt-2 text-xs text-gray-400 underline underline-offset-2 hover:text-gray-700"
                    >
                      Effacer les filtres
                    </button>
                  )}
                </td>
              </tr>
            ) : (
              filtered.map((c, index) => {
                const isTop5    = top5Ids.has(c.id);
                const linkedJob = jobs.find((j) => j.id === c.job_id);

                return (
                  <tr
                    key={c.id}
                    onClick={() => navigate(`/candidates/${c.id}`)}
                    className={`cursor-pointer transition-colors hover:bg-gray-50 ${
                      isTop5 ? "bg-gray-50/60" : ""
                    }`}
                  >
                    {/* Rank */}
                    <td className="px-4 py-3">
                      <span className={`text-xs font-semibold tabular-nums ${
                        isTop5 ? "text-gray-900" : "text-gray-300"
                      }`}>
                        {index + 1}
                      </span>
                    </td>

                    {/* Name */}
                    <td className="px-4 py-3">
                      <p className="text-sm font-medium text-gray-900">{c.full_name || "—"}</p>
                      <p className="text-xs text-gray-400 mt-0.5">{c.email || "—"}</p>
                    </td>

                    {/* Position */}
                    <td className="px-4 py-3">
                      <p className="text-sm text-gray-700">{c.current_position || "—"}</p>
                      {linkedJob && (
                        <p className="text-xs text-gray-400 mt-0.5">{linkedJob.title}</p>
                      )}
                    </td>

                    {/* Skills */}
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {(c.skills ?? []).slice(0, 3).map((skill) => (
                          <span
                            key={skill}
                            className="px-2 py-0.5 rounded border border-gray-200 text-gray-500 text-xs bg-gray-50"
                          >
                            {skill}
                          </span>
                        ))}
                        {(c.skills ?? []).length > 3 && (
                          <span className="px-2 py-0.5 rounded border border-gray-200 text-gray-400 text-xs">
                            +{c.skills.length - 3}
                          </span>
                        )}
                        {(c.skills ?? []).length === 0 && (
                          <span className="text-xs text-gray-300">—</span>
                        )}
                      </div>
                    </td>

                    {/* Status */}
                    <td className="px-4 py-3">
                      <StatusBadge status={c.status} />
                    </td>

                    {/* Score */}
                    <td className="px-4 py-3">
                      <ScoreBadge score={c.score} />
                    </td>

                    {/* Delete */}
                    <td className="px-4 py-3">
                      <button
                        onClick={(e) => handleDelete(e, c)}
                        className="p-1.5 rounded text-gray-300 hover:text-red-500 hover:bg-red-50 transition-colors"
                      >
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>

        {/* Footer */}
        {!isLoading && filtered.length > 0 && (
          <div className="px-4 py-2.5 border-t border-gray-100 flex items-center justify-between">
            <span className="text-xs text-gray-400 tabular-nums">
              {filtered.length} candidat{filtered.length !== 1 ? "s" : ""}
            </span>
            <span className="text-xs text-gray-400 tabular-nums">
              {top5Ids.size} top candidat{top5Ids.size !== 1 ? "s" : ""}
            </span>
          </div>
        )}
      </div>

      {/* Delete modal */}
      {showDeleteModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
          onClick={closeDeleteModal}
        >
          <div
            className="w-full max-w-sm bg-white rounded-xl border border-gray-200 p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-sm font-semibold text-gray-900 mb-1">Supprimer le candidat</h2>
            <p className="text-xs text-gray-500 mb-6">
              <span className="font-medium text-gray-700">{candidateToDelete?.full_name}</span>
              {" "}sera définitivement supprimé. Cette action est irréversible.
            </p>
            <div className="flex gap-2">
              <button
                onClick={closeDeleteModal}
                className="flex-1 h-9 rounded-lg border border-gray-200 bg-white text-xs font-medium text-gray-600 hover:bg-gray-50 transition-colors"
              >
                Annuler
              </button>
              <button
                onClick={confirmDelete}
                className="flex-1 h-9 rounded-lg bg-red-600 hover:bg-red-700 text-white text-xs font-medium transition-colors"
              >
                Supprimer
              </button>
            </div>
          </div>
        </div>
      )}

      {showUpload && <UploadCVModal onClose={() => setShowUpload(false)} />}
    </div>
  );
}