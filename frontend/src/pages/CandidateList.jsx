import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search, Upload, RefreshCw, Trash2 } from "lucide-react";
import { useCandidates, useDeleteCandidate, useDriveSync } from "../hooks/useCandidates";
import StatusBadge from "../components/StatusBadge";
import ScoreBadge from "../components/ScoreBadge";
import UploadCVModal from "../components/UploadCVModal";

const STATUS_OPTIONS = [
  { value: "", label: "Tous les statuts" },
  { value: "applied",   label: "Candidature" },
  { value: "screening", label: "Screening" },
  { value: "interview", label: "Entretien" },
  { value: "offer",     label: "Offre" },
  { value: "hired",     label: "Embauché" },
  { value: "rejected",  label: "Refusé" },
];

export default function CandidateList() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [showUpload, setShowUpload] = useState(false);

  const { data: candidates = [], isLoading } = useCandidates(
    statusFilter ? { status: statusFilter } : {}
  );
  const { mutate: deleteCandidate } = useDeleteCandidate();
  const { mutate: syncDrive, isPending: isSyncing } = useDriveSync();

  const filtered = candidates.filter((c) => {
    const q = search.toLowerCase();
    return (
      !q ||
      c.full_name?.toLowerCase().includes(q) ||
      c.email?.toLowerCase().includes(q) ||
      c.current_position?.toLowerCase().includes(q)
    );
  });

  const handleDelete = (e, id) => {
    e.stopPropagation();
    if (confirm("Supprimer ce candidat ?")) deleteCandidate(id);
  };

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Candidats</h1>
          <p className="text-gray-500 text-sm mt-1">{candidates.length} candidat(s)</p>
        </div>
        <div className="flex gap-2">
          <button
            className="btn-secondary"
            onClick={() => syncDrive()}
            disabled={isSyncing}
          >
            <RefreshCw size={16} className={isSyncing ? "animate-spin" : ""} />
            {isSyncing ? "Sync..." : "Sync Drive"}
          </button>
          <button className="btn-primary" onClick={() => setShowUpload(true)}>
            <Upload size={16} />
            Uploader un CV
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3 mb-5">
        <div className="relative flex-1 max-w-sm">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            className="input pl-9"
            placeholder="Rechercher..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <select
          className="input w-48"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      {/* Table */}
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              {["Nom", "Poste actuel", "Compétences", "Statut", "Score", ""].map((h) => (
                <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {isLoading ? (
              <tr>
                <td colSpan={6} className="text-center py-12 text-gray-400">
                  Chargement...
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="text-center py-12 text-gray-400">
                  Aucun candidat trouvé
                </td>
              </tr>
            ) : (
              filtered.map((c) => (
                <tr
                  key={c.id}
                  onClick={() => navigate(`/candidates/${c.id}`)}
                  className="hover:bg-gray-50 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-3">
                    <p className="font-medium text-gray-900">{c.full_name || "—"}</p>
                    <p className="text-xs text-gray-400">{c.email || "—"}</p>
                  </td>
                  <td className="px-4 py-3 text-gray-600">{c.current_position || "—"}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {(c.skills ?? []).slice(0, 3).map((s) => (
                        <span key={s} className="badge bg-gray-100 text-gray-600">{s}</span>
                      ))}
                      {(c.skills ?? []).length > 3 && (
                        <span className="badge bg-gray-100 text-gray-500">
                          +{c.skills.length - 3}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3"><StatusBadge status={c.status} /></td>
                  <td className="px-4 py-3"><ScoreBadge score={c.score} /></td>
                  <td className="px-4 py-3">
                    <button
                      onClick={(e) => handleDelete(e, c.id)}
                      className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded transition-colors"
                    >
                      <Trash2 size={15} />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {showUpload && <UploadCVModal onClose={() => setShowUpload(false)} />}
    </div>
  );
}