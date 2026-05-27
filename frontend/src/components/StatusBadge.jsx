// frontend/src/components/StatusBadge.jsx
const STATUS_CONFIG = {
  applied:   { label: "Candidature", color: "bg-blue-100 text-blue-700" },
  screening: { label: "Screening",   color: "bg-yellow-100 text-yellow-700" },
  interview: { label: "Entretien",   color: "bg-purple-100 text-purple-700" },
  offer:     { label: "Offre",       color: "bg-orange-100 text-orange-700" },
  hired:     { label: "Embauché",    color: "bg-green-100 text-green-700" },
  rejected:  { label: "Refusé",      color: "bg-red-100 text-red-700" },
};

export default function StatusBadge({ status }) {
  const config = STATUS_CONFIG[status] ?? { label: status, color: "bg-gray-100 text-gray-700" };
  return (
    <span className={`badge ${config.color}`}>
      {config.label}
    </span>
  );
}