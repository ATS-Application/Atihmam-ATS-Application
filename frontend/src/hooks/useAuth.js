import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import { login, register } from "../api/authApi";
import { useAuthStore } from "../store/authStore";

export function useLogin() {
  const setAuth = useAuthStore((s) => s.setAuth);
  const navigate = useNavigate();

  return useMutation({
    mutationFn: ({ email, password }) => login(email, password),
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

export function useLogout() {
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();
  return () => {
    logout();
    navigate("/login");
    toast.success("Déconnecté");
  };
}