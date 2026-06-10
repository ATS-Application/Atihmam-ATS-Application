// frontend/src/api/jobsApi.js
import axiosClient from "./axiosClient";

const unwrap = (promise) => promise.then((res) => res.data);

export const getJobs    = ()         => unwrap(axiosClient.get("/jobs"));
export const getJob     = (id)       => unwrap(axiosClient.get(`/jobs/${id}`));
export const createJob  = (data)     => unwrap(axiosClient.post("/jobs", data));
export const updateJob  = (id, data) => unwrap(axiosClient.patch(`/jobs/${id}`, data));
export const deleteJob  = (id)       => unwrap(axiosClient.delete(`/jobs/${id}`));