// frontend/src/api/authApi.js
import axiosClient from "./axiosClient";

/**
 * Normalize API responses
 */
const unwrap = (promise) =>
  promise
    .then((res) => res.data)
    .catch((error) => {
      const message =
        error?.response?.data?.detail ||
        error?.response?.data?.message ||
        error.message ||
        "Unexpected error occurred";

      throw new Error(message);
    });

/**
 * Auth API
 */
export const authApi = {
  login: ({ email, password }) => {
    return unwrap(
      axiosClient.post("/auth/login", { email, password })
    );
  },

  register: ({ email, password, full_name }) => {
    return unwrap(
      axiosClient.post("/auth/register", {
        email,
        password,
        full_name,
      })
    );
  },

  forgotPassword: ({ email }) => {
    return unwrap(
      axiosClient.post("/auth/forgot-password", { email })
    );
  },

  resetPassword: ({ access_token, new_password }) => {
    return unwrap(
      axiosClient.post("/auth/reset-password", {
        access_token,
        new_password,
      })
    );
  },
};