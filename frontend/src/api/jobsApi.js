// frontend/src/api/jobsApi.js
import axiosClient from "./axiosClient";

export const getJobs    = ()         => axiosClient.get("/jobs");
export const getJob     = (id)       => axiosClient.get(`/jobs/${id}`);
export const createJob  = (data)     => axiosClient.post("/jobs", data);
export const updateJob  = (id, data) => axiosClient.patch(`/jobs/${id}`, data);
export const deleteJob  = (id)       => axiosClient.delete(`/jobs/${id}`);