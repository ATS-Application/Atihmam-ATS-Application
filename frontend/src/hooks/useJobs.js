// frontend/src/hooks/useJobs.js
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { useAuthStore } from "../store/authStore";
import { getJobs, createJob, updateJob, deleteJob } from "../api/jobsApi";

export function useJobs() {
  const isHydrated = useAuthStore((state) => state._hydrated);
  return useQuery({
    queryKey: ["jobs"],
    queryFn: () => getJobs().then((r) => r.data),
    enabled: isHydrated,
  });
}

export function useCreateJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data) => createJob(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      toast.success("Poste créé");
    },
    onError: () => toast.error("Erreur lors de la création"),
  });
}

export function useUpdateJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }) => updateJob(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      toast.success("Poste mis à jour");
    },
  });
}

export function useDeleteJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => deleteJob(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      toast.success("Poste supprimé");
    },
  });
}