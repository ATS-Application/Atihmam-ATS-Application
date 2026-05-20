import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import {
  getCandidates,
  getCandidate,
  transitionStatus,
  deleteCandidate,
  uploadCV,
  triggerDriveSync,
} from "../api/candidatesApi";

export function useCandidates(filters = {}) {
  return useQuery({
    queryKey: ["candidates", filters],
    queryFn: () => getCandidates(filters).then((r) => r.data),
  });
}

export function useCandidate(id) {
  return useQuery({
    queryKey: ["candidates", id],
    queryFn: () => getCandidate(id).then((r) => r.data),
    enabled: !!id,
  });
}

export function useTransitionStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, new_status, note }) => transitionStatus(id, new_status, note),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: ["candidates"] });
      toast.success("Statut mis à jour");
    },
    onError: (err) => {
      toast.error(err.response?.data?.detail || "Transition non autorisée");
    },
  });
}

export function useDeleteCandidate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => deleteCandidate(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["candidates"] });
      toast.success("Candidat supprimé");
    },
  });
}

export function useUploadCV() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ file, job_id }) => uploadCV(file, job_id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["candidates"] });
      toast.success("CV uploadé — traitement en cours");
    },
    onError: () => toast.error("Échec de l'upload"),
  });
}

export function useDriveSync() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (job_id) => triggerDriveSync(job_id),
    onSuccess: () => {
      toast.success("Synchronisation Drive lancée");
      setTimeout(() => qc.invalidateQueries({ queryKey: ["candidates"] }), 3000);
    },
    onError: () => toast.error("Échec de la synchronisation Drive"),
  });
}