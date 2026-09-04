"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

const DOCK_ID = "background-task-dock";

/** Column above the floating "New" button where background task toasts stack. */
export function TaskDock() {
  return (
    <div
      id={DOCK_ID}
      className="fixed bottom-24 right-8 z-40 flex flex-col items-end gap-2"
    />
  );
}

export function DockedToast({ children }) {
  const [dock, setDock] = useState(null);

  useEffect(() => {
    setDock(document.getElementById(DOCK_ID));
  }, []);

  if (!dock) return null;
  return createPortal(children, dock);
}
