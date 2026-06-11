// frontend/src/pages/JobList.jsx

import { useState } from "react";
import { Plus, Pencil, Trash2, X, Check, ChevronDown, ChevronUp } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useJobs, useCreateJob, useUpdateJob, useDeleteJob } from "../hooks/useJobs";
// import { useCandidates } from "../hooks/useCandidates";

export const JOB_DOMAINS = [
  { value: "achats_supply_chain",        label: "Achats & Supply Chain"                        },
  { value: "administration_secretariat", label: "Administration & Secrétariat"                 },
  { value: "agriculture_agroalimentaire",label: "Agriculture & Agroalimentaire"                },
  { value: "art_culture_design",         label: "Art, Culture & Design"                        },
  { value: "banque_assurance",           label: "Banque & Assurance"                           },
  { value: "commercial_vente",           label: "Commercial & Vente"                           },
  { value: "comptabilite_finance",       label: "Comptabilité & Finance"                       },
  { value: "construction_btp",           label: "Construction & BTP"                           },
  { value: "droit_juridique",            label: "Droit & Juridique"                            },
  { value: "education_formation",        label: "Éducation & Formation"                        },
  { value: "energie_mines_petrole",      label: "Énergie, Mines & Pétrole"                    },
  { value: "hotellerie_restauration",    label: "Hôtellerie & Restauration"                   },
  { value: "immobilier",                 label: "Immobilier"                                   },
  { value: "informatique_dev",           label: "Informatique & Développement logiciel"        },
  { value: "ingenierie_techniques",      label: "Ingénierie & Techniques"                     },
  { value: "journalisme_medias",         label: "Journalisme & Médias"                        },
  { value: "marketing_communication",    label: "Marketing & Communication"                    },
  { value: "production_industrie",       label: "Production & Industrie"                      },
  { value: "qhse",                       label: "Qualité, Hygiène, Sécurité, Environnement"   },
  { value: "reseaux_telecoms_cyber",     label: "Réseaux, Télécoms & Cybersécurité"           },
  { value: "ressources_humaines",        label: "Ressources Humaines"                         },
  { value: "sante_medical",             label: "Santé & Médical"                              },
  { value: "sciences_recherche",         label: "Sciences & Recherche"                        },
  { value: "services_generaux",          label: "Services Généraux"                           },
  { value: "stage_jeune_diplome",        label: "Stage / Jeune diplômé"                      },
  { value: "etudiant",                   label: "Étudiant"                                    },
  { value: "tourisme_loisirs",           label: "Tourisme & Loisirs"                         },
  { value: "transport_logistique",       label: "Transport & Logistique"                      },
  { value: "travail_social_ong",         label: "Travail Social & ONG"                        },
];

const DEGREE_OPTIONS = [
  { value: "none",        label: "Aucun requis"       },
  { value: "engineer",     label: "Bac+2/3 Ingénieur" },
  { value: "high_school", label: "Bac / High School"  },
  { value: "associate",   label: "Bac+2 / Associate"  },
  { value: "bachelor",    label: "Bac+3 / Bachelor"   },
  { value: "master",      label: "Bac+5 / Master"     },
  { value: "phd",         label: "Doctorat / PhD"     },
];

const EMPTY_SCREENING = {
  min_degree: "none",
  min_experience_years: 0,
  required_certifications: [],
  custom_questions: [],
};

// ─── Confirm Modal ────────────────────────────────────────────────────────────

function ConfirmModal({ title, message, onConfirm, onCancel }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/30 backdrop-blur-sm"
        onClick={onCancel}
      />
      <div className="relative bg-white rounded-xl border border-gray-200 shadow-xl p-6 w-full max-w-sm mx-4">
        <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
        <p className="text-xs text-gray-500 mt-1.5 leading-relaxed">{message}</p>
        <div className="flex items-center justify-end gap-2 mt-5">
          <button
            onClick={onCancel}
            className="px-4 py-2 rounded-lg border border-gray-200 bg-white text-xs font-medium text-gray-600 hover:bg-gray-50 transition-colors"
          >
            Annuler
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white text-xs font-medium transition-colors"
          >
            Supprimer
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Screening Builder ────────────────────────────────────────────────────────

function ScreeningBuilder({ value, onChange }) {
  const [certInput, setCertInput] = useState("");
  const [open, setOpen]           = useState(false);

  function update(patch) { onChange({ ...value, ...patch }); }

  function addCert() {
    const t = certInput.trim();
    if (!t) return;
    update({ required_certifications: [...value.required_certifications, t] });
    setCertInput("");
  }

  function removeCert(idx) {
    update({ required_certifications: value.required_certifications.filter((_, i) => i !== idx) });
  }

  function addQuestion() {
    update({ custom_questions: [...value.custom_questions, { id: crypto.randomUUID(), text: "", required: false }] });
    if (!open) setOpen(true);
  }

  function updateQuestion(id, patch) {
    update({ custom_questions: value.custom_questions.map((q) => q.id === id ? { ...q, ...patch } : q) });
  }

  function removeQuestion(id) {
    update({ custom_questions: value.custom_questions.filter((q) => q.id !== id) });
  }

  const hasContent =
    value.min_degree !== "none" ||
    value.min_experience_years > 0 ||
    value.required_certifications.length > 0 ||
    value.custom_questions.length > 0;

  return (
    <div className="rounded-lg border border-gray-200 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100 transition-colors text-left"
      >
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-gray-700">Questions de présélection</span>
          {hasContent && (
            <span className="text-xs bg-gray-200 text-gray-600 px-2 py-0.5 rounded font-medium">
              Configurées
            </span>
          )}
        </div>
        {open
          ? <ChevronUp size={13} className="text-gray-400" />
          : <ChevronDown size={13} className="text-gray-400" />
        }
      </button>

      {open && (
        <div className="p-4 space-y-5 bg-white border-t border-gray-100">

          <div>
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
              Niveau de diplôme minimum
            </label>
            <select
              value={value.min_degree}
              onChange={(e) => update({ min_degree: e.target.value })}
              className="w-full h-9 px-3 rounded-lg border border-gray-200 bg-white text-xs text-gray-700 outline-none focus:border-gray-400"
            >
              {DEGREE_OPTIONS.map((d) => (
                <option key={d.value} value={d.value}>{d.label}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
              Années d'expérience minimum
            </label>
            <div className="flex items-center gap-3">
              <input
                type="range" min={0} max={15} step={1}
                value={value.min_experience_years}
                onChange={(e) => update({ min_experience_years: Number(e.target.value) })}
                className="flex-1"
              />
              <span className="text-xs font-semibold text-gray-700 w-14 text-right tabular-nums shrink-0">
                {value.min_experience_years === 0 ? "Aucun" : `${value.min_experience_years} an${value.min_experience_years > 1 ? "s" : ""}`}
              </span>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
              Diplôme ou Certifications requises
            </label>
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                value={certInput}
                onChange={(e) => setCertInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addCert())}
                placeholder="ex. PMP, TOEIC 900, Bac+5 Informatique…"
                className="flex-1 h-9 px-3 rounded-lg border border-gray-200 bg-white text-xs outline-none focus:border-gray-400 placeholder:text-gray-300"
              />
              <button
                type="button"
                onClick={addCert}
                className="h-9 px-3 rounded-lg bg-gray-900 hover:bg-gray-700 text-white text-xs font-medium transition-colors"
              >
                Ajouter
              </button>
            </div>
            {value.required_certifications.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {value.required_certifications.map((cert, idx) => (
                  <span
                    key={idx}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-gray-200 text-gray-600 text-xs bg-gray-50"
                  >
                    {cert}
                    <button
                      type="button"
                      onClick={() => removeCert(idx)}
                      className="hover:text-red-500 transition-colors ml-0.5"
                    >
                      <X size={9} />
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                Questions personnalisées
              </label>
              <button
                type="button"
                onClick={addQuestion}
                className="text-xs text-gray-500 hover:text-gray-900 font-medium flex items-center gap-1 transition-colors"
              >
                <Plus size={11} /> Ajouter
              </button>
            </div>
            {value.custom_questions.length === 0 ? (
              <p className="text-xs text-gray-400">Aucune question.</p>
            ) : (
              <div className="space-y-2">
                {value.custom_questions.map((q, idx) => (
                  <div
                    key={q.id}
                    className="flex items-start gap-2 p-3 rounded-lg border border-gray-100 bg-gray-50"
                  >
                    <span className="text-xs text-gray-300 pt-1.5 w-4 shrink-0 tabular-nums">{idx + 1}.</span>
                    <div className="flex-1 space-y-1.5">
                      <input
                        type="text"
                        value={q.text}
                        onChange={(e) => updateQuestion(q.id, { text: e.target.value })}
                        placeholder="ex. Êtes-vous autorisé à travailler en France ?"
                        className="w-full h-8 px-2.5 rounded border border-gray-200 bg-white text-xs outline-none focus:border-gray-400 placeholder:text-gray-300"
                      />
                      <label className="flex items-center gap-1.5 text-xs text-gray-500 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={q.required}
                          onChange={(e) => updateQuestion(q.id, { required: e.target.checked })}
                          className="rounded"
                        />
                        Réponse obligatoire
                      </label>
                    </div>
                    <button
                      type="button"
                      onClick={() => removeQuestion(q.id)}
                      className="p-1 text-gray-300 hover:text-red-500 transition-colors mt-1"
                    >
                      <X size={12} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Job Form ─────────────────────────────────────────────────────────────────

function JobForm({ initial = {}, onSubmit, onCancel, isPending }) {
  const [title,        setTitle]        = useState(initial.title        ?? "");
  const [description,  setDescription]  = useState(initial.description  ?? "");
  const [requirements, setRequirements] = useState(initial.requirements ?? "");
  const [domain,       setDomain]       = useState(initial.domain       ?? "");
  const [screening,    setScreening]    = useState(initial.screening_questions ?? EMPTY_SCREENING);

  function handleSubmit() {
    const trimmed = {
      title: title.trim(),
      description: description.trim(),
      requirements: requirements.trim(),
      domain: domain || null,
      screening_questions: screening,
    };
    if (!trimmed.title) return;
    onSubmit(trimmed);
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-gray-900">
          {initial.id ? "Modifier le poste" : "Nouveau poste"}
        </h3>
        <p className="text-xs text-gray-400 mt-0.5">Renseignez les détails du poste</p>
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
          Titre du poste
        </label>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
          placeholder="ex. Responsable d'Achats & Supply Chain"
          className="w-full h-9 px-3 rounded-lg border border-gray-200 bg-white text-sm outline-none focus:border-gray-400 focus:ring-2 focus:ring-gray-100 placeholder:text-gray-300 transition-colors"
        />
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
          Secteur d'activité
          <span className="text-red-400 ml-1 normal-case">(requis pour le scoring IA)</span>
        </label>
        <select
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
          className="w-full h-9 px-3 rounded-lg border border-gray-200 bg-white text-sm text-gray-700 outline-none focus:border-gray-400 transition-colors"
        >
          <option value="">Sélectionner un secteur…</option>
          {JOB_DOMAINS.map((d) => (
            <option key={d.value} value={d.value}>{d.label}</option>
          ))}
        </select>
        <p className="text-xs text-gray-400 mt-1">
          Seuls les CVs du même secteur seront scorés pour ce poste.
        </p>
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
          Description
        </label>
        <textarea
          rows={3}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Décrivez le rôle…"
          className="w-full px-3 py-2.5 rounded-lg border border-gray-200 bg-white text-sm resize-none outline-none focus:border-gray-400 focus:ring-2 focus:ring-gray-100 placeholder:text-gray-300 transition-colors"
        />
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
          Exigences
        </label>
        <textarea
          rows={3}
          value={requirements}
          onChange={(e) => setRequirements(e.target.value)}
          placeholder="Listez les exigences du poste…"
          className="w-full px-3 py-2.5 rounded-lg border border-gray-200 bg-white text-sm resize-none outline-none focus:border-gray-400 focus:ring-2 focus:ring-gray-100 placeholder:text-gray-300 transition-colors"
        />
        <p className="text-xs text-gray-400 mt-1">Utilisé pour le scoring IA des candidats.</p>
      </div>

      <ScreeningBuilder value={screening} onChange={setScreening} />

      <div className="flex items-center justify-end gap-2 pt-1">
        <button
          onClick={onCancel}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg border border-gray-200 bg-white text-xs font-medium text-gray-600 hover:bg-gray-50 transition-colors"
        >
          <X size={13} /> Annuler
        </button>
        <button
          disabled={!title.trim() || isPending}
          onClick={handleSubmit}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-gray-900 hover:bg-gray-700 text-white text-xs font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Check size={13} />
          {isPending ? "Sauvegarde…" : "Sauvegarder"}
        </button>
      </div>
    </div>
  );
}

// ─── Screening Summary ────────────────────────────────────────────────────────

function ScreeningSummary({ sq }) {
  if (!sq) return null;
  const chips = [];

  if (sq.min_degree && sq.min_degree !== "none") {
    const d = DEGREE_OPTIONS.find((o) => o.value === sq.min_degree);
    chips.push({ key: "deg", label: d?.label });
  }
  if (sq.min_experience_years > 0) {
    chips.push({ key: "exp", label: `${sq.min_experience_years} an${sq.min_experience_years > 1 ? "s" : ""} exp.` });
  }
  (sq.required_certifications ?? []).forEach((c, i) => {
    chips.push({ key: `cert-${i}`, label: c });
  });
  if ((sq.custom_questions ?? []).length > 0) {
    chips.push({ key: "q", label: `${sq.custom_questions.length} question${sq.custom_questions.length > 1 ? "s" : ""}` });
  }

  if (chips.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5 mt-3">
      {chips.map((c) => (
        <span key={c.key} className="text-xs px-2 py-0.5 rounded border border-gray-200 text-gray-500 bg-gray-50">
          {c.label}
        </span>
      ))}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function JobList() {
  const navigate = useNavigate();

  const { data: jobs = [], isLoading, status, error } = useJobs();
  console.log("useJobs →", { status, jobsCount: jobs.length, error });

  const { mutate: createJob, isPending: isCreating } = useCreateJob({ onSuccess: () => setShowCreate(false) });
  const { mutate: updateJob, isPending: isUpdating } = useUpdateJob({ onSuccess: () => setEditingId(null) });
  const { mutate: deleteJob }                        = useDeleteJob();
  // const { data: candidates = [] }                    = useCandidates();

  const [showCreate,    setShowCreate]    = useState(false);
  const [editingId,     setEditingId]     = useState(null);
  const [deleteTarget,  setDeleteTarget]  = useState(null); // { id, title }

  // function candidateCount(jobId) {
  //   return candidates.filter((c) => c.job_id === jobId).length;
  // }

  return (
    <div className="p-6 lg:p-8 bg-gray-50 min-h-screen">

      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4 mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Postes</h1>
          <p className="text-sm text-gray-400 mt-0.5">
            {jobs.length} poste{jobs.length !== 1 ? "s" : ""} actif{jobs.length !== 1 ? "s" : ""}
          </p>
        </div>
        <button
          onClick={() => { setEditingId(null); setShowCreate(true); }}
          className="flex items-center gap-2 rounded-lg bg-gray-900 hover:bg-gray-700 px-3 py-1.5 text-xs font-medium text-white transition-colors self-start"
        >
          <Plus size={13} />
          Nouveau poste
        </button>
      </div>

      {/* Create form */}
      {showCreate && (
        <div className="mb-5">
          <JobForm
            isPending={isCreating}
            onCancel={() => setShowCreate(false)}
            onSubmit={(data) => createJob(data)}
          />
        </div>
      )}

      {/* Loading */}
      {isLoading ? (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
          <p className="text-sm text-gray-400">Chargement…</p>
        </div>

      /* Empty state */
      ) : jobs.length === 0 && !showCreate ? (
        <div className="bg-white rounded-xl border border-dashed border-gray-300 p-16 text-center">
          <p className="text-sm font-medium text-gray-700">Aucun poste disponible</p>
          <p className="text-xs text-gray-400 mt-1 mb-5">Créez votre premier poste pour commencer le recrutement.</p>
          <button
            onClick={() => setShowCreate(true)}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-gray-900 hover:bg-gray-700 text-white text-xs font-medium transition-colors"
          >
            <Plus size={13} /> Nouveau poste
          </button>
        </div>

      /* Job grid */
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {jobs.map((job) =>
            editingId === job.id ? (
              <JobForm
                key={job.id}
                initial={job}
                isPending={isUpdating}
                onCancel={() => setEditingId(null)}
                onSubmit={(data) => updateJob({ id: job.id, ...data })}
              />
            ) : (
              <div
                key={job.id}
                className="bg-white rounded-xl border border-gray-200 p-5 hover:border-gray-300 hover:shadow-sm transition-all"
              >
                {/* Card header */}
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <h3 className="text-sm font-semibold text-gray-900 truncate">{job.title}</h3>
                    <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                      <span className="text-xs text-gray-400 tabular-nums">
                        {job.candidate_count ?? 0} candidat{(job.candidate_count ?? 0) !== 1 ? "s" : ""}
                      </span>
                      {job.domain && (
                        <>
                          <span className="text-gray-200">·</span>
                          <span className="text-xs text-gray-400">
                            {JOB_DOMAINS.find((d) => d.value === job.domain)?.label ?? job.domain}
                          </span>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      onClick={() => navigate(`/candidates?job=${job.id}`)}
                      className="p-1.5 rounded text-gray-300 hover:text-gray-700 hover:bg-gray-100 transition-colors"
                      title="Voir les candidats"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>
                        <path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
                      </svg>
                    </button>
                    <button
                      onClick={() => { setShowCreate(false); setEditingId(job.id); }}
                      className="p-1.5 rounded text-gray-300 hover:text-gray-700 hover:bg-gray-100 transition-colors"
                    >
                      <Pencil size={13} />
                    </button>
                    <button
                      onClick={() => setDeleteTarget({ id: job.id, title: job.title })}
                      className="p-1.5 rounded text-gray-300 hover:text-red-500 hover:bg-red-50 transition-colors"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>

                {/* Description */}
                {job.description && (
                  <p className="text-xs text-gray-500 mt-3 line-clamp-2 leading-relaxed">
                    {job.description}
                  </p>
                )}

                {/* Requirements */}
                {job.requirements && (
                  <div className="mt-3">
                    <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-1">Exigences</p>
                    <p className="text-xs text-gray-500 line-clamp-2">{job.requirements}</p>
                  </div>
                )}

                <ScreeningSummary sq={job.screening_questions} />

                {/* Footer */}
                <div className="mt-4 pt-3 border-t border-gray-100 flex items-center justify-between">
                  <button
                    onClick={() => navigate(`/candidates?job=${job.id}`)}
                    className="text-xs font-medium text-gray-500 hover:text-gray-900 transition-colors"
                  >
                    Voir les candidats →
                  </button>
                  <span className="text-xs text-gray-300 tabular-nums font-mono">
                    {job.id.slice(0, 8)}
                  </span>
                </div>
              </div>
            )
          )}
        </div>
      )}

      {/* Delete confirm modal */}
      {deleteTarget && (
        <ConfirmModal
          title="Supprimer ce poste ?"
          message={`Le poste "${deleteTarget.title}" sera supprimé définitivement. Cette action est irréversible.`}
          onConfirm={() => {
            deleteJob(deleteTarget.id);
            setDeleteTarget(null);
          }}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </div>
  );
}