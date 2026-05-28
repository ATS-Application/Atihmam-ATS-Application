import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useResetPassword } from "../hooks/useAuth";

function parseHashToken() {
  const hash = window.location.hash.slice(1); // strip leading #
  const params = new URLSearchParams(hash);
  return {
    access_token: params.get("access_token"),
    type: params.get("type"),
  };
}

export default function ResetPassword() {
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [tokenError, setTokenError] = useState(false);
  const [accessToken, setAccessToken] = useState(null);
  const [validationError, setValidationError] = useState("");
  const { mutate, isPending, error } = useResetPassword();

  useEffect(() => {
    const { access_token, type } = parseHashToken();
    if (!access_token || type !== "recovery") {
      setTokenError(true);
    } else {
      setAccessToken(access_token);
    }
  }, []);

  const handleSubmit = (e) => {
    e.preventDefault();
    setValidationError("");

    if (password.length < 8) {
      setValidationError("Le mot de passe doit contenir au moins 8 caractères.");
      return;
    }
    if (password !== confirm) {
      setValidationError("Les mots de passe ne correspondent pas.");
      return;
    }

    mutate({ access_token: accessToken, new_password: password });
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm">

        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <img
            src="/src/assets/atihmam_logo.png"
            alt="Atihmam Conseils"
            className="h-14 w-auto object-contain"
            draggable={false}
          />
          <p className="text-xs text-gray-400 mt-3 tracking-widest uppercase">
            Plateforme ATS
          </p>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-8 shadow-sm">

          {/* Invalid / expired token */}
          {tokenError ? (
            <div className="text-center py-4">
              <div className="w-12 h-12 rounded-full bg-red-50 border border-red-100 flex items-center justify-center mx-auto mb-4">
                <svg className="w-5 h-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                </svg>
              </div>
              <h2 className="text-sm font-semibold text-gray-900 mb-2">
                Lien invalide ou expiré
              </h2>
              <p className="text-xs text-gray-400 leading-relaxed mb-6">
                Ce lien de réinitialisation est invalide ou a expiré. Veuillez en demander un nouveau.
              </p>
              <button
                type="button"
                onClick={() => navigate("/login")}
                className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
              >
                ← Retour à la connexion
              </button>
            </div>
          ) : (

            /* Reset form */
            <>
              <h1 className="text-sm font-semibold text-gray-900 mb-1">
                Nouveau mot de passe
              </h1>
              <p className="text-xs text-gray-400 mb-6">
                Choisissez un mot de passe d'au moins 8 caractères.
              </p>

              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label
                    htmlFor="new-password"
                    className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5"
                  >
                    Nouveau mot de passe
                  </label>
                  <input
                    id="new-password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    autoFocus
                    autoComplete="new-password"
                    className="w-full h-10 px-3 rounded-lg border border-gray-200 bg-white text-sm text-gray-900 outline-none transition-colors focus:border-gray-400 focus:ring-2 focus:ring-gray-100 placeholder:text-gray-300"
                    placeholder="••••••••"
                  />
                </div>

                <div>
                  <label
                    htmlFor="confirm-password"
                    className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5"
                  >
                    Confirmer le mot de passe
                  </label>
                  <input
                    id="confirm-password"
                    type="password"
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    required
                    autoComplete="new-password"
                    className="w-full h-10 px-3 rounded-lg border border-gray-200 bg-white text-sm text-gray-900 outline-none transition-colors focus:border-gray-400 focus:ring-2 focus:ring-gray-100 placeholder:text-gray-300"
                    placeholder="••••••••"
                  />
                </div>

                {(validationError || error) && (
                  <p className="text-xs text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
                    {validationError || error.response?.data?.detail || "Une erreur est survenue."}
                  </p>
                )}

                <button
                  type="submit"
                  disabled={isPending || !accessToken}
                  className="w-full h-10 rounded-lg bg-orange-500 hover:bg-orange-600 text-white text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed mt-2"
                >
                  {isPending ? "Enregistrement…" : "Enregistrer le mot de passe"}
                </button>
              </form>
            </>
          )}
        </div>

        <p className="text-center text-xs text-gray-300 mt-6">
          © {new Date().getFullYear()} Atihmam Conseils
        </p>
      </div>
    </div>
  );
}