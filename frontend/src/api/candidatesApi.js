// frontend/src/api/candidatesApi.js

import axiosClient from "./axiosClient";

export const getCandidates = (params) =>
  axiosClient.get("/candidates", { params });

export const getCandidate = (id) =>
  axiosClient.get(`/candidates/${id}`);

export const getCandidateCVUrl = (id) =>
  axiosClient.get(`/candidates/${id}/cv-url`);

export const createCandidate = (data) =>
  axiosClient.post("/candidates", data);

export const updateCandidate = (id, data) =>
  axiosClient.patch(`/candidates/${id}`, data);

export const transitionStatus = (id, new_status, note) =>
  axiosClient.post(`/candidates/${id}/transition`, {
    new_status,
    note,
  });

export const deleteCandidate = (id) =>
  axiosClient.delete(`/candidates/${id}`);

export const uploadCV = async (file, job_id) => {
  const formData = new FormData();

  formData.append("file", file);

  if (job_id) {
    formData.append("job_id", job_id);
  }

  try {
    return await axiosClient.post(
      "/ingestion/upload",
      formData,
      {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      }
    );
  } catch (error) {
    throw error;
  }
};

export const triggerDriveSync = (job_id) =>
  axiosClient.post(
    "/ingestion/drive/sync",
    null,
    {
      params: { job_id },
    }
  );

export const getDriveSyncStatus = () =>
  axiosClient.get("/ingestion/drive/sync/status");

export const triggerDriveIngest = (job_id) =>
  axiosClient.post(
    "/ingestion/drive/ingest",
    null,
    {
      params: { job_id },
    }
  );

export const getDriveIngestStatus = () =>
  axiosClient.get("/ingestion/drive/ingest/status");

export const triggerAIProcessing = (job_id) =>
  axiosClient.post(
    "/ingestion/ai/process",
    null,
    {
      params: { job_id },
    }
  );

export const getAIProcessingStatus = () =>
  axiosClient.get("/ingestion/ai/status");
