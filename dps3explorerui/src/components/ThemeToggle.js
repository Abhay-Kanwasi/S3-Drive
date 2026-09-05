"use client";
import { useContext } from "react";
import { Sun, Moon } from "lucide-react";
import { ApplicationContext } from "@/services/ContextProvider";

export default function ThemeToggle() {
  const { theme, toggleTheme } = useContext(ApplicationContext);

  // theme is null until useTheme's useEffect fires after mount.
  // Show a same-size invisible placeholder so layout does not shift.
  // Both the icon and toggleTheme wait on the same state — no race.
  if (theme === null) {
    return <div className="w-9 h-9 flex-shrink-0" aria-hidden="true" />;
  }

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className="flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground transition-colors flex-shrink-0"
      aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
    >
      {theme === "dark" ? (
        <Sun className="h-4 w-4" />
      ) : (
        <Moon className="h-4 w-4" />
      )}
    </button>
  );
}
