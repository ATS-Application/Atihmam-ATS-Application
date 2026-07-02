// frontend/src/components/UploadCVModal.jsx

import { useState, useRef } from "react";
import {
  X,
  Upload,
  FileText,
  Briefcase,
  Sparkles,
} from "lucide-react";

import toast from "react-hot-toast";

import { useUploadCV } from "../hooks/useCandidates";
import { useJobs } from "../hooks/useJobs";

export default function UploadCVModal({ onClose }) {
  const [files, setFiles] = useState([]);
  const [jobId, setJobId] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);

  const fileRef = useRef();

  const { mutateAsync } = useUploadCV();
  const { data: jobs = [] } = useJobs();

  const ALLOWED_TYPES = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp"
  ];

  const ALLOWED_EXTENSIONS = [
    ".pdf",
    ".docx",
    ".doc",
    ".png",
    ".jpeg",
    ".jpg",
    ".webp"
  ];

  const isValidFile = (file) => {
    if (ALLOWED_TYPES.includes(file.type)) return true;
    const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    return ALLOWED_EXTENSIONS.includes(ext);
  };

  function handleDrop(e) {
    e.preventDefault();
    setIsDragging(false);

    const dropped = Array.from(e.dataTransfer.files || []);
    const validFiles = dropped.filter(isValidFile);

    if (validFiles.length > 0) {
      setFiles((prev) => [...prev, ...validFiles]);
    }

    if (dropped.length !== validFiles.length) {
      toast.error("Certains fichiers ont été ignorés (PDF, Word, Images uniquement)");
    }
  }

  function handleFileSelect(e) {
    const selected = Array.from(e.target.files || []);
    const validFiles = selected.filter(isValidFile);

    if (validFiles.length > 0) {
      setFiles((prev) => [...prev, ...validFiles]);
    }

    if (selected.length !== validFiles.length) {
      toast.error("Certains fichiers ont été ignorés (PDF, Word, Images uniquement)");
    }
  }

  async function handleSubmit() {
    if (files.length === 0) return;
    setIsUploading(true);

    let successCount = 0;
    let failCount = 0;
    let dupCount = 0;

    for (const file of files) {
      try {
        await mutateAsync({
          file,
          job_id: jobId || undefined,
        });
        successCount++;
      } catch (error) {
        if (error?.response?.status === 409) {
          dupCount++;
        } else {
          failCount++;
        }
      }
    }

    setIsUploading(false);

    if (successCount > 0) {
      toast.success(`${successCount} CV importé(s) avec succès`);
      onClose();
    }
    if (dupCount > 0) {
      toast.error(`${dupCount} CV déjà existant(s)`);
    }
    if (failCount > 0) {
      toast.error(`${failCount} échec(s) d'importation`);
    }
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
          w-full max-w-lg
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
                Uploader des CV
              </h2>

              <p className="text-sm text-gray-500 mt-1">
                Importez un ou plusieurs CV et
                associez-les à un poste
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
              files.length === 0 && fileRef.current?.click()
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
              p-8
              text-center
              ${files.length === 0 ? "cursor-pointer" : "cursor-default"}
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
              accept="application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/*"
              multiple
              className="hidden"
              onChange={handleFileSelect}
            />

            {/* Glow */}
            <div className="absolute inset-0 bg-linear-to-br from-orange-500/5 to-amber-500/5 opacity-0 group-hover:opacity-100 transition-opacity" />

            {files.length > 0 ? (
              <div className="relative flex flex-col w-full text-left" onClick={(e) => e.stopPropagation()}>
                <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
                  Fichiers sélectionnés ({files.length})
                </h4>
                <div className="max-h-40 overflow-y-auto space-y-2 pr-1">
                  {files.map((f, i) => (
                    <div key={i} className="flex items-center justify-between p-2.5 rounded-2xl bg-gray-50 border border-gray-100 hover:border-gray-200 transition-colors">
                      <div className="flex items-center gap-3 truncate">
                        <div className="p-2 rounded-xl bg-orange-100/50">
                          <FileText size={16} className="text-orange-600" />
                        </div>
                        <div className="truncate">
                          <p className="text-xs font-semibold text-gray-700 truncate">{f.name}</p>
                          <p className="text-[10px] text-gray-400">{(f.size / (1024 * 1024)).toFixed(2)} MB</p>
                        </div>
                      </div>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setFiles((prev) => prev.filter((_, idx) => idx !== i));
                        }}
                        className="p-1 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors"
                      >
                        <X size={14} />
                      </button>
                    </div>
                  ))}
                </div>
                
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    fileRef.current?.click();
                  }}
                  className="mt-4 inline-flex items-center justify-center gap-2 px-3 py-2 rounded-xl border border-gray-200 bg-white text-gray-600 text-xs font-semibold hover:bg-gray-50 transition-colors"
                >
                  <Upload size={12} />
                  Ajouter d'autres fichiers
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
                  Déposez vos CV ici
                </h3>

                <p className="text-sm text-gray-500 mt-2">
                  Glissez-déposez un ou plusieurs PDF/Word
                  ou cliquez pour sélectionner
                </p>

                <div className="mt-5 inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-orange-100 text-orange-700 text-sm font-medium">
                  <Upload size={15} />
                  Choisir des fichiers
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
              disabled={files.length === 0 || isUploading}
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
                  isUploading
                    ? "animate-bounce"
                    : ""
                }
              />

              {isUploading
                ? "Upload en cours..."
                : "Uploader les CV"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
