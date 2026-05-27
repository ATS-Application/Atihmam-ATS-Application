// frontend/src/pages/Analytics.jsx

import { useState, useEffect } from "react";
import { RefreshCw, ChevronRight, AlertTriangle, AlertCircle, CheckCircle } from "lucide-react";
import axiosClient from "../api/axiosClient";

// ─── Score Radar ──────────────────────────────────────────────────────────────

function ScoreRadar({ breakdown }) {
  if (!breakdown) return null;

  const dimensions = [
    { key: "skill_match",         label: "Skills"      },
    { key: "experience",          label: "Expérience"  },
    { key: "project_complexity",  label: "Complexité"  },
    { key: "seniority",           label: "Séniorité"   },
    { key: "domain_diversity",    label: "Diversité"   },
    { key: "career_progression",  label: "Progression" },
  ];

  const cx = 120, cy = 120, r = 85;
  const n = dimensions.length;

  const toXY = (i, val) => {
    const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
    const dist  = (val / 100) * r;
    return { x: cx + dist * Math.cos(angle), y: cy + dist * Math.sin(angle) };
  };

  const gridLevels   = [25, 50, 75, 100];
  const labelRadius  = r + 20;
  const scorePoints  = dimensions.map((d, i) => toXY(i, breakdown[d.key] || 0));
  const scorePath    = scorePoints.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ") + " Z";

  return (
    <svg viewBox="0 0 240 240" className="w-full max-w-xs mx-auto">
      {gridLevels.map((lvl) => {
        const pts  = dimensions.map((_, i) => toXY(i, lvl));
        const path = pts.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ") + " Z";
        return (
          <path
            key={lvl}
            d={path}
            fill="none"
            stroke="#e5e7eb"
            strokeWidth="1"
            strokeDasharray={lvl < 100 ? "3 2" : "0"}
          />
        );
      })}
      {dimensions.map((_, i) => {
        const end = toXY(i, 100);
        return <line key={i} x1={cx} y1={cy} x2={end.x} y2={end.y} stroke="#e5e7eb" strokeWidth="1" />;
      })}
      <path d={scorePath} fill="rgba(17,24,39,0.07)" stroke="#111827" strokeWidth="1.5" />
      {scorePoints.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r="3.5" fill="#111827" stroke="white" strokeWidth="1.5" />
      ))}
      {dimensions.map((d, i) => {
        const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
        const lx    = cx + labelRadius * Math.cos(angle);
        const ly    = cy + labelRadius * Math.sin(angle);
        const val   = Math.round(breakdown[d.key] || 0);
        return (
          <g key={i}>
            <text x={lx} y={ly - 5}  textAnchor="middle" fontSize="7"  fill="#9ca3af" fontWeight="500">{d.label}</text>
            <text x={lx} y={ly + 7}  textAnchor="middle" fontSize="8"  fill="#111827" fontWeight="700">{val}</text>
          </g>
        );
      })}
    </svg>
  );
}

// ─── Score Bar ────────────────────────────────────────────────────────────────

function ScoreDimension({ label, value, note, bonus }) {
  const pct = Math.min(100, (value / 100) * 100);
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 flex-1 min-w-0">
          <span className="text-xs text-gray-600 font-medium truncate">{label}</span>
          {note  && <span className="text-xs text-gray-400 italic truncate ml-1">({note})</span>}
          {bonus > 0 && <span className="text-xs text-gray-500 font-medium shrink-0">+{bonus}</span>}
        </div>
        <span className="text-xs font-semibold text-gray-900 shrink-0 ml-2 tabular-nums">{Math.round(value)}</span>
      </div>
      <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div className="h-full rounded-full bg-gray-800 transition-all duration-700" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

// ─── Stat Card ────────────────────────────────────────────────────────────────

function StatCard({ label, value, sub }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5">
      <p className="text-xs font-medium text-gray-400 uppercase tracking-widest mb-3">{label}</p>
      <p className="text-3xl font-semibold text-gray-900 tabular-nums">{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  );
}

// ─── Pipeline Bar Chart ───────────────────────────────────────────────────────

function PipelineChart({ distribution }) {
  if (!distribution) return null;
  const entries = Object.entries(distribution);
  const total   = entries.reduce((s, [, v]) => s + v, 0);

  return (
    <div className="space-y-3">
      {entries.map(([label, count]) => {
        const pct = total > 0 ? (count / total) * 100 : 0;
        return (
          <div key={label} className="space-y-1">
            <div className="flex justify-between text-xs">
              <span className="text-gray-600 capitalize">{label}</span>
              <span className="font-medium text-gray-800 tabular-nums">{count} ({Math.round(pct)}%)</span>
            </div>
            <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full bg-gray-700 transition-all duration-700"
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Skill Cloud ──────────────────────────────────────────────────────────────

function SkillCloud({ skills }) {
  if (!skills?.length) return <p className="text-sm text-gray-400">Aucune donnée</p>;
  const max = skills[0]?.count || 1;
  return (
    <div className="flex flex-wrap gap-2">
      {skills.map(({ skill, count }) => {
        const weight  = count / max;
        const size    = 11 + weight * 4;
        const opacity = 0.45 + weight * 0.55;
        return (
          <span
            key={skill}
            className="px-2.5 py-1 rounded border border-gray-200 text-gray-700 font-medium bg-white"
            style={{ fontSize: `${size}px`, opacity }}
          >
            {skill}
            <span className="ml-1 text-gray-400 text-xs">×{count}</span>
          </span>
        );
      })}
    </div>
  );
}

// ─── Recruiter Suggestions ────────────────────────────────────────────────────

function RecruiterSuggestionsPanel({ suggestions, basedOnHired }) {
  if (!suggestions?.length) return null;
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5">
      <div className="flex items-baseline gap-3 mb-4">
        <h2 className="text-sm font-semibold text-gray-900">Suggestions IA</h2>
        <span className="text-xs text-gray-400">
          basé sur {basedOnHired} embauche{basedOnHired !== 1 ? "s" : ""}
        </span>
      </div>
      <div className="space-y-2">
        {suggestions.map((suggestion, i) => (
          <div key={i} className="flex items-start gap-2.5 py-2.5 border-b border-gray-50 last:border-0">
            <span className="text-gray-300 shrink-0 mt-0.5">›</span>
            <p className="text-xs text-gray-600 leading-relaxed">{suggestion}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Project Dedup Badge ──────────────────────────────────────────────────────

function ProjectDedupBadge({ dedup }) {
  if (!dedup || dedup.duplicates_removed === 0) return null;
  return (
    <div className="flex items-start gap-2.5 p-3 rounded-lg bg-gray-50 border border-gray-200">
      <AlertTriangle size={13} className="text-gray-500 shrink-0 mt-0.5" />
      <div>
        <p className="text-xs font-semibold text-gray-700">Projets similaires détectés</p>
        <p className="text-xs text-gray-500 mt-0.5">
          {dedup.duplicates_removed} projet{dedup.duplicates_removed > 1 ? "s" : ""} supprimé{dedup.duplicates_removed > 1 ? "s" : ""}.
          {dedup.real_duration_years
            ? ` Expérience réelle estimée : ~${dedup.real_duration_years}y.`
            : ""}
        </p>
        {dedup.diversity_ratio != null && (
          <div className="flex items-center gap-2 mt-2">
            <div className="h-1.5 rounded-full bg-gray-200 flex-1 overflow-hidden">
              <div
                className="h-full rounded-full bg-gray-500"
                style={{ width: `${Math.round(dedup.diversity_ratio * 100)}%` }}
              />
            </div>
            <span className="text-xs text-gray-500 tabular-nums">{Math.round(dedup.diversity_ratio * 100)}% unique</span>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Score Detail Modal ───────────────────────────────────────────────────────

function ScoreDetailModal({ candidateId, onClose }) {
  const [data,      setData]      = useState(null);
  const [loading,   setLoading]   = useState(true);
  const [rescoring, setRescoring] = useState(false);

  useEffect(() => {
    if (!candidateId) return;
    setLoading(true);
    axiosClient.get(`/analytics/score-breakdown/${candidateId}`)
      .then((r) => setData(r.data))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [candidateId]);

  const handleRescore = async () => {
    setRescoring(true);
    try {
      const r = await axiosClient.post(`/analytics/rescore-candidate/${candidateId}`);
      setData((prev) => ({ ...prev, ...r.data }));
    } finally {
      setRescoring(false);
    }
  };

  if (!candidateId) return null;

  const dimensions = [
    { key: "skill_match",        label: "Skill Match"         },
    { key: "experience",         label: "Expérience"          },
    { key: "project_complexity", label: "Complexité projets"  },
    { key: "seniority",          label: "Niveau séniorité"    },
    { key: "domain_diversity",   label: "Diversité domaines"  },
    { key: "career_progression", label: "Progression carrière"},
  ];

  const bonuses = [
    { key: "depth_bonus",        label: "Skill Depth Bonus",        sign: "+" },
    { key: "ecosystem_bonus",    label: "Ecosystem Mastery Bonus",  sign: "+" },
    { key: "certification_bonus",label: "Certification Bonus",      sign: "+" },
    { key: "recruiter_fit_bonus",label: "Recruiter Fit Bonus",      sign: "+" },
    { key: "diversity_penalty",  label: "Low Diversity Penalty",    sign: "−" },
    { key: "repetition_penalty", label: "Project Repetition Penalty",sign: "−"},
  ];

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl border border-gray-200 w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-xl">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Analyse du score</h2>
            {data && <p className="text-xs text-gray-400 mt-0.5">{data.candidate_name}</p>}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleRescore}
              disabled={rescoring}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-gray-200 text-xs font-medium text-gray-600 hover:bg-gray-50 transition-colors"
            >
              <RefreshCw size={12} className={rescoring ? "animate-spin" : ""} />
              Re-scorer
            </button>
            <button
              onClick={onClose}
              className="px-3 py-1.5 rounded border border-gray-200 text-xs font-medium text-gray-600 hover:bg-gray-50 transition-colors"
            >
              Fermer
            </button>
          </div>
        </div>

        {loading ? (
          <div className="p-16 text-center text-sm text-gray-400">Chargement…</div>
        ) : data ? (
          <div className="p-6 space-y-6">
            {/* Score + radar */}
            <div className="flex items-center gap-6 p-5 rounded-lg bg-gray-50 border border-gray-200">
              <div className="shrink-0">
                <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Score intelligent</p>
                <p className="text-5xl font-bold text-gray-900 tabular-nums">{data.final_score}</p>
                <p className="text-xs text-gray-500 mt-2 max-w-45 leading-relaxed">{data.reasoning}</p>
              </div>
              <div className="flex-1">
                <ScoreRadar breakdown={data.score_breakdown} />
              </div>
            </div>

            {/* Dedup warning */}
            {data.insights?.project_dedup?.duplicates_removed > 0 && (
              <ProjectDedupBadge dedup={data.insights.project_dedup} />
            )}

            {/* Breakdown */}
            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Dimensions</h3>
              <div className="space-y-3">
                {dimensions.map((d) => (
                  <ScoreDimension
                    key={d.key}
                    label={d.label}
                    value={data.score_breakdown?.[d.key] || 0}
                    note={
                      d.key === "experience" &&
                      data.insights?.experience_note?.includes("Adjusted")
                        ? `${data.insights.effective_years}y réel`
                        : null
                    }
                    bonus={0}
                  />
                ))}
              </div>
            </div>

            {/* Bonuses / Penalties */}
            {bonuses.some((b) => data.score_breakdown?.[b.key] > 0) && (
              <div>
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Ajustements</h3>
                <div className="space-y-1.5">
                  {bonuses.filter((b) => data.score_breakdown?.[b.key] > 0).map((b) => (
                    <div
                      key={b.key}
                      className="flex justify-between items-center text-xs px-3 py-2 rounded border border-gray-100 bg-gray-50"
                    >
                      <span className="text-gray-600">{b.label}</span>
                      <span className={`font-semibold tabular-nums ${b.sign === "+" ? "text-gray-900" : "text-gray-500"}`}>
                        {b.sign}{data.score_breakdown[b.key]}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Insights grid */}
            {data.insights && (
              <div className="grid grid-cols-3 gap-3">
                {[
                  { label: "Niveau",      value: data.insights.seniority_level                 },
                  { label: "Complexité",  value: data.insights.complexity_level                },
                  { label: "Domaines",    value: data.insights.unique_domains?.length ?? 0     },
                ].map(({ label, value }) => (
                  <div key={label} className="p-3 rounded-lg bg-gray-50 border border-gray-100 text-center">
                    <p className="text-xs text-gray-400 mb-1">{label}</p>
                    <p className="text-sm font-semibold text-gray-900">{value}</p>
                  </div>
                ))}
              </div>
            )}

            {/* Keywords */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs font-semibold text-gray-600 mb-2 flex items-center gap-1">
                  <CheckCircle size={11} className="text-gray-400" />
                  Présents ({data.matched_keywords?.length || 0})
                </p>
                <div className="flex flex-wrap gap-1">
                  {(data.matched_keywords || []).slice(0, 12).map((k) => (
                    <span key={k} className="text-xs px-2 py-0.5 rounded border border-gray-200 text-gray-600 bg-gray-50">
                      {k}
                    </span>
                  ))}
                </div>
              </div>
              <div>
                <p className="text-xs font-semibold text-gray-600 mb-2 flex items-center gap-1">
                  <AlertCircle size={11} className="text-gray-400" />
                  Manquants ({data.missing_keywords?.length || 0})
                </p>
                <div className="flex flex-wrap gap-1">
                  {(data.missing_keywords || []).slice(0, 12).map((k) => (
                    <span key={k} className="text-xs px-2 py-0.5 rounded border border-gray-200 text-gray-400 bg-white">
                      {k}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* Recruiter suggestions */}
            {data.recruiter_suggestions?.length > 0 && (
              <div>
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Suggestions recruteur IA</h3>
                <ul className="space-y-2">
                  {data.recruiter_suggestions.map((s, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-gray-600">
                      <span className="text-gray-300 shrink-0 mt-0.5">›</span>
                      {s}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <div className="p-16 text-center text-sm text-gray-400">Aucune donnée disponible</div>
        )}
      </div>
    </div>
  );
}

// ─── Main Analytics Page ──────────────────────────────────────────────────────

export default function Analytics() {
  const [pipelineStats,       setPipelineStats]       = useState(null);
  const [recruiterProfile,    setRecruiterProfile]    = useState(null);
  const [recommendations,     setRecommendations]     = useState([]);
  const [recruiterSuggestions,setRecruiterSuggestions]= useState([]);
  const [loading,             setLoading]             = useState(true);
  const [selectedCandidate,   setSelectedCandidate]   = useState(null);
  const [rescoring,           setRescoring]           = useState(false);
  const [rescoreResult,       setRescoreResult]       = useState(null);

  useEffect(() => {
    Promise.all([
      axiosClient.get("/analytics/pipeline-stats"),
      axiosClient.get("/analytics/recruiter-profile"),
      axiosClient.get("/analytics/smart-recommendations"),
      axiosClient.get("/analytics/recruiter-suggestions"),
    ])
      .then(([stats, profile, recs, suggestions]) => {
        setPipelineStats(stats.data);
        setRecruiterProfile(profile.data);
        setRecommendations(recs.data.recommendations || []);
        setRecruiterSuggestions(suggestions.data.suggestions || []);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const handleRescoreAll = async () => {
    setRescoring(true);
    setRescoreResult(null);
    try {
      const r = await axiosClient.post("/analytics/rescore-all");
      setRescoreResult(r.data);
    } catch (e) {
      console.error(e);
    } finally {
      setRescoring(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full p-20">
        <p className="text-sm text-gray-400">Chargement…</p>
      </div>
    );
  }

  return (
    <div className="p-6 lg:p-8 space-y-8 bg-gray-50 min-h-screen">
      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Analytics</h1>
          <p className="text-sm text-gray-400 mt-0.5">Intelligence adaptative à vos patterns de recrutement</p>
        </div>
        <div className="flex items-center gap-3">
          {rescoreResult && (
            <span className="text-xs font-medium text-gray-600 bg-white border border-gray-200 px-3 py-2 rounded-lg">
              {rescoreResult.updated} candidats re-scorés
              {rescoreResult.errors > 0 && (
                <span className="text-gray-400 ml-2">({rescoreResult.errors} erreurs)</span>
              )}
            </span>
          )}
          <button
            onClick={handleRescoreAll}
            disabled={rescoring}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-900 text-white text-xs font-medium hover:bg-gray-700 transition-colors disabled:opacity-60"
          >
            <RefreshCw size={13} className={rescoring ? "animate-spin" : ""} />
            {rescoring ? "Re-scoring…" : "Re-scorer tout"}
          </button>
        </div>
      </div>

      {/* KPI Row */}
      {pipelineStats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatCard label="Total candidats"  value={pipelineStats.total_candidates || 0} />
          <StatCard label="Score moyen"      value={pipelineStats.avg_score || 0}        sub="/ 100"                  />
          <StatCard label="Taux conversion"  value={`${pipelineStats.conversion_rate || 0}%`} sub="candidature → embauche" />
          <StatCard label="Profils embauchés" value={recruiterProfile?.hired_count || 0} sub="données d'entraînement" />
        </div>
      )}

      {/* Suggestions banner */}
      {recruiterSuggestions.length > 0 && (
        <RecruiterSuggestionsPanel
          suggestions={recruiterSuggestions}
          basedOnHired={recruiterProfile?.hired_count || 0}
        />
      )}

      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Left column */}
        <div className="space-y-4">
          {/* Recruiter profile */}
          <div className="bg-white rounded-lg border border-gray-200 p-5">
            <h2 className="text-sm font-semibold text-gray-900 mb-4">Profil recruteur</h2>
            {recruiterProfile?.hired_count > 0 ? (
              <div className="space-y-4">
                <div className="space-y-2.5">
                  {(recruiterProfile.insights || []).map((insight, i) => (
                    <p key={i} className="text-xs text-gray-600 leading-relaxed pl-3 border-l-2 border-gray-200">
                      {insight}
                    </p>
                  ))}
                </div>
                {recruiterProfile.common_domains?.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Domaines privilégiés</p>
                    <div className="flex flex-wrap gap-1.5">
                      {recruiterProfile.common_domains.map((d) => (
                        <span key={d} className="text-xs px-2 py-0.5 rounded border border-gray-200 text-gray-600 bg-gray-50 font-medium">
                          {d}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {recruiterProfile.avg_experience && (
                  <div className="pt-3 border-t border-gray-100">
                    <p className="text-xs text-gray-400 mb-1">Expérience moyenne embauche</p>
                    <p className="text-2xl font-semibold text-gray-900 tabular-nums">
                      {recruiterProfile.avg_experience.toFixed(1)}
                      <span className="text-sm font-normal text-gray-400 ml-1">ans</span>
                    </p>
                  </div>
                )}
              </div>
            ) : (
              <div className="py-6 text-center">
                <p className="text-sm font-medium text-gray-700">Mode apprentissage</p>
                <p className="text-xs text-gray-400 mt-1 leading-relaxed">
                  Embauchez votre premier candidat pour activer l'IA.
                </p>
              </div>
            )}
          </div>

          {/* Score distribution */}
          {pipelineStats?.score_distribution && (
            <div className="bg-white rounded-lg border border-gray-200 p-5">
              <h2 className="text-sm font-semibold text-gray-900 mb-4">Distribution des scores</h2>
              <PipelineChart distribution={pipelineStats.score_distribution} />
            </div>
          )}
        </div>

        {/* Right columns */}
        <div className="lg:col-span-2 space-y-4">
          {/* Skill cloud */}
          {pipelineStats?.top_skills?.length > 0 && (
            <div className="bg-white rounded-lg border border-gray-200 p-5">
              <h2 className="text-sm font-semibold text-gray-900 mb-4">Compétences fréquentes</h2>
              <SkillCloud skills={pipelineStats.top_skills} />
            </div>
          )}

          {/* Smart recommendations */}
          <div className="bg-white rounded-lg border border-gray-200 p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-gray-900">Recommandations</h2>
              <span className="text-xs text-gray-400 tabular-nums">{recommendations.length}</span>
            </div>
            {recommendations.length > 0 ? (
              <div className="divide-y divide-gray-50">
                {recommendations.map((rec) => (
                  <div
                    key={rec.candidate_id}
                    className="flex items-center justify-between py-3 cursor-pointer group"
                    onClick={() => setSelectedCandidate(rec.candidate_id)}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-7 h-7 rounded-full bg-gray-100 border border-gray-200 flex items-center justify-center font-medium text-xs text-gray-600 shrink-0">
                        {rec.candidate_name?.[0] || "?"}
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-gray-900">{rec.candidate_name}</p>
                        <p className="text-xs text-gray-400 truncate">{rec.match_reason}</p>
                        {rec.match_categories?.length > 0 && (
                          <div className="flex gap-1 mt-1">
                            {rec.match_categories.map((cat) => (
                              <span key={cat} className="text-xs px-1.5 py-0.5 rounded border border-gray-200 text-gray-500 capitalize">
                                {cat}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="text-sm font-semibold text-gray-900 tabular-nums">{rec.confidence}%</span>
                      <ChevronRight size={13} className="text-gray-300 group-hover:text-gray-600 transition-colors" />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-400 py-4">
                Embauchez des candidats pour activer les recommandations.
              </p>
            )}
          </div>

          {/* Pipeline status */}
          {pipelineStats?.status_breakdown && (
            <div className="bg-white rounded-lg border border-gray-200 p-5">
              <h2 className="text-sm font-semibold text-gray-900 mb-4">Statut du pipeline</h2>
              <div className="grid grid-cols-3 gap-2">
                {Object.entries(pipelineStats.status_breakdown).map(([status, count]) => (
                  <div key={status} className="p-3 rounded-lg bg-gray-50 border border-gray-100 text-center">
                    <p className="text-2xl font-semibold text-gray-900 tabular-nums">{count}</p>
                    <p className="text-xs text-gray-400 mt-0.5 capitalize">{status}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Score modal */}
      {selectedCandidate && (
        <ScoreDetailModal
          candidateId={selectedCandidate}
          onClose={() => setSelectedCandidate(null)}
        />
      )}
    </div>
  );
}