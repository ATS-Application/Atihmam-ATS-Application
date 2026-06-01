// frontend/src/api/axiosClient.js
import axios from "axios";
import { useAuthStore } from "../store/authStore";

const axiosClient = axios.create({
  // Use the environment variable, fallback to production URL if missing
  baseURL: import.meta.env.VITE_API_BASE_URL || "https://atihmam-ats-application.onrender.com/api/v1",
  headers: { "Content-Type": "application/json" },
});

// Attach JWT on every request
axiosClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Auto-logout on 401
axiosClient.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      useAuthStore.getState().logout();
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

export default axiosClient;