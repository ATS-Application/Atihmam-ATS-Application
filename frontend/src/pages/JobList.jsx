import { useState } from "react";
import {
  Plus,
  Pencil,
  Trash2,
  X,
  Check,
  Users,
  Briefcase,
  Sparkles,
  ArrowRight,
} from "lucide-react";

import { useNavigate } from "react-router-dom";

import {
  useJobs,
  useCreateJob,
  useUpdateJob,
  useDeleteJob,
} from "../hooks/useJobs";

import { useCandidates } from "../hooks/useCandidates";

function JobForm({
  initial = {},
  onSubmit,
  onCancel,
  isPending,
}) {
  const [title, setTitle] = useState(
    initial.title ?? ""
  );

  const [description, setDescription] =
    useState(initial.description ?? "");

  const [requirements, setRequirements] =
    useState(initial.requirements ?? "");

  function handleSubmit() {
    const trimmed = {
      title: title.trim(),
      description: description.trim(),
      requirements: requirements.trim(),
    };

    if (!trimmed.title) return;

    onSubmit(trimmed);
  }

  return (
    <div
      className="
        rounded-3xl
        border border-indigo-200
        bg-white
        p-6
        shadow-lg
        space-y-4
      "
    >
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="p-3 rounded-2xl bg-indigo-100">
          <Briefcase
            size={18}
            className="text-indigo-600"
          />
        </div>

        <div>
          <h3 className="font-semibold text-gray-900">
            {initial.id
              ? "Modifier le poste"
              : "Créer un nouveau poste"}
          </h3>

          <p className="text-sm text-gray-500">
            Ajoutez les détails du poste
          </p>
        </div>
      </div>

      {/* Title */}
      <div>
        <label className="text-sm font-medium text-gray-700 mb-2 block">
          Titre du poste
        </label>

        <input
          type="text"
          value={title}
          onChange={(e) =>
            setTitle(e.target.value)
          }
          onKeyDown={(e) =>
            e.key === "Enter" &&
            handleSubmit()
          }
          placeholder="Frontend Developer..."
          className="
            w-full
            h-12
            px-4
            rounded-2xl
            border border-gray-200
            bg-white
            text-sm
            outline-none
            transition-all
            focus:ring-4 focus:ring-indigo-100
            focus:border-indigo-400
          "
        />
      </div>

      {/* Description */}
      <div>
        <label className="text-sm font-medium text-gray-700 mb-2 block">
          Description
        </label>

        <textarea
          rows={3}
          value={description}
          onChange={(e) =>
            setDescription(e.target.value)
          }
          placeholder="Décrivez le rôle..."
          className="
            w-full
            px-4 py-3
            rounded-2xl
            border border-gray-200
            bg-white
            text-sm
            resize-none
            outline-none
            transition-all
            focus:ring-4 focus:ring-indigo-100
            focus:border-indigo-400
          "
        />
      </div>

      {/* Requirements */}
      <div>
        <label className="text-sm font-medium text-gray-700 mb-2 block">
          Exigences
        </label>

        <textarea
          rows={4}
          value={requirements}
          onChange={(e) =>
            setRequirements(e.target.value)
          }
          placeholder="React, Node.js, PostgreSQL..."
          className="
            w-full
            px-4 py-3
            rounded-2xl
            border border-gray-200
            bg-white
            text-sm
            resize-none
            outline-none
            transition-all
            focus:ring-4 focus:ring-indigo-100
            focus:border-indigo-400
          "
        />

        <p className="text-xs text-gray-400 mt-2">
          Utilisé pour le scoring IA des
          candidats
        </p>
      </div>

      {/* Actions */}
      <div className="flex items-center justify-end gap-3 pt-2">
        <button
          onClick={onCancel}
          className="
            flex items-center gap-2
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
          <X size={16} />
          Annuler
        </button>

        <button
          disabled={
            !title.trim() || isPending
          }
          onClick={handleSubmit}
          className="
            flex items-center gap-2
            px-5 py-3
            rounded-2xl
            bg-linear-to-r
            from-indigo-600
            to-blue-600
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
          <Check size={16} />

          {isPending
            ? "Sauvegarde..."
            : "Sauvegarder"}
        </button>
      </div>
    </div>
  );
}

export default function JobList() {
  const navigate = useNavigate();

  const {
    data: jobs = [],
    isLoading,
  } = useJobs();

  const {
    mutate: createJob,
    isPending: isCreating,
  } = useCreateJob();

  const {
    mutate: updateJob,
    isPending: isUpdating,
  } = useUpdateJob();

  const { mutate: deleteJob } =
    useDeleteJob();

  const { data: candidates = [] } =
    useCandidates();

  const [showCreate, setShowCreate] =
    useState(false);

  const [editingId, setEditingId] =
    useState(null);

  function candidateCountForJob(jobId) {
    return candidates.filter(
      (c) => c.job_id === jobId
    ).length;
  }

  return (
    <div className="p-8 bg-gray-50 min-h-screen">
      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-5 mb-8">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <div className="p-2 rounded-xl bg-indigo-100">
              <Sparkles
                size={18}
                className="text-indigo-600"
              />
            </div>

            <span className="text-sm font-medium text-indigo-600">
              Recruitment Jobs
            </span>
          </div>

          <h1 className="text-4xl font-bold tracking-tight text-gray-900">
            Postes
          </h1>

          <p className="text-gray-500 mt-2 text-sm">
            {jobs.length} poste(s)
            actif(s)
          </p>
        </div>

        {/* Create Button */}
        <button
          onClick={() => {
            setEditingId(null);
            setShowCreate(true);
          }}
          className="
            group
            flex items-center gap-2
            px-5 py-3
            rounded-2xl
            bg-linear-to-r
            from-indigo-600
            to-blue-600
            text-white
            text-sm font-semibold
            shadow-md hover:shadow-xl
            transition-all duration-300
            hover:-translate-y-0.5
            active:scale-[0.98]
          "
        >
          <div className="p-1 rounded-lg bg-white/15">
            <Plus
              size={16}
              className="group-hover:rotate-90 transition-transform duration-300"
            />
          </div>

          Nouveau poste
        </button>
      </div>

      {/* Create Form */}
      {showCreate && (
        <div className="mb-6">
          <JobForm
            isPending={isCreating}
            onCancel={() =>
              setShowCreate(false)
            }
            onSubmit={(data) =>
              createJob(data, {
                onSuccess: () =>
                  setShowCreate(false),
              })
            }
          />
        </div>
      )}

      {/* Loading */}
      {isLoading ? (
        <div className="rounded-3xl bg-white border border-gray-200 p-10 text-center shadow-sm">
          <p className="text-gray-400">
            Chargement...
          </p>
        </div>
      ) : jobs.length === 0 &&
        !showCreate ? (
        /* Empty State */
        <div className="rounded-3xl border border-dashed border-gray-300 bg-white p-14 text-center">
          <div className="w-16 h-16 rounded-3xl bg-indigo-100 flex items-center justify-center mx-auto mb-5">
            <Briefcase
              size={28}
              className="text-indigo-600"
            />
          </div>

          <h3 className="text-lg font-semibold text-gray-900">
            Aucun poste disponible
          </h3>

          <p className="text-sm text-gray-500 mt-2">
            Créez votre premier poste
            pour commencer le recrutement
          </p>

          <button
            onClick={() =>
              setShowCreate(true)
            }
            className="
              mt-6
              inline-flex items-center gap-2
              px-5 py-3
              rounded-2xl
              bg-indigo-600
              text-white
              text-sm font-medium
              hover:bg-indigo-700
              transition-colors
            "
          >
            <Plus size={16} />
            Nouveau poste
          </button>
        </div>
      ) : (
        /* Jobs Grid */
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {jobs.map((job) =>
            editingId === job.id ? (
              <JobForm
                key={job.id}
                initial={job}
                isPending={isUpdating}
                onCancel={() =>
                  setEditingId(null)
                }
                onSubmit={(data) =>
                  updateJob(
                    {
                      id: job.id,
                      ...data,
                    },
                    {
                      onSuccess: () =>
                        setEditingId(
                          null
                        ),
                    }
                  )
                }
              />
            ) : (
              <div
                key={job.id}
                className="
                  group
                  relative overflow-hidden
                  rounded-3xl
                  border border-gray-200
                  bg-white
                  p-6
                  shadow-sm
                  hover:shadow-xl
                  transition-all duration-300
                  hover:-translate-y-1
                "
              >
                {/* Glow */}
                <div className="absolute -top-10 -right-10 w-24 h-24 bg-indigo-400/10 rounded-full blur-3xl opacity-0 group-hover:opacity-100 transition-opacity duration-500" />

                <div className="relative">
                  {/* Top */}
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-3">
                        <div className="p-3 rounded-2xl bg-indigo-100">
                          <Briefcase
                            size={18}
                            className="text-indigo-600"
                          />
                        </div>

                        <div>
                          <h3 className="font-semibold text-gray-900">
                            {job.title}
                          </h3>

                          <div className="flex items-center gap-2 mt-1">
                            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-gray-100 text-gray-600 text-xs font-medium">
                              <Users size={11} />
                              {candidateCountForJob(
                                job.id
                              )}
                            </span>
                          </div>
                        </div>
                      </div>

                      {job.description && (
                        <p className="text-sm text-gray-500 mt-4 line-clamp-3">
                          {job.description}
                        </p>
                      )}

                      {job.requirements && (
                        <div className="mt-4">
                          <p className="text-xs font-medium text-gray-400 mb-2 uppercase tracking-wide">
                            Exigences
                          </p>

                          <p className="text-sm text-gray-600 line-clamp-2">
                            {
                              job.requirements
                            }
                          </p>
                        </div>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-1 shrink-0">
                      {/* Candidates */}
                      <button
                        title="Voir les candidats"
                        onClick={() =>
                          navigate(
                            `/candidates?job=${job.id}`
                          )
                        }
                        className="
                          p-2.5 rounded-xl
                          text-gray-400
                          hover:text-blue-600
                          hover:bg-blue-50
                          transition-colors
                        "
                      >
                        <Users size={16} />
                      </button>

                      {/* Edit */}
                      <button
                        onClick={() => {
                          setShowCreate(
                            false
                          );
                          setEditingId(
                            job.id
                          );
                        }}
                        className="
                          p-2.5 rounded-xl
                          text-gray-400
                          hover:text-indigo-600
                          hover:bg-indigo-50
                          transition-colors
                        "
                      >
                        <Pencil size={16} />
                      </button>

                      {/* Delete */}
                      <button
                        onClick={() => {
                          if (
                            confirm(
                              "Supprimer ce poste ?"
                            )
                          ) {
                            deleteJob(
                              job.id
                            );
                          }
                        }}
                        className="
                          p-2.5 rounded-xl
                          text-gray-400
                          hover:text-red-500
                          hover:bg-red-50
                          transition-colors
                        "
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </div>

                  {/* Footer */}
                  <div className="mt-6 pt-5 border-t border-gray-100 flex items-center justify-between">
                    <button
                      onClick={() =>
                        navigate(
                          `/candidates?job=${job.id}`
                        )
                      }
                      className="
                        inline-flex items-center gap-2
                        text-sm font-medium
                        text-indigo-600
                        hover:text-indigo-700
                        transition-colors
                      "
                    >
                      Voir les candidats
                      <ArrowRight
                        size={15}
                      />
                    </button>

                    <span className="text-xs text-gray-400">
                      ID:{" "}
                      {job.id.slice(
                        0,
                        8
                      )}
                    </span>
                  </div>
                </div>
              </div>
            )
          )}
        </div>
      )}
    </div>
  );
}