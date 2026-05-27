// frontend/src/components/ScoreBadge.jsx
export default function ScoreBadge({
  score,
}) {
  if (
    score === null ||
    score === undefined
  ) {
    return (
      <span className="text-gray-400">
        —
      </span>
    );
  }

  let color =
    "bg-red-100 text-red-700";

  if (score >= 80) {
    color =
      "bg-green-100 text-green-700";
  } else if (score >= 60) {
    color =
      "bg-yellow-100 text-yellow-700";
  }

  return (
    <div
      className={`
        inline-flex
        items-center
        px-3 py-1
        rounded-full
        text-xs
        font-semibold
        ${color}
      `}
    >
      {score}/100
    </div>
  );
}