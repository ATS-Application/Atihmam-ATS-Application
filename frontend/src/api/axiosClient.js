// frontend/src/api/axiosClient.js
import axios from "axios";
import { useAuthStore } from "../store/authStore";

const axiosClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  headers: { "Content-Type": "application/json" },
});

// Normalize trailing slashes before auth header is attached —
// prevents the 307 redirect that strips Authorization on redirect.
// axiosClient.interceptors.request.use((config) => {
//   const url = config.url ?? "";
//   const [path, query] = url.split("?");
//   if (path && !path.endsWith("/")) {
//     config.url = query ? `${path}/?${query}` : `${path}/`;
//   }
//   return config;
// });

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