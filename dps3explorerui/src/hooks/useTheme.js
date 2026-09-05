"use client";
import { useState, useEffect } from "react";

export function useTheme() {
  // null = not yet mounted on client.
  // Prevents a hydration mismatch: server renders without knowing the stored theme,
  // so we defer reading localStorage until after mount.
  const [theme, setTheme] = useState(null);

  useEffect(() => {
    let preferred = "light";
    try {
      const stored = localStorage.getItem("theme");
      // Accept ONLY "light" or "dark" — ignore corrupted/old/missing values.
      if (stored === "light" || stored === "dark") {
        preferred = stored;
      } else if (window.matchMedia("(prefers-color-scheme: dark)").matches) {
        preferred = "dark";
      }
    } catch (_) {
      // localStorage unavailable (Safari private mode, etc.) — use "light".
    }
    setTheme(preferred);
    document.documentElement.classList.toggle("dark", preferred === "dark");
  }, []);

  const toggleTheme = () => {
    setTheme((prev) => {
      // toggleTheme is only reachable after mount, so prev is "light" or "dark", never null.
      const next = prev === "dark" ? "light" : "dark";
      try {
        localStorage.setItem("theme", next);
      } catch (_) {
        // Safari private mode or storage quota exceeded — silently ignore.
      }
      document.documentElement.classList.toggle("dark", next === "dark");
      return next;
    });
  };

  return { theme, toggleTheme };
}
