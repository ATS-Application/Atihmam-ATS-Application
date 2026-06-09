// frontend/src/hooks/useAuth.js

import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";

import { authApi } from "../api/authApi";
import { useAuthStore } from "../store/authStore";

// ======================================================
// LOGIN
// ======================================================

export function useLogin() {
  const navigate = useNavigate();
  const login = useAuthStore((state) => state.login); // ← login, not setAuth

  return useMutation({
    mutationFn: ({ email, password }) => authApi.login({ email, password }),

    onSuccess: (data) => {
      if (!data?.access_token) {
        toast.error("Token d'authentification introuvable");
        return;
      }

      login(data); // ← decodes JWT internally, sets both token + user

      toast.success("Connexion réussie");
      navigate("/dashboard");
    },

    onError: (error) => {
      toast.error(error?.message || "Identifiants incorrects");
    },
  });
}

// ======================================================
// REGISTER
// ======================================================

export function useRegister() {
  const navigate = useNavigate();

  return useMutation({
    mutationFn: ({
      email,
      password,
      full_name,
    }) =>
      authApi.register({
        email,
        password,
        full_name,
      }),

    onSuccess: () => {
      toast.success(
        "Compte créé avec succès"
      );

      navigate("/login");
    },

    onError: (error) => {
      toast.error(
        error?.message ||
          "Impossible de créer le compte"
      );
    },
  });
}

// ======================================================
// FORGOT PASSWORD
// ======================================================

export function useForgotPassword() {
  return useMutation({
    mutationFn: ({ email }) =>
      authApi.forgotPassword({
        email,
      }),

    onSuccess: () => {
      toast.success(
        "Email de réinitialisation envoyé"
      );
    },

    onError: (error) => {
      toast.error(
        error?.message ||
          "Une erreur est survenue"
      );
    },
  });
}

// ======================================================
// RESET PASSWORD
// ======================================================

export function useResetPassword() {
  const navigate = useNavigate();

  return useMutation({
    mutationFn: ({
      access_token,
      new_password,
    }) =>
      authApi.resetPassword({
        access_token,
        new_password,
      }),

    onSuccess: () => {
      toast.success(
        "Mot de passe mis à jour"
      );

      navigate("/login");
    },

    onError: (error) => {
      toast.error(
        error?.message ||
          "Lien invalide ou expiré"
      );
    },
  });
}

// ======================================================
// LOGOUT
// ======================================================

export function useLogout() {
  const logout = useAuthStore(
    (state) => state.logout
  );

  const navigate = useNavigate();

  return () => {
    logout();

    toast.success("Déconnecté");

    navigate("/login");
  };
}