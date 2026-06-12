// src/hooks/useOpenCV.js
import { useState, useCallback } from "react";

const BUCKET_BASE_URL =
  "https://nflmcuktfosaketloomh.supabase.co/storage/v1/object/public/cvs/manual/";

/**
 * Open a candidate CV in a new browser tab.
 *
 * Supports:
 * - Full public URLs
 * - Relative storage paths
 * - Paths that accidentally include "public/"
 */
export function useOpenCV() {
  const [isOpeningCV, setIsOpeningCV] = useState(false);

  const openCV = useCallback((cvFileUrl) => {
    if (!cvFileUrl) {
      alert("CV introuvable.");
      return;
    }

    setIsOpeningCV(true);

    try {
      let finalUrl;

      if (cvFileUrl.startsWith("http")) {
        // Already a complete URL
        finalUrl = cvFileUrl;
      } else {
        const cleanPath = cvFileUrl.replace(/^\/+/, "");

        const normalizedPath = cleanPath.startsWith("public/")
          ? cleanPath.replace(/^public\//, "")
          : cleanPath;

        finalUrl = `${BASE_STORAGE_URL}${normalizedPath}`;
      }

      console.log("Opening CV:", finalUrl);

      window.open(finalUrl, "_blank", "noopener,noreferrer");
    } catch (error) {
      console.error("Failed to open CV:", error);
      alert("Impossible d'ouvrir le CV.");
    } finally {
      setIsOpeningCV(false);
    }
  }, []);

  return {
    openCV,
    isOpeningCV,
  };
}