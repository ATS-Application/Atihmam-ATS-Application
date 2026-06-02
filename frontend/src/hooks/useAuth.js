// frontend/src/hooks/useAuth.js
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import { authApi, register, forgotPassword, resetPassword } from "../api/authApi";
import { useAuthStore } from "../store/authStore";

export function useLogin() {
  const setAuth = useAuthStore((s) => s.setAuth);
  const navigate = useNavigate();

  return useMutation({
    mutationFn: ({ email, password }) => authApi.login({ email, password }),
    onSuccess: (res) => {
      setAuth(res.data.access_token, null);
      navigate("/dashboard");
      toast.success("Connexion réussie");
    },
    onError: (err) => {
      toast.error(err.response?.data?.detail || "Identifiants incorrects");
    },
  });
}

export function useForgotPassword() {
  return useMutation({
    mutationFn: (email) => forgotPassword(email),
    onError: (err) => {
      toast.error(err.response?.data?.detail || "Une erreur est survenue");
    },
  });
}

export function useResetPassword() {
  const navigate = useNavigate();
  return useMutation({
    mutationFn: ({ access_token, new_password }) =>
      resetPassword(access_token, new_password),
    onSuccess: () => {
      toast.success("Mot de passe mis à jour. Veuillez vous reconnecter.");
      navigate("/login");
    },
    onError: (err) => {
      toast.error(err.response?.data?.detail || "Lien invalide ou expiré.");
    },
  });
}

export function useLogout() {
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();
  return () => {
    logout();
    navigate("/login");
    toast.success("Déconnecté");
  };
}
