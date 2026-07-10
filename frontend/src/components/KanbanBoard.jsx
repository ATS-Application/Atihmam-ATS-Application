// frontend/src/components/KanbanBoard.jsx

import { useNavigate } from "react-router-dom";
import { ChevronRight } from "lucide-react";

import StatusBadge from "./StatusBadge";
import ScoreBadge from "./ScoreBadge";

const COLUMNS = [
  { key: "applied",    label: "Candidatures" },
  { key: "screening",  label: "Screening"    },
  { key: "interview",  label: "Entretiens"   },
  { key: "offer",      label: "Offres"       },
  { key: "hired",      label: "Embauchés"    },
];

export default function KanbanBoard({ candidates = [], filterJobId = null }) {
  const navigate = useNavigate();

  const visible = filterJobId
    ? candidates.filter((c) => {
        const isLegacyMatch = c.job_id === filterJobId;
        const aiData = c.ai_extracted_data || {};
        const jobScores = aiData.job_scores || {};
        const hasJobScore = Object.keys(jobScores).includes(filterJobId);
        return isLegacyMatch || hasJobScore;
      })
    : candidates;

  const byStatus = (status) => visible.filter((c) => c.status === status);
  const rejected = byStatus("rejected");

  const columns = rejected.length > 0
    ? [...COLUMNS, { key: "rejected", label: "Refusés" }]
    : COLUMNS;

  return (
    <div className="flex gap-px bg-gray-200 overflow-x-auto">
      {columns.map(({ key, label }) => {
        const cards = byStatus(key);

        return (
          <div key={key} className="w-72 shrink-0 bg-gray-50 flex flex-col">
            {/* Column header */}
            <div className="flex items-center justify-between px-4 py-3 bg-white border-b border-gray-200">
              <span className="text-xs font-semibold text-gray-600 uppercase tracking-wide">{label}</span>
              <span className="text-xs font-semibold text-gray-400 tabular-nums">{cards.length}</span>
            </div>

            {/* Cards */}
            <div className="flex-1 p-3 space-y-2">
              {cards.map((candidate) => {
                const initials = (candidate.full_name ?? "?")
                  .split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();

                return (
                  <button
                    key={candidate.id}
                    onClick={() => navigate(`/candidates/${candidate.id}`)}
                    className="w-full text-left group bg-white border border-gray-200 rounded-lg p-3.5 hover:border-gray-400 hover:shadow-sm transition-all"
                  >
                    {/* Name row */}
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div className="w-8 h-8 rounded-full bg-gray-100 border border-gray-200 flex items-center justify-center text-xs font-semibold text-gray-600 shrink-0">
                          {initials}
                        </div>
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-gray-900 truncate leading-tight">
                            {candidate.full_name || "Sans nom"}
                          </p>
                          <p className="text-xs text-gray-400 truncate mt-0.5">
                            {candidate.current_position || "—"}
                          </p>
                        </div>
                      </div>
                      <ChevronRight
                        size={14}
                        className="text-gray-200 group-hover:text-gray-500 transition-colors shrink-0 mt-1"
                      />
                    </div>

                    {/* Domain tag */}
                    {candidate.domain && (
                      <div className="mt-3">
                        <span className="text-xs text-gray-500 border border-gray-200 rounded px-2 py-0.5">
                          {candidate.domain}
                        </span>
                      </div>
                    )}

                    {/* Footer */}
                    <div className="flex items-center justify-between mt-3 pt-3 border-t border-gray-100">
                      <StatusBadge status={candidate.status} />
                      <ScoreBadge score={candidate.score} />
                    </div>
                  </button>
                );
              })}

              {cards.length === 0 && (
                <div className="border border-dashed border-gray-200 rounded-lg py-8 text-center">
                  <p className="text-xs text-gray-300">Aucun candidat</p>
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
