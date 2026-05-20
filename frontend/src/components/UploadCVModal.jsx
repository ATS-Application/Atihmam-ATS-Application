import { useState, useRef } from "react";
import { X, Upload, FileText } from "lucide-react";
import { useUploadCV } from "../hooks/useCandidates";
import { useJobs } from "../hooks/useJobs";

export default function UploadCVModal({ onClose }) {
  const [file, setFile] = useState(null);
  const [jobId, setJobId] = useState("");
  const fileRef = useRef();
  const { mutate, isPending } = useUploadCV();
  const { data: jobs = [] } = useJobs();

  const handleDrop = (e) => {
    e.preventDefault();
    const dropped = e.dataTransfer.files[0];
    if (dropped?.type === "application/pdf") setFile(dropped);
  };

  const handleSubmit = () => {
    if (!file) return;
    mutate({ file, job_id: jobId || undefined }, { onSuccess: onClose });
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="card w-full max-w-md p-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-semibold">Uploader un CV</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X size={20} />
          </button>
        </div>

        {/* Drop zone */}
        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleDrop}
          onClick={() => fileRef.current.click()}
          className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center cursor-pointer hover:border-primary-400 hover:bg-primary-50 transition-colors mb-4"
        >
          <input
            ref={fileRef}
            type="file"
            accept="application/pdf"
            className="hidden"
            onChange={(e) => setFile(e.target.files[0])}
          />
          {file ? (
            <div className="flex items-center justify-center gap-2 text-primary-600">
              <FileText size={20} />
              <span className="text-sm font-medium">{file.name}</span>
            </div>
          ) : (
            <>
              <Upload size={24} className="mx-auto text-gray-400 mb-2" />
              <p className="text-sm text-gray-500">Glissez un PDF ou cliquez pour sélectionner</p>
            </>
          )}
        </div>

        {/* Job selector */}
        <select
          className="input mb-5"
          value={jobId}
          onChange={(e) => setJobId(e.target.value)}
        >
          <option value="">— Associer à un poste (optionnel) —</option>
          {jobs.map((j) => (
            <option key={j.id} value={j.id}>{j.title}</option>
          ))}
        </select>

        <div className="flex gap-3 justify-end">
          <button className="btn-secondary" onClick={onClose}>Annuler</button>
          <button
            className="btn-primary"
            onClick={handleSubmit}
            disabled={!file || isPending}
          >
            {isPending ? "Upload..." : "Uploader"}
          </button>
        </div>
      </div>
    </div>
  );
}