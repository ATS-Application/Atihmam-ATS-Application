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
  getDriveSyncStatus,
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
  return useQuery({
    queryKey: ["candidate", id],
    queryFn: async () => {
      const res = await getCandidate(id);
      return res.data;
    },
    enabled: !!id,         // ← remove isHydrated guard
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
    enabled: !!id,         // ← remove isHydrated guard
    refetchInterval: (query) => {
      if (!pollUntilScored) return false;
      const candidate = query.state.data;
      if (!candidate) return 3000;
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

    onSuccess: (response) => {
      const count = response?.data?.deleted;
      toast.success(
        count != null
          ? `${count} candidat(s) supprimé(s)`
          : "Tous les candidats ont été supprimés"
      );
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
    },
  });
}

export function useDriveSync() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: triggerDriveSync,

    onSuccess: () => {
      toast.success("Synchronisation démarrée en arrière-plan...", { duration: 4000 });
      qc.invalidateQueries({ queryKey: ["driveSyncStatus"] });
      qc.invalidateQueries({ queryKey: ["candidates"] });
    },

    onError: () => {
      toast.error("Échec de la synchronisation Drive");
    },
  });
}

export function useDriveSyncStatus(options = {}) {
  const isHydrated = useAuthStore((state) => state._hydrated);
  const token = useAuthStore((state) => state.token);

  return useQuery({
    queryKey: ["driveSyncStatus"],
    queryFn: async () => {
      try {
        const response = await getDriveSyncStatus();
        return response.data;
      } catch (err) {
        // If the endpoint doesn't exist yet on the deployed backend (404),
        // return null silently rather than throwing — this prevents
        // React Query from retrying and spamming the console.
        if (err?.response?.status === 404) return null;
        throw err;
      }
    },
    enabled: isHydrated && !!token,
    // Don't retry on errors — avoids hammering a 404 endpoint.
    retry: (failureCount, err) => {
      if (err?.response?.status === 404) return false;
      return failureCount < 2;
    },
    // Pause the polling interval when the query is in an error state.
    refetchInterval: (query) => {
      if (query.state.status === "error") return false;
      return options.refetchInterval ?? false;
    },
    ...options,
  });
}