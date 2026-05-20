import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, ExternalLink, GitBranch } from "lucide-react";
import { useCandidate } from "../hooks/useCandidates";
import StatusBadge from "../components/StatusBadge";
import ScoreBadge from "../components/ScoreBadge";
import StatusTransitionModal from "../components/StatusTransitionModal";

function InfoRow({ label, value }) {
  if (!value) return null;
  return (
    <div>
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
      <p className="text-sm text-gray-900 mt-0.5">{value}</p>
    </div>
  );
}

export default function CandidateDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { data: candidate, isLoading } = useCandidate(id);
  const [showTransition, setShowTransition] = useState(false);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-gray-400">Chargement...</p>
      </div>
    );
  }

  if (!candidate) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-gray-400">Candidat introuvable</p>
      </div>
    );
  }

  return (
    <div className="p-8 max-w-4xl">
      {/* Header */}
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-800 mb-6 transition-colors"
      >
        <ArrowLeft size={16} />
        Retour
      </button>

      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            {candidate.full_name || "Candidat sans nom"}
          </h1>
          <p className="text-gray-500 mt-1">{candidate.current_position || "—"}</p>
        </div>
        <div className="flex items-center gap-3">
          <ScoreBadge score={candidate.score} />
          <StatusBadge status={candidate.status} />
          <button
            className="btn-secondary"
            onClick={() => setShowTransition(true)}
          >
            <GitBranch size={15} />
            Changer statut
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left — Info */}
        <div className="lg:col-span-1 space-y-4">
          <div className="card p-5 space-y-4">
            <h2 className="text-sm font-semibold text-gray-900">Informations</h2>
            <InfoRow label="Email"       value={candidate.email} />
            <InfoRow label="Téléphone"   value={candidate.phone} />
            <InfoRow label="Expérience"  value={candidate.experience_years != null ? `${candidate.experience_years} ans` : null} />

            {candidate.cv_file_url && (
              <a
                href={candidate.cv_file_url}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-secondary w-full justify-center mt-2"
              >
                <ExternalLink size={15} />
                Voir le CV
              </a>
            )}
          </div>

          {/* Skills */}
          {candidate.skills?.length > 0 && (
            <div className="card p-5">
              <h2 className="text-sm font-semibold text-gray-900 mb-3">Compétences</h2>
              <div className="flex flex-wrap gap-1.5">
                {candidate.skills.map((s) => (
                  <span key={s} className="badge bg-blue-50 text-blue-700">{s}</span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right — AI data */}
        <div className="lg:col-span-2 space-y-4">
          {candidate.ai_extracted_data?.summary && (
            <div className="card p-5">
              <h2 className="text-sm font-semibold text-gray-900 mb-2">Résumé IA</h2>
              <p className="text-sm text-gray-600 leading-relaxed">
                {candidate.ai_extracted_data.summary}
              </p>
            </div>
          )}

          <div className="card p-5">
            <h2 className="text-sm font-semibold text-gray-900 mb-3">Données extraites par l'IA</h2>
            {candidate.ai_extracted_data ? (
              <pre className="text-xs text-gray-600 bg-gray-50 rounded-lg p-4 overflow-auto max-h-80">
                {JSON.stringify(candidate.ai_extracted_data, null, 2)}
              </pre>
            ) : (
              <p className="text-sm text-gray-400">Traitement IA en cours ou non effectué.</p>
            )}
          </div>
        </div>
      </div>

      {showTransition && (
        <StatusTransitionModal
          candidate={candidate}
          onClose={() => setShowTransition(false)}
        />
      )}
    </div>
  );
}