export default function ScoreBadge({ score }) {
  if (score == null) return <span className="text-gray-400 text-sm">—</span>;

  const color =
    score >= 7 ? "text-green-600" :
    score >= 4 ? "text-yellow-600" :
                 "text-red-600";

  return (
    <span className={`font-semibold text-sm ${color}`}>
      {score.toFixed(1)}/10
    </span>
  );
}