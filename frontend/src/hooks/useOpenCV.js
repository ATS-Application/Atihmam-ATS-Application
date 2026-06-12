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
    
    // 1. Ensure the URL is absolute. 
    // If the path starts with '/', remove it to avoid double-slash issues.
    const path = cvFileUrl.startsWith('/') ? cvFileUrl.substring(1) : cvFileUrl;
    
    // 2. Use your corrected base URL
    const finalUrl = cvFileUrl.startsWith('http') 
      ? cvFileUrl 
      : `https://nflmcuktfosaketloomh.supabase.co/storage/v1/object/public/${path}`;

    try {
      // 3. window.open with an absolute URL will now properly open in a new tab
      // instead of trying to route internally.
      window.open(finalUrl, "_blank", "noopener,noreferrer");
    } catch (e) {
      console.error("Failed to open CV:", e);
    } finally {
      setIsOpeningCV(false);
    }
  }, []);

  return { openCV, isOpeningCV };
}