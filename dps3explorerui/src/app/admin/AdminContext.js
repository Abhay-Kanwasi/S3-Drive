"use client";
import { createContext, useContext } from "react";
import { useQuery } from "react-query";
import { getAdminMe } from "@/services/admin";
import { getSessionUser } from "@/services/auth";

const AdminCtx = createContext(null);

export function AdminProvider({ children }) {
  const { data: sessionUser, isLoading: sessionLoading } = useQuery(
    ["session-user"],
    getSessionUser,
    { retry: false, staleTime: 5 * 60 * 1000 },
  );
  const { data: me, isLoading, isError, error } = useQuery(
    ["admin-me"],
    getAdminMe,
    {
      enabled: Boolean(sessionUser),
      retry: false,
      staleTime: 5 * 60 * 1000,
    },
  );

  return (
    <AdminCtx.Provider value={{ me, isLoading: isLoading || sessionLoading, isError, error, userId: sessionUser?.id }}>
      {children}
    </AdminCtx.Provider>
  );
}

export function useAdminMe() {
  const ctx = useContext(AdminCtx);
  if (!ctx) throw new Error("useAdminMe must be inside AdminProvider");
  return ctx;
}
