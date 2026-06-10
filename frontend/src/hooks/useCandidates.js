// src/hooks/useCandidates.js

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { useAuthStore } from "../store/authStore";

import axiosClient from "../api/axiosClient";
import {
  getCandidates,
  getCandidate,
  transitionStatus,
  deleteCandidate,
  uploadCV,
  triggerDriveSync,
} from "../api/candidatesApi";

// Processing statuses that mean "still in flight" — poll until we leave these.
const PENDING_STATUSES = new Set(["queued", "processing"]);

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
  const isHydrated = useAuthStore((state) => state._hydrated);
  return useQuery({
    queryKey: ["candidate", id],

    queryFn: async () => {
      const res = await getCandidate(id);
      return res.data;
    },

    enabled: !!id && isHydrated,
    staleTime: 1000 * 30,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useCandidateWithPolling(id, { pollUntilScored = false } = {}) {
  return useQuery({
    queryKey: ["candidate", id],

    queryFn: async () => {
      const res = await getCandidate(id);
      return res.data;
    },

    enabled: !!id && isHydrated,

    refetchInterval: (query) => {
      if (!pollUntilScored) return false;

      const candidate = query.state.data;

      // No data yet — poll to get the initial state.
      if (!candidate) return 3000;

      // processing_status is the authoritative signal.
      // Stop once we've left a pending state (completed, failed, done, or null).
      if (PENDING_STATUSES.has(candidate.processing_status)) return 3000;

      return false;
    },

    refetchIntervalInBackground: false,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useDeleteAllCandidates() {
  const queryClient = useQueryClient();

  return useMutation({
    // Fix: was referencing undefined `api` — use axiosClient directly.
    mutationFn: () => axiosClient.delete("/candidates"),

    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["candidates"] });
    },

    onError: () => {
      toast.error("Erreur lors de la suppression");
    },
  });
}

export function useTransitionStatus() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({ id, new_status, note }) =>
      transitionStatus(id, new_status, note),

    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: ["candidates"] });
      qc.invalidateQueries({ queryKey: ["candidate", id] });
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
    mutationFn: deleteCandidate,

    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["candidates"] });
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
    mutationFn: ({ file, job_id }) => uploadCV(file, job_id),

    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["candidates"] });
      toast.success("CV uploadé — traitement en cours");
    },

    onError: (err) => {
      toast.error(
        err.response?.data?.detail || "Échec de l'upload"
      );
    },
  });
}

export function useDriveSync() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: triggerDriveSync,

    onSuccess: () => {
      toast.success("Synchronisation Drive lancée");
      // Invalidate immediately — new candidates appear as stubs right away.
      // Individual polling hooks handle live score updates from there.
      qc.invalidateQueries({ queryKey: ["candidates"] });
    },

    onError: () => {
      toast.error("Échec de la synchronisation Drive");
    },
  });
}