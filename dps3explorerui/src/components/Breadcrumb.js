"use client";

import { ChevronRight, Home } from "lucide-react";

export default function Breadcrumb({ path = [], onNavigate }) {
  return (
    <nav aria-label="Breadcrumb" className="min-w-0">
      <ol className="flex min-w-0 items-center gap-1 text-sm">
        <li>
          <button
            type="button"
            onClick={() => onNavigate?.(path[0]?.id ?? "")}
            className="rounded p-1.5 text-muted-foreground hover:bg-gray-100 hover:text-foreground"
            aria-label="Root folder"
          >
            <Home className="h-4 w-4" />
          </button>
        </li>
        {path.map((item, index) => (
          <li key={item.id} className="flex min-w-0 items-center gap-1">
            <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
            <button
              type="button"
              onClick={() => onNavigate?.(item.id)}
              className={`max-w-40 truncate rounded px-1.5 py-1 hover:bg-gray-100 hover:text-foreground ${
                index === path.length - 1 ? "font-semibold text-foreground" : "text-muted-foreground"
              }`}
            >
              {item.name}
            </button>
          </li>
        ))}
      </ol>
    </nav>
  );
}