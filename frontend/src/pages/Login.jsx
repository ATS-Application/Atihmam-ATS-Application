import { useState } from "react";
import { useLogin } from "../hooks/useAuth";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  // FIX 12 — Surface auth errors to the user. The original form called
  // mutate() and silently swallowed failures — a wrong password showed
  // nothing. useLogin must expose an error state; wire it here.
  const { mutate, isPending, error } = useLogin();

  const handleSubmit = (e) => {
    e.preventDefault();
    // FIX 13 — Trim email before sending; trailing spaces in autofilled
    // email fields are a common cause of spurious "invalid credentials" errors.
    mutate({ email: email.trim(), password });
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="card w-full max-w-sm p-8">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-primary-600">ATS Platform</h1>
          <p className="text-sm text-gray-500 mt-1">Connectez-vous pour continuer</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="email"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Email
            </label>
            <input
              id="email"
              type="email"
              className="input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
              // FIX 14 — Disable autocomplete for the password manager to
              // fill correctly; "username" maps to email in most browsers.
              autoComplete="username"
            />
          </div>
          <div>
            <label
              htmlFor="password"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Mot de passe
            </label>
            <input
              id="password"
              type="password"
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
            />
          </div>

          {/* FIX 12 (continued) — Show error message below the fields */}
          {error && (
            <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">
              {error.message ?? "Identifiants incorrects. Veuillez réessayer."}
            </p>
          )}

          <button
            type="submit"
            className="btn-primary rounded-full text-sm w-full h-10 justify-center mt-2"
            disabled={isPending}
          >
            {isPending ? "Connexion..." : "Se connecter"}
          </button>
        </form>
      </div>
    </div>
  );
}