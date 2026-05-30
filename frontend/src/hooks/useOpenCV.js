// src/hooks/useOpenCV.js
import { useState, useCallback } from "react";
import { supabase } from "../lib/supabaseClient";

const BUCKET = "cvs";

/**
 * Extracts the storage path from a Supabase public URL or raw path.
 * Returns null if extraction fails.
 */
function extractBucketPath(value) {
  if (!value || typeof value !== "string") return null;
  try {
    if (!value.includes("http")) {
      return value.replace(/^\/+/, "").replace(/\?$/, "").trim();
    }
    const marker = `/storage/v1/object/public/${BUCKET}/`;
    const idx = value.indexOf(marker);
    if (idx === -1) return null;
    return value.slice(idx + marker.length).replace(/\?$/, "").trim();
  } catch {
    return null;
  }
}

/**
 * Returns { openCV, isOpeningCV }.
 * openCV(cvFileUrl) generates a signed URL and opens it in a new tab.
 */
export function useOpenCV() {
  const [isOpeningCV, setIsOpeningCV] = useState(false);

  const openCV = useCallback(async (cvFileUrl) => {
    if (!cvFileUrl) {
      alert("CV introuvable.");
      return;
    }

    const filePath = extractBucketPath(cvFileUrl);
    if (!filePath) {
      console.error("[useOpenCV] Invalid path:", cvFileUrl);
      alert("Chemin du CV invalide. Contactez l'administrateur.");
      return;
    }

    try {
      setIsOpeningCV(true);

      const { data, error } = await supabase.storage
        .from(BUCKET)
        .createSignedUrl(filePath, 3600);

      if (error || !data?.signedUrl) {
        console.error("[useOpenCV] Storage error:", error);
        alert("Impossible d'ouvrir le CV.");
        return;
      }

      window.open(data.signedUrl, "_blank", "noopener,noreferrer");
    } catch (err) {
      console.error("[useOpenCV] Unexpected error:", err);
      alert("Une erreur est survenue.");
    } finally {
      setIsOpeningCV(false);
    }
  }, []);

  return { openCV, isOpeningCV };
}