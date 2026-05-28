// frontend/src/api/authApi.js
import axiosClient from "./axiosClient";

export const login = (email, password) =>
  axiosClient.post("/auth/login", { email, password });

export const register = (email, password, full_name) =>
  axiosClient.post("/auth/register", { email, password, full_name });

export const forgotPassword = (email) =>
  axiosClient.post("/auth/forgot-password", { email });

export const resetPassword = (access_token, new_password) =>
  axiosClient.post("/auth/reset-password", { access_token, new_password });