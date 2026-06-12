// src/hooks/useOpenCV.js
import { useState, useCallback } from "react";

/**
 * Opens a CV in a new tab directly from its stored public URL.
 * No signed URL generation needed — cv_file_url is already a public
 * Supabase Storage URL returned by get_public_url() at ingestion time.
 */
export function useOpenCV() {
  const [isOpeningCV, setIsOpeningCV] = useState(false);

  const openCV = useCallback((cvFileUrl) => {
    if (!cvFileUrl) {
      alert("CV introuvable.");
      return;
    }

    setIsOpeningCV(true);
    
    let finalUrl = cvFileUrl;
    
    // Check if it's already an absolute URL
    if (!finalUrl.startsWith('http')) {
       // Corrected path construction
       finalUrl = `https://nflmcuktfosaketloomh.supabase.co/storage/v1/object/public/${cvFileUrl}`;
    }

    try {
      window.open(finalUrl, "_blank", "noopener,noreferrer");
    } catch (e) {
      console.error("Failed to open CV:", e);
    } finally {
      setIsOpeningCV(false);
    }
  }, []);

  return { openCV, isOpeningCV };
}