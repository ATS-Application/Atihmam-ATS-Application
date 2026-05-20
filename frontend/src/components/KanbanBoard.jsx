import { useNavigate } from "react-router-dom";
import StatusBadge from "./StatusBadge";
import ScoreBadge from "./ScoreBadge";

const COLUMNS = [
  { key: "applied",   label: "Candidatures" },
  { key: "screening", label: "Screening" },
  { key: "interview", label: "Entretiens" },
  { key: "offer",     label: "Offres" },
  { key: "hired",     label: "Embauchés" },
];

export default function KanbanBoard({ candidates }) {
  const navigate = useNavigate();

  const byStatus = (status) =>
    candidates.filter((c) => c.status === status);

  return (
    <div className="flex gap-4 overflow-x-auto pb-4">
      {COLUMNS.map(({ key, label }) => {
        const cards = byStatus(key);
        return (
          <div key={key} className="flex-shrink-0 w-64">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gray-700">{label}</h3>
              <span className="badge bg-gray-100 text-gray-600">{cards.length}</span>
            </div>
            <div className="space-y-2">
              {cards.map((c) => (
                <div
                  key={c.id}
                  onClick={() => navigate(`/candidates/${c.id}`)}
                  className="card p-3 cursor-pointer hover:shadow-md transition-shadow"
                >
                  <p className="text-sm font-medium text-gray-900 truncate">
                    {c.full_name || "Sans nom"}
                  </p>
                  <p className="text-xs text-gray-500 truncate mt-0.5">
                    {c.current_position || "—"}
                  </p>
                  <div className="flex items-center justify-between mt-2">
                    <StatusBadge status={c.status} />
                    <ScoreBadge score={c.score} />
                  </div>
                </div>
              ))}
              {cards.length === 0 && (
                <div className="border-2 border-dashed border-gray-200 rounded-lg p-4 text-center">
                  <p className="text-xs text-gray-400">Aucun candidat</p>
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}