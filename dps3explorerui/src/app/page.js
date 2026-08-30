"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getSelectedUserId } from "@/services/auth";
import { useQuery } from "react-query";
import { getAdminMe } from "@/services/admin";
import { getExplorerAccess } from "@/services/access";
import { Loader2 } from "lucide-react";

export default function Home() {
  const router = useRouter();
  const userId = getSelectedUserId();

  const { data: access, isLoading: accessLoading } = useQuery(
    ["explorer-access", userId],
    getExplorerAccess,
    { enabled: Boolean(userId), retry: false, staleTime: 60 * 1000 }
  );

  const { data: adminMe, isLoading: adminLoading } = useQuery(
    ["admin-me", userId],
    getAdminMe,
    { enabled: Boolean(userId) && access?.can_access === true, retry: false, staleTime: 5 * 60 * 1000 }
  );

  useEffect(() => {
    if (!userId) { router.replace("/login"); return; }
    if (accessLoading || adminLoading) return;
    const isAdmin = Boolean(adminMe?.is_global_admin || adminMe?.role_label === "admin" || adminMe?.is_admin);
    router.replace(isAdmin ? "/admin" : "/explorer");
  }, [userId, accessLoading, adminLoading, adminMe, router]);

  return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
    </div>
  );
}
