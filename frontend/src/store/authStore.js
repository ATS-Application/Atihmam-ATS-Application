// src/store/authStore.js
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { jwtDecode } from "jwt-decode";

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

      // Called after successful /auth/login response
      // Decodes JWT immediately — no extra round-trip needed
      login: ({ access_token }) => {
        const user = decodeUser(access_token);
        set({ token: access_token, user });
      },

      // Called on page reload via onRehydrateStorage to verify
      // the persisted token is still valid server-side
      fetchUser: async () => {
        const { token, logout } = get();
        if (!token) return;
        try {
          // Lazy import avoids circular dependency (axiosClient → authStore → axiosClient)
          const { default: axiosClient } = await import("../api/axiosClient");
          const res = await axiosClient.get("/auth/me/");
          set({ user: res.data });
        } catch {
          logout();
        }
      },

      // Kept for backward compatibility with any existing callsites
      setAuth: (token, user) => set({ token, user }),

      logout: () => set({ token: null, user: null }),
    }),
    {
      name: "ats-auth",
      // Only persist the token — user is derived from it
      partialize: (state) => ({ token: state.token }),
      onRehydrateStorage: () => (state) => {
        if (!state?.token) return;

        // Optimistic decode: populate user synchronously from the persisted
        // token so there's no flash of unauthenticated UI on reload
        const user = decodeUser(state.token);
        if (user) {
          state.user = user;
          // Then verify server-side asynchronously; logout() if token is expired
          setTimeout(() => state.fetchUser(), 0);
        } else {
          // Token is malformed — clear it immediately
          state.token = null;
        }
      },
    }
  )
);