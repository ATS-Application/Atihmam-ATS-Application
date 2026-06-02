// frontend/src/components/UploadCVModal.jsx

import { useState, useRef } from "react";
import {
  X,
  Upload,
  FileText,
  Briefcase,
  Sparkles,
  CheckCircle2,
} from "lucide-react";

import toast from "react-hot-toast";

import { useUploadCV } from "../hooks/useCandidates";
import { useJobs } from "../hooks/useJobs";

export default function UploadCVModal({ onClose }) {
  const [file, setFile] = useState(null);
  const [jobId, setJobId] = useState("");
  const [isDragging, setIsDragging] = useState(false);

  const fileRef = useRef();

  const { mutate, isPending } = useUploadCV();
  const { data: jobs = [] } = useJobs();

  function handleDrop(e) {
    e.preventDefault();
    setIsDragging(false);

    const dropped = e.dataTransfer.files?.[0];

    if (dropped?.type === "application/pdf") {
      setFile(dropped);
    }
  }

  function handleFileSelect(e) {
    const selected = e.target.files?.[0];

    if (selected?.type === "application/pdf") {
      setFile(selected);
    }
  }

  function handleSubmit() {
    if (!file) return;

    mutate(
      {
        file,
        job_id: jobId || undefined,
      },
      {
        onSuccess: () => {
          toast.success("CV uploaded successfully");
          onClose();
        },

        onError: (error) => {
          if (error?.response?.status === 409) {
            toast.error(
              error.response?.data?.detail ||
                "This CV has already been processed."
            );
            return;
          }

          toast.error("Failed to upload CV.");
        },
      }
    );
  }


  return (
    <div
      className="
        fixed inset-0 z-50
        flex items-center justify-center
        bg-black/50
        backdrop-blur-sm
        p-4
      "
    >
      {/* Modal */}
      <div
        className="
          relative
          w-full max-w-lg h-150
          overflow-hidden
          rounded-3xl
          border border-white/20
          bg-white
          shadow-2xl
        "
      >
        {/* Glow */}
        <div className="absolute -top-20 -right-20 w-56 h-56 bg-indigo-500/10 rounded-full blur-3xl" />

        {/* Header */}
        <div className="relative flex items-start justify-between p-6 border-b border-gray-100">
          <div className="flex items-start gap-4">
            <div className="p-3 rounded-2xl bg-amber-100">
              <Sparkles
                size={20}
                className="text-orange-600"
              />
            </div>

            <div>
              <h2 className="text-xl font-bold text-gray-900">
                Uploader un CV
              </h2>

              <p className="text-sm text-gray-500 mt-1">
                Importez un CV PDF et
                associez-le à un poste
              </p>
            </div>
          </div>

          {/* Close */}
          <button
            onClick={onClose}
            className="
              p-2 rounded-xl
              text-gray-400
              hover:text-gray-700
              hover:bg-gray-100
              transition-colors
            "
          >
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <div className="relative p-6">
          {/* Upload Area */}
          <div
            onClick={() =>
              fileRef.current?.click()
            }
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() =>
              setIsDragging(false)
            }
            onDrop={handleDrop}
            className={`
              group
              relative
              overflow-hidden
              rounded-3xl
              border-2 border-dashed
              p-10
              text-center
              cursor-pointer
              transition-all duration-300

              ${
                isDragging
                  ? `
                    border-orange-500
                    bg-orange-50
                    scale-[1.01]
                  `
                  : `
                    border-gray-300
                    hover:border-orange-400
                    hover:bg-orange-50/50
                  `
              }
            `}
          >
            {/* Hidden Input */}
            <input
              ref={fileRef}
              type="file"
              accept="application/pdf"
              className="hidden"
              onChange={handleFileSelect}
            />

            {/* Glow */}
            <div className="absolute inset-0 bg-linear-to-br from-orange-500/5 to-amber-500/5 opacity-0 group-hover:opacity-100 transition-opacity" />

            {file ? (
              <div className="relative flex flex-col items-center">
                <div className="relative">
                  <div className="p-5 rounded-3xl bg-green-100">
                    <FileText
                      size={34}
                      className="text-green-600"
                    />
                  </div>

                  <div className="absolute -bottom-1 -right-1">
                    <CheckCircle2
                      size={22}
                      className="text-green-500 bg-white rounded-full"
                    />
                  </div>
                </div>

                <h3 className="mt-4 font-semibold text-orange-900">
                  {file.name}
                </h3>

                <p className="text-sm text-gray-500 mt-1">
                  PDF sélectionné avec
                  succès
                </p>

                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setFile(null);
                  }}
                  className="
                    mt-4
                    text-sm font-medium
                    text-red-500
                    hover:text-red-600
                    transition-colors
                  "
                >
                  Retirer le fichier
                </button>
              </div>
            ) : (
              <div className="relative">
                <div className="mx-auto w-20 h-20 rounded-3xl bg-orange-100 flex items-center justify-center mb-5 group-hover:scale-105 hover:bg-orange-200 transition-transform">
                  <Upload
                    size={32}
                    className="text-orange-600"
                  />
                </div>

                <h3 className="text-lg font-semibold text-gray-900">
                  Déposez votre CV ici
                </h3>

                <p className="text-sm text-gray-500 mt-2">
                  Glissez-déposez un PDF
                  ou cliquez pour
                  sélectionner un fichier
                </p>

                <div className="mt-5 inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-orange-100 text-orange-700 text-sm font-medium">
                  <Upload size={15} />
                  Choisir un fichier
                </div>
              </div>
            )}
          </div>

          {/* Job Selector */}
          <div className="mt-6">
            <label className="text-sm font-medium text-gray-700 mb-2 block">
              Associer à un poste
            </label>

            <div className="relative">
              <Briefcase
                size={16}
                className="
                  absolute left-4 top-1/2 -translate-y-1/2
                  text-gray-400
                "
              />

              <select
                value={jobId}
                onChange={(e) =>
                  setJobId(
                    e.target.value
                  )
                }
                className="
                  w-full
                  h-12
                  pl-11 pr-4
                  rounded-2xl
                  border border-gray-200
                  bg-white
                  text-sm text-gray-700
                  outline-none
                  transition-all
                  focus:ring-4 focus:ring-orange-100
                  focus:border-orange-400
                "
              >
                <option value="">
                  — Aucun poste —
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

            <p className="text-xs text-gray-400 mt-2">
              Optionnel — utilisé pour le
              matching automatique
            </p>
          </div>

          {/* Actions */}
          <div className="flex items-center justify-end gap-3 mt-8">
            <button
              onClick={onClose}
              className="
                px-5 py-3
                rounded-2xl
                border border-gray-200
                bg-white
                text-sm font-medium text-gray-700
                hover:bg-gray-50
                hover:border-gray-300
                transition-all
              "
            >
              Annuler
            </button>

            <button
              disabled={!file || isPending}
              onClick={handleSubmit}
              className="
                flex items-center gap-2
                px-5 py-3
                rounded-2xl
                bg-linear-to-r
                from-orange-600
                to-amber-600
                text-white
                text-sm font-semibold
                shadow-md hover:shadow-xl
                transition-all duration-300
                hover:-translate-y-0.5
                active:scale-[0.98]
                disabled:opacity-70
                disabled:cursor-not-allowed
              "
            >
              <Upload
                size={16}
                className={
                  isPending
                    ? "animate-bounce"
                    : ""
                }
              />

              {isPending
                ? "Upload en cours..."
                : "Uploader le CV"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}