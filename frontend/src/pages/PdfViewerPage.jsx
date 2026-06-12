import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Download, ExternalLink } from "lucide-react";

export default function PdfViewerPage() {
  const { jobId, filename } = useParams();
  const navigate = useNavigate();

  // Adjust this URL if your backend serves files differently
  const pdfUrl = `/api/uploads/candidates/${jobId}/${filename}`;

  const decodedFilename = decodeURIComponent(filename || "");

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col">
      {/* Top Navigation Bar */}
      <div className="bg-gray-900 border-b border-gray-800 px-6 py-4 flex items-center justify-between sticky top-0 z-50">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-2 text-white hover:text-gray-300 transition-colors"
        >
          <ArrowLeft size={20} />
          <span className="font-medium">Retour</span>
        </button>

        <div className="text-white font-medium truncate max-w-xl px-4 text-center">
          {decodedFilename}
        </div>

        <div className="flex items-center gap-3">
          <a
            href={pdfUrl}
            download={decodedFilename}
            className="flex items-center gap-2 px-4 py-2 text-sm bg-white/10 hover:bg-white/20 text-white rounded-lg transition-colors"
          >
            <Download size={18} />
            Télécharger
          </a>
          
          <a
            href={pdfUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 px-4 py-2 text-sm bg-white/10 hover:bg-white/20 text-white rounded-lg transition-colors"
          >
            <ExternalLink size={18} />
            Nouvel onglet
          </a>
        </div>
      </div>

      {/* PDF Viewer Area */}
      <div className="flex-1 p-6 bg-gray-950 flex items-center justify-center overflow-auto">
        <div className="w-full max-w-5xl bg-white shadow-2xl rounded-xl overflow-hidden border border-gray-700">
          <iframe
            src={pdfUrl}
            className="w-full h-[calc(100vh-110px)] border-0"
            title={decodedFilename}
          />
        </div>
      </div>
    </div>
  );
}