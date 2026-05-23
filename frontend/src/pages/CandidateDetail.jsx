import { useState, useMemo, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  ExternalLink,
  GitBranch,
  Mail,
  Phone,
  Briefcase,
} from "lucide-react";

import { createClient } from "@supabase/supabase-js";

import { useCandidateWithPolling } from "../hooks/useCandidates";
import { useJobs } from "../hooks/useJobs";

import StatusBadge from "../components/StatusBadge";
import ScoreBadge from "../components/ScoreBadge";
import StatusTransitionModal from "../components/StatusTransitionModal";

// ======================================================
// SUPABASE
// ======================================================

const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY
);

// ======================================================
// REUSABLE COMPONENTS
// ======================================================

function InfoRow({ icon: Icon, label, value }) {
  if (value == null || value === "") return null;

  return (
    <div className="flex items-start gap-3">
      {Icon && (
        <div className="mt-0.5 text-gray-400">
          <Icon size={16} />
        </div>
      )}

      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
          {label}
        </p>

        <p className="mt-0.5 wrap-break-word text-sm text-gray-900">
          {value}
        </p>
      </div>
    </div>
  );
}

function CandidateAvatar({ name }) {
  const initials = useMemo(() => {
    if (!name) return "?";

    return name
      .split(" ")
      .map((part) => part[0])
      .join("")
      .slice(0, 2)
      .toUpperCase();
  }, [name]);

  return (
    <div
      className="
        flex h-16 w-16 items-center justify-center
        rounded-2xl
        bg-indigo-100
        text-xl font-bold text-indigo-700
      "
    >
      {initials}
    </div>
  );
}

function KeywordBadge({ keyword }) {
  return (
    <span
      className="
        rounded-xl
        bg-green-100
        px-3 py-1.5
        text-xs font-medium text-green-700
      "
    >
      {keyword}
    </span>
  );
}

// ======================================================
// MAIN COMPONENT
// ======================================================

export default function CandidateDetail() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [showTransition, setShowTransition] = useState(false);
  const [isOpeningCV, setIsOpeningCV] = useState(false);

  // ======================================================
  // DATA
  // ======================================================

  const { data: candidate, isLoading } = useCandidateWithPolling(id, {
    pollUntilScored: true,
  });

  const { data: jobs = [] } = useJobs();

  // ======================================================
  // MEMOIZED VALUES
  // ======================================================

  const linkedJob = useMemo(() => {
    if (!candidate?.job_id) return null;

    return jobs.find((job) => job.id === candidate.job_id);
  }, [jobs, candidate]);

  const rawWithoutSummary = useMemo(() => {
    if (!candidate?.ai_extracted_data) return null;

    const { summary, ...rest } = candidate.ai_extracted_data;

    return rest;
  }, [candidate]);

  // ======================================================
  // ACTIONS
  // ======================================================

  const openCV = useCallback(async () => {
    if (!candidate?.cv_file_url) return;

    try {
      setIsOpeningCV(true);

      const { data, error } = await supabase.storage
        .from("cvs")
        .createSignedUrl(candidate.cv_file_url, 60);

      if (error) {
        console.error("CV access error:", error);
        alert("Impossible d'ouvrir le CV.");
        return;
      }

      if (data?.signedUrl) {
        window.open(
          data.signedUrl,
          "_blank",
          "noopener,noreferrer"
        );
      }
    } catch (error) {
      console.error("Unexpected CV error:", error);
      alert("Une erreur est survenue.");
    } finally {
      setIsOpeningCV(false);
    }
  }, [candidate]);

  // ======================================================
  // LOADING
  // ======================================================

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center p-10">
        <p className="animate-pulse text-sm text-gray-400">
          Chargement du candidat...
        </p>
      </div>
    );
  }

  // ======================================================
  // NOT FOUND
  // ======================================================

  if (!candidate) {
    return (
      <div className="flex h-full items-center justify-center p-10">
        <p className="text-sm text-gray-400">
          Candidat introuvable
        </p>
      </div>
    );
  }

  // ======================================================
  // UI
  // ======================================================

  return (
    <div className="mx-auto max-w-6xl p-6 lg:p-8">
      {/* BACK BUTTON */}
      <button
        onClick={() => navigate(-1)}
        className="
          mb-6
          flex items-center gap-2
          text-sm text-gray-500
          transition-colors
          hover:text-gray-900
        "
      >
        <ArrowLeft size={16} />
        Retour
      </button>

      {/* ======================================================
          HEADER
      ====================================================== */}

      <div
        className="
          mb-6
          rounded-3xl
          border border-gray-200
          bg-white
          p-6
          shadow-sm
        "
      >
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          {/* LEFT */}
          <div className="flex items-start gap-4">
            <CandidateAvatar name={candidate.full_name} />

            <div>
              <h1 className="text-2xl font-bold text-gray-900">
                {candidate.full_name || "Candidat sans nom"}
              </h1>

              <p className="mt-1 text-gray-500">
                {candidate.current_position ||
                  "Poste non renseigné"}
              </p>

              {linkedJob && (
                <div
                  className="
                    mt-3
                    inline-flex items-center
                    rounded-full
                    bg-indigo-50
                    px-3 py-1
                    text-xs font-semibold text-indigo-700
                  "
                >
                  Poste ciblé : {linkedJob.title}
                </div>
              )}
            </div>
          </div>

          {/* RIGHT */}
          <div className="flex flex-wrap items-center gap-3">
            {candidate.score == null && (
              <span className="animate-pulse text-xs text-gray-400">
                AI scoring...
              </span>
            )}

            <ScoreBadge score={candidate.score} />

            <StatusBadge status={candidate.status} />

            <button
              onClick={() => setShowTransition(true)}
              className="
                flex items-center gap-2
                rounded-full
                border border-gray-200
                bg-white
                px-4 py-2
                text-xs font-medium text-gray-700
                transition-all
                hover:border-indigo-300
                hover:bg-indigo-50
                hover:text-indigo-700
              "
            >
              <GitBranch size={15} />
              Changer statut
            </button>
          </div>
        </div>
      </div>

      {/* ======================================================
          CONTENT GRID
      ====================================================== */}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* ======================================================
            LEFT PANEL
        ====================================================== */}

        <div className="space-y-6">
          {/* INFORMATIONS */}
          <div
            className="
              rounded-3xl
              border border-gray-200
              bg-white
              p-5
              shadow-sm
            "
          >
            <h2 className="mb-5 text-sm font-semibold text-gray-900">
              Informations
            </h2>

            <div className="space-y-5">
              <InfoRow
                icon={Mail}
                label="Email"
                value={candidate.email}
              />

              <InfoRow
                icon={Phone}
                label="Téléphone"
                value={candidate.phone}
              />

              <InfoRow
                icon={Briefcase}
                label="Expérience"
                value={
                  candidate.experience_years != null
                    ? `${candidate.experience_years} an${
                        candidate.experience_years > 1
                          ? "s"
                          : ""
                      }`
                    : null
                }
              />

              {linkedJob && (
                <InfoRow
                  icon={Briefcase}
                  label="Poste ciblé"
                  value={linkedJob.title}
                />
              )}
            </div>

            {/* CV BUTTON */}
            {candidate.cv_file_url && (
              <button
                onClick={openCV}
                disabled={isOpeningCV}
                className="
                  mt-6
                  flex w-full items-center justify-center gap-2
                  rounded-2xl
                  border border-gray-200
                  bg-white
                  px-4 py-3
                  text-sm font-medium text-gray-700
                  transition-all
                  hover:border-indigo-300
                  hover:bg-indigo-50
                  hover:text-indigo-700
                  disabled:cursor-not-allowed
                  disabled:opacity-50
                "
              >
                <ExternalLink size={16} />

                {isOpeningCV
                  ? "Ouverture..."
                  : "Voir le CV"}
              </button>
            )}
          </div>

          {/* MATCHED KEYWORDS */}
          {candidate.matched_keywords?.length > 0 && (
            <div
              className="
                rounded-3xl
                border border-gray-200
                bg-white
                p-5
                shadow-sm
              "
            >
              <h2 className="mb-4 text-sm font-semibold text-gray-900">
                Matched Keywords
              </h2>

              <div className="flex flex-wrap gap-2">
                {candidate.matched_keywords.map((keyword) => (
                  <KeywordBadge
                    key={keyword}
                    keyword={keyword}
                  />
                ))}
              </div>
            </div>
          )}
        </div>

        {/* ======================================================
            RIGHT PANEL
        ====================================================== */}

        <div className="space-y-6 lg:col-span-2">
          {/* AI SUMMARY */}
          {candidate.ai_extracted_data?.summary && (
            <div
              className="
                rounded-3xl
                border border-gray-200
                bg-white
                p-6
                shadow-sm
              "
            >
              <h2 className="mb-3 text-sm font-semibold text-gray-900">
                Résumé IA
              </h2>

              <p
                className="
                  whitespace-pre-line
                  text-sm leading-relaxed text-gray-600
                "
              >
                {candidate.ai_extracted_data.summary}
              </p>
            </div>
          )}

          {/* RAW AI DATA */}
          <div
            className="
              rounded-3xl
              border border-gray-200
              bg-white
              p-6
              shadow-sm
            "
          >
            <h2 className="mb-4 text-sm font-semibold text-gray-900">
              Données extraites par l'IA
            </h2>

            {rawWithoutSummary &&
            Object.keys(rawWithoutSummary).length > 0 ? (
              <pre
                className="
                  max-h-125
                  overflow-auto
                  rounded-2xl
                  border border-gray-100
                  bg-gray-50
                  p-4
                  text-xs text-gray-700
                "
              >
                {JSON.stringify(
                  rawWithoutSummary,
                  null,
                  2
                )}
              </pre>
            ) : (
              <p className="text-sm text-gray-400">
                Aucune donnée structurée disponible.
              </p>
            )}
          </div>
        </div>
      </div>

      {/* ======================================================
          STATUS MODAL
      ====================================================== */}

      {showTransition && (
        <StatusTransitionModal
          candidate={candidate}
          onClose={() => setShowTransition(false)}
        />
      )}
    </div>
  );
}