// frontend/src/hooks/useJobs.js
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { useAuthStore } from "../store/authStore";
import { getJobs, createJob, updateJob, deleteJob } from "../api/jobsApi";

export function useJobs() {
  const isHydrated = useAuthStore((state) => state._hydrated);
  const token = useAuthStore((state) => state.token);
  console.log("useJobs enabled check →", { isHydrated, hasToken: !!token });
  return useQuery({
    queryKey: ["jobs"],
    queryFn: getJobs,   // ← just pass getJobs directly, no .then()
    enabled: isHydrated && !!token,
  });
}


export function useCreateJob({ onSuccess } = {}) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data) => createJob(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      toast.success("Poste créé");
      onSuccess?.();                          // call page-level callback here
    },
    onError: () => toast.error("Erreur lors de la création"),
  });
}

export function useUpdateJob({ onSuccess } = {}) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }) => updateJob(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      toast.success("Poste mis à jour");
      onSuccess?.();
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