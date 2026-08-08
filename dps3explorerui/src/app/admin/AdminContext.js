"use client";
import { createContext, useContext } from "react";
import { useQuery } from "react-query";
import { getAdminMe } from "@/services/admin";

const AdminCtx = createContext(null);

export function AdminProvider({ children }) {
  const { data: me, isLoading, isError, error } = useQuery("admin-me", getAdminMe, {
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  return (
    <AdminCtx.Provider value={{ me, isLoading, isError, error }}>
      {children}
    </AdminCtx.Provider>
  );
}

export function useAdminMe() {
  const ctx = useContext(AdminCtx);
  if (!ctx) throw new Error("useAdminMe must be inside AdminProvider");
  return ctx;
}
