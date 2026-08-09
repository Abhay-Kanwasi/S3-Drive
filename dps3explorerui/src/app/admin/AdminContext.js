"use client";
import { createContext, useContext } from "react";
import { useQuery } from "react-query";
import { getAdminMe } from "@/services/admin";
import { getSelectedUserId } from "@/services/auth";

const AdminCtx = createContext(null);

export function AdminProvider({ children }) {
  const userId = typeof window !== "undefined" ? getSelectedUserId() : null;
  const { data: me, isLoading, isError, error } = useQuery(
    ["admin-me", userId],
    getAdminMe,
    {
      enabled: Boolean(userId),
      retry: false,
      staleTime: 5 * 60 * 1000,
    },
  );

  return (
    <AdminCtx.Provider value={{ me, isLoading, isError, error, userId }}>
      {children}
    </AdminCtx.Provider>
  );
}

export function useAdminMe() {
  const ctx = useContext(AdminCtx);
  if (!ctx) throw new Error("useAdminMe must be inside AdminProvider");
  return ctx;
}
