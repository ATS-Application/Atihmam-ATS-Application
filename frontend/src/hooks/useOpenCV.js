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
    
    // 1. Identify the base storage URL for your Supabase project
    const BASE_URL = "https://nflmcuktfosaketloomh.supabase.co/storage/v1/object/public/";
    
    // 2. Construct the absolute URL
    // If it already starts with 'http', use it as-is. 
    // Otherwise, prepend the base URL and ensure no double slashes.
    const cleanPath = cvFileUrl.startsWith('/') ? cvFileUrl.substring(1) : cvFileUrl;
    const finalUrl = cvFileUrl.startsWith('http') ? cvFileUrl : `${BASE_URL}${cleanPath}`;

    try {
      // 3. Open in a new window/tab as an external resource
      window.open(finalUrl, "_blank", "noopener,noreferrer");
    } catch (e) {
      console.error("Failed to open CV:", e);
    } finally {
      setIsOpeningCV(false);
    }
  }, []);

  return { openCV, isOpeningCV };
}
