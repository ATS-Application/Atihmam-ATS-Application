import { useState } from "react";
import { Plus, Pencil, Trash2, X, Check } from "lucide-react";
import { useJobs, useCreateJob, useUpdateJob, useDeleteJob } from "../hooks/useJobs";

function JobForm({ initial = {}, onSubmit, onCancel, isPending }) {
  const [title, setTitle] = useState(initial.title ?? "");
  const [description, setDescription] = useState(initial.description ?? "");
  const [requirements, setRequirements] = useState(initial.requirements ?? "");

  return (
    <div className="card p-5 border-primary-200 border space-y-3">
      <input
        className="input"
        placeholder="Titre du poste *"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />
      <textarea
        className="input resize-none"
        rows={2}
        placeholder="Description"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />
      <textarea
        className="input resize-none"
        rows={3}
        placeholder="Exigences (utilisées pour le scoring IA)"
        value={requirements}
        onChange={(e) => setRequirements(e.target.value)}
      />
      <div className="flex gap-2 justify-end">
        <button className="btn-secondary" onClick={onCancel}>
          <X size={15} /> Annuler
        </button>
        <button
          className="btn-primary"
          disabled={!title || isPending}
          onClick={() => onSubmit({ title, description, requirements })}
        >
          <Check size={15} />
          {isPending ? "Sauvegarde..." : "Sauvegarder"}
        </button>
      </div>
    </div>
  );
}

export default function JobList() {
  const { data: jobs = [], isLoading } = useJobs();
  const { mutate: createJob, isPending: isCreating } = useCreateJob();
  const { mutate: updateJob, isPending: isUpdating } = useUpdateJob();
  const { mutate: deleteJob } = useDeleteJob();

  const [showCreate, setShowCreate] = useState(false);
  const [editingId, setEditingId] = useState(null);

  return (
    <div className="p-8 max-w-3xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Postes</h1>
          <p className="text-gray-500 text-sm mt-1">{jobs.length} poste(s) actif(s)</p>
        </div>
        <button className="btn-primary" onClick={() => setShowCreate(true)}>
          <Plus size={16} /> Nouveau poste
        </button>
      </div>

      <div className="space-y-4">
        {showCreate && (
          <JobForm
            onCancel={() => setShowCreate(false)}
            isPending={isCreating}
            onSubmit={(data) =>
              createJob(data, { onSuccess: () => setShowCreate(false) })
            }
          />
        )}

        {isLoading ? (
          <p className="text-gray-400 text-sm">Chargement...</p>
        ) : jobs.length === 0 && !showCreate ? (
          <div className="card p-10 text-center">
            <p className="text-gray-400 text-sm">Aucun poste. Créez-en un.</p>
          </div>
        ) : (
          jobs.map((job) =>
            editingId === job.id ? (
              <JobForm
                key={job.id}
                initial={job}
                isPending={isUpdating}
                onCancel={() => setEditingId(null)}
                onSubmit={(data) =>
                  updateJob({ id: job.id, ...data }, { onSuccess: () => setEditingId(null) })
                }
              />
            ) : (
              <div key={job.id} className="card p-5">
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-gray-900">{job.title}</h3>
                    {job.description && (
                      <p className="text-sm text-gray-500 mt-1 line-clamp-2">{job.description}</p>
                    )}
                    {job.requirements && (
                      <p className="text-xs text-gray-400 mt-1 line-clamp-1">
                        Exigences : {job.requirements}
                      </p>
                    )}
                  </div>
                  <div className="flex gap-1 ml-4 flex-shrink-0">
                    <button
                      onClick={() => setEditingId(job.id)}
                      className="p-1.5 text-gray-400 hover:text-primary-600 hover:bg-primary-50 rounded transition-colors"
                    >
                      <Pencil size={15} />
                    </button>
                    <button
                      onClick={() => {
                        if (confirm("Supprimer ce poste ?")) deleteJob(job.id);
                      }}
                      className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded transition-colors"
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </div>
              </div>
            )
          )
        )}
      </div>
    </div>
  );
}