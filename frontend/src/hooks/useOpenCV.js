// src/hooks/useOpenCV.js
import { useState, useCallback } from "react";

/**
 * Opens a CV in a new tab directly from its stored public URL.
 * No signed URL generation needed — cv_file_url is already a public
 * Supabase Storage URL returned by get_public_url() at ingestion time.
 */
// src/hooks/useOpenCV.js
export function useOpenCV() {
  const [isOpeningCV, setIsOpeningCV] = useState(false);

  const openCV = useCallback((cvFileUrl) => {
    if (!cvFileUrl) {
      alert("CV introuvable.");
      return;
    }

    setIsOpeningCV(true);
    
    // Ensure the URL is absolute before opening
    let finalUrl = cvFileUrl;
    if (!finalUrl.startsWith('http')) {
       // If it's a relative path, prepend your base URL or handle accordingly
       finalUrl = `https://nflmcuktfosaketloomh.supabase.co.supabase.co/storage/v1/object/public/${cvFileUrl}`;
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
