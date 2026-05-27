// frontend/src/pages/Login.jsx
import { useState } from "react";
import { useLogin } from "../hooks/useAuth";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const { mutate, isPending, error } = useLogin();

  const handleSubmit = (e) => {
    e.preventDefault();
    mutate({ email: email.trim(), password });
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm">

        {/* Logo card */}
        <div className="flex flex-col items-center mb-8">
          <img
            src="./src/assets/atihmam_logo.png"
            alt="Atihmam Conseils"
            className="h-14 w-auto object-contain"
            draggable={false}
          />
          <p className="text-xs text-gray-400 mt-3 tracking-widest uppercase">
            Plateforme ATS
          </p>
        </div>

        {/* Form card */}
        <div className="bg-white rounded-xl border border-gray-200 p-8 shadow-sm">
          <h1 className="text-sm font-semibold text-gray-900 mb-1">Connexion</h1>
          <p className="text-xs text-gray-400 mb-6">
            Connectez-vous pour accéder au tableau de bord.
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="email"
                className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5"
              >
                Email
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus
                autoComplete="username"
                className="w-full h-10 px-3 rounded-lg border border-gray-200 bg-white text-sm text-gray-900 outline-none transition-colors focus:border-gray-400 focus:ring-2 focus:ring-gray-100 placeholder:text-gray-300"
                placeholder="vous@exemple.com"
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5"
              >
                Mot de passe
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                className="w-full h-10 px-3 rounded-lg border border-gray-200 bg-white text-sm text-gray-900 outline-none transition-colors focus:border-gray-400 focus:ring-2 focus:ring-gray-100 placeholder:text-gray-300"
                placeholder="••••••••"
              />
            </div>

            {error && (
              <p className="text-xs text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
                {error.message ?? "Identifiants incorrects. Veuillez réessayer."}
              </p>
            )}

            <button
              type="submit"
              disabled={isPending}
              className="w-full h-10 rounded-lg bg-orange-500 hover:bg-orange-600 text-white text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed mt-2"
            >
              {isPending ? "Connexion…" : "Se connecter"}
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-gray-300 mt-6">
          © {new Date().getFullYear()} Atihmam Conseils
        </p>
      </div>
    </div>
  );
}