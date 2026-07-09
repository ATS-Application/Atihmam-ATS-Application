// src/hooks/useOpenCV.js
import { useState, useCallback } from "react";
import { getCandidateCVUrl } from "../api/candidatesApi";

const BUCKET_BASE_URL =
  "https://nflmcuktfosaketloomh.supabase.co/storage/v1/object/public/cvs/";

export function useOpenCV() {
  const [isOpeningCV, setIsOpeningCV] = useState(false);

  const openCV = useCallback(async (cvFileUrl, candidateId = null) => {
    if (!cvFileUrl) {
      alert("CV introuvable.");
      return;
    }

    setIsOpeningCV(true);

    try {
      let finalUrl;

      if (candidateId) {
        const response = await getCandidateCVUrl(candidateId);
        finalUrl = response.data?.url;
      } else if (cvFileUrl.startsWith("http")) {
        finalUrl = cvFileUrl;
      } else {
        const cleanPath = cvFileUrl
          .replace(/^\/+/, "")
          .replace(/^cvs\//, "")
          .replace(/^public\//, "");

        finalUrl = `${BUCKET_BASE_URL}${cleanPath}`;
      }

      if (!finalUrl) {
        throw new Error("No CV URL returned");
      }

      window.open(finalUrl, "_blank", "noopener,noreferrer");
    } catch (error) {
      console.error("Failed to open CV:", error);
      alert("Impossible d'ouvrir le CV.");
    } finally {
      setIsOpeningCV(false);
    }
  }, []);

  return { openCV, isOpeningCV };
}
