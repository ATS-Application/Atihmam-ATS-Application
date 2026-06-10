// src/store/authStore.js
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { jwtDecode } from "jwt-decode";
import axiosClient from "../api/axiosClient"; // ← import statique direct

const decodeUser = (token) => {
  try {
    const { sub, email, full_name, role } = jwtDecode(token);
    return { id: sub, email, full_name, role };
  } catch {
    return null;
  }
};

export const useAuthStore = create(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      _hydrated: false,

      login: ({ access_token }) => {
        const user = decodeUser(access_token);
        set({ token: access_token, user });
      },

      fetchUser: async () => {
        const { token, logout } = get();
        if (!token) return;
        try {
          const { default: axiosClient } = await import("../api/axiosClient");
          const res = await axiosClient.get("/auth/me");
          set({ user: res.data });
        } catch {
          logout();
        }
      },

      setAuth: (token, user) => set({ token, user }),

      logout: () => set({ token: null, user: null, _hydrated: false }),
    }),
    {
      name: "ats-auth",
      partialize: (state) => ({ token: state.token }),

      onRehydrateStorage: () => (state, error) => {
        if (error || !state?.token) {
          useAuthStore.setState({ _hydrated: true });
          return;
        }
        const user = decodeUser(state.token);
        if (user) {
          useAuthStore.setState({ user, _hydrated: true });
          setTimeout(() => useAuthStore.getState().fetchUser(), 0);
        } else {
          useAuthStore.setState({ token: null, user: null, _hydrated: true });
        }
      },
    }
  )
);

setTimeout(() => {
  if (!useAuthStore.getState()._hydrated) {
    const token = useAuthStore.getState().token;
    const user = token ? decodeUser(token) : null;
    useAuthStore.setState({ user: user ?? null, _hydrated: true });
  }
}, 500);
