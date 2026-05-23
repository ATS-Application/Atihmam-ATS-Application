// src/hooks/useCandidates.js

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

    queryFn: async () => {
      const res = await getCandidates(filters);
      return res.data;
    },

    staleTime: 1000 * 30,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useCandidate(id) {
  return useQuery({
    queryKey: ["candidate", id],

    queryFn: async () => {
      const res = await getCandidate(id);
      return res.data;
    },

    enabled: !!id,

    staleTime: 1000 * 15,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useCandidateWithPolling(
  id,
  { pollUntilScored = false } = {}
) {
  return useQuery({
    queryKey: ["candidate", id],

    queryFn: async () => {
      const res = await getCandidate(id);
      return res.data;
    },

    enabled: !!id,

    refetchInterval: (query) => {
      if (!pollUntilScored) {
        return false;
      }

      const candidate = query.state.data;

      if (!candidate) {
        return 3000;
      }

      // stop polling if completed
      if (
        candidate.processing_status === "completed" ||
        candidate.processing_status === "failed"
      ) {
        return false;
      }

      // stop if score exists
      if (candidate.score !== null && candidate.score !== undefined) {
        return false;
      }

      // continue polling
      return 3000;
    },

    refetchIntervalInBackground: false,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useTransitionStatus() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({ id, new_status, note }) =>
      transitionStatus(id, new_status, note),

    onSuccess: (_, { id }) => {
      qc.invalidateQueries({
        queryKey: ["candidates"],
      });

      qc.invalidateQueries({
        queryKey: ["candidate", id],
      });

      toast.success("Statut mis à jour");
    },

    onError: (err) => {
      toast.error(
        err.response?.data?.detail ||
          "Transition non autorisée"
      );
    },
  });
}

export function useDeleteCandidate() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: deleteCandidate,

    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: ["candidates"],
      });

      toast.success("Candidat supprimé");
    },

    onError: () => {
      toast.error("Erreur suppression");
    },
  });
}

export function useUploadCV() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({ file, job_id }) =>
      uploadCV(file, job_id),

    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: ["candidates"],
      });

      toast.success(
        "CV uploadé — traitement en cours"
      );
    },

    onError: () => {
      toast.error("Échec de l'upload");
    },
  });
}

export function useDriveSync() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: triggerDriveSync,

    onSuccess: () => {
      toast.success(
        "Synchronisation Drive lancée"
      );

      setTimeout(() => {
        qc.invalidateQueries({
          queryKey: ["candidates"],
        });
      }, 3000);
    },

    onError: () => {
      toast.error(
        "Échec de la synchronisation Drive"
      );
    },
  });
}