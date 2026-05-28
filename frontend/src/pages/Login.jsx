import { useState } from "react";
import { useLogin, useForgotPassword } from "../hooks/useAuth";

// ─── Sub-views ────────────────────────────────────────────────

function LoginForm({ onForgotPassword }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const { mutate, isPending, error } = useLogin();

  const handleSubmit = (e) => {
    e.preventDefault();
    mutate({ email: email.trim(), password });
  };

  return (
    <>
      <h1 className="text-sm font-semibold text-gray-900 mb-1">Connexion</h1>
      <p className="text-xs text-gray-400 mb-6">
        Connectez-vous pour accéder au tableau de bord.
      </p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="email" className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
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
          <div className="flex items-center justify-between mb-1.5">
            <label htmlFor="password" className="block text-xs font-medium text-gray-500 uppercase tracking-wide">
              Mot de passe
            </label>
            <button
              type="button"
              onClick={onForgotPassword}
              className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
            >
              Mot de passe oublié ?
            </button>
          </div>
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
    </>
  );
}

function ForgotPasswordForm({ onBack, onSuccess }) {
  const [email, setEmail] = useState("");
  const { mutate, isPending, error } = useForgotPassword();

  const handleSubmit = (e) => {
    e.preventDefault();
    mutate(email.trim(), { onSuccess });
  };

  return (
    <>
      <h1 className="text-sm font-semibold text-gray-900 mb-1">
        Réinitialisation
      </h1>
      <p className="text-xs text-gray-400 mb-6">
        Entrez votre adresse email pour recevoir un lien de réinitialisation.
      </p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="reset-email" className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
            Email
          </label>
          <input
            id="reset-email"
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

        {error && (
          <p className="text-xs text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
            {error.message ?? "Une erreur est survenue. Veuillez réessayer."}
          </p>
        )}

        <button
          type="submit"
          disabled={isPending}
          className="w-full h-10 rounded-lg bg-orange-500 hover:bg-orange-600 text-white text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed mt-2"
        >
          {isPending ? "Envoi…" : "Envoyer le lien"}
        </button>

        <button
          type="button"
          onClick={onBack}
          className="w-full h-10 text-xs text-gray-400 hover:text-gray-600 transition-colors"
        >
          ← Retour à la connexion
        </button>
      </form>
    </>
  );
}

function ResetEmailSent({ onBack }) {
  return (
    <div className="text-center py-4">
      <div className="w-12 h-12 rounded-full bg-green-50 border border-green-100 flex items-center justify-center mx-auto mb-4">
        <svg className="w-5 h-5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
        </svg>
      </div>
      <h2 className="text-sm font-semibold text-gray-900 mb-2">Email envoyé</h2>
      <p className="text-xs text-gray-400 leading-relaxed mb-6">
        Si cette adresse est associée à un compte, vous recevrez un lien de
        réinitialisation sous quelques minutes.
      </p>
      <button
        type="button"
        onClick={onBack}
        className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
      >
        ← Retour à la connexion
      </button>
    </div>
  );
}

// ─── Root ─────────────────────────────────────────────────────

export default function Login() {
  const [view, setView] = useState("login");

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm">

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

        <div className="bg-white rounded-xl border border-gray-200 p-8 shadow-sm">
          {view === "login" && (
            <LoginForm onForgotPassword={() => setView("forgot")} />
          )}
          {view === "forgot" && (
            <ForgotPasswordForm
              onBack={() => setView("login")}
              onSuccess={() => setView("sent")}
            />
          )}
          {view === "sent" && (
            <ResetEmailSent onBack={() => setView("login")} />
          )}
        </div>

        <p className="text-center text-xs text-gray-300 mt-6">
          © {new Date().getFullYear()} Atihmam Conseils
        </p>
      </div>
    </div>
  );
}