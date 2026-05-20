import { useState } from "react";
import { X } from "lucide-react";
import { useTransitionStatus } from "../hooks/useCandidates";

const ALLOWED_TRANSITIONS = {
  applied:   ["screening", "rejected"],
  screening: ["interview", "rejected"],
  interview: ["offer",     "rejected"],
  offer:     ["hired",     "rejected"],
  hired:     [],
  rejected:  [],
};

const STATUS_LABELS = {
  screening: "Screening",
  interview: "Entretien",
  offer:     "Offre",
  hired:     "Embauché",
  rejected:  "Refusé",
};

export default function StatusTransitionModal({ candidate, onClose }) {
  const [selected, setSelected] = useState("");
  const [note, setNote] = useState("");
  const { mutate, isPending } = useTransitionStatus();

  const options = ALLOWED_TRANSITIONS[candidate.status] ?? [];

  const handleSubmit = () => {
    if (!selected) return;
    mutate(
      { id: candidate.id, new_status: selected, note },
      { onSuccess: onClose }
    );
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="card w-full max-w-md p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Changer le statut</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X size={20} />
          </button>
        </div>

        <p className="text-sm text-gray-500 mb-4">
          Candidat : <span className="font-medium text-gray-900">{candidate.full_name}</span>
        </p>

        {options.length === 0 ? (
          <p className="text-sm text-gray-500">Aucune transition possible depuis cet état.</p>
        ) : (
          <>
            <div className="space-y-2 mb-4">
              {options.map((status) => (
                <label
                  key={status}
                  className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                    selected === status
                      ? "border-primary-500 bg-primary-50"
                      : "border-gray-200 hover:bg-gray-50"
                  }`}
                >
                  <input
                    type="radio"
                    name="status"
                    value={status}
                    checked={selected === status}
                    onChange={() => setSelected(status)}
                    className="accent-primary-600"
                  />
                  <span className="text-sm font-medium">{STATUS_LABELS[status]}</span>
                </label>
              ))}
            </div>

            <textarea
              className="input resize-none mb-4"
              rows={2}
              placeholder="Note (optionnel)"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />

            <div className="flex gap-3 justify-end">
              <button className="btn-secondary" onClick={onClose}>Annuler</button>
              <button
                className="btn-primary"
                onClick={handleSubmit}
                disabled={!selected || isPending}
              >
                {isPending ? "En cours..." : "Confirmer"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}