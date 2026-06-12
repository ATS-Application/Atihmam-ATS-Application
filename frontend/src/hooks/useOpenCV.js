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
    
    // Ensure the path is clean and prepended with your Supabase storage URL
    const BASE_STORAGE_URL = "https://nflmcuktfosaketloomh.supabase.co/storage/v1/object/public/";
    
    // If the path already has a leading slash, remove it so it doesn't duplicate
    const path = cvFileUrl.startsWith('/') ? cvFileUrl.substring(1) : cvFileUrl;
    
    const finalUrl = cvFileUrl.startsWith('http') 
        ? cvFileUrl 
        : `${BASE_STORAGE_URL}${path}`;

    try {
      // By using an absolute URL, the browser treats this as an external file
      window.open(finalUrl, "_blank", "noopener,noreferrer");
    } catch (e) {
      console.error("Failed to open CV:", e);
    } finally {
      setIsOpeningCV(false);
    }
  }, []);

  return { openCV, isOpeningCV };
}
