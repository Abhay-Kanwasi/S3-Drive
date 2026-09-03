"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getSelectedUserId } from "@/services/auth";
import { useQuery } from "react-query";
import { getExplorerAccess } from "@/services/access";
import { Loader2 } from "lucide-react";
import LandingPage from "@/components/LandingPage";

export default function Home() {
  const router = useRouter();
  const userId = getSelectedUserId();

  const { data: access, isLoading } = useQuery(
    ["explorer-access", userId],
    getExplorerAccess,
    { enabled: Boolean(userId), retry: false, staleTime: 60 * 1000 }
  );

  useEffect(() => {
    if (!userId) router.replace("/login");
  }, [userId, router]);

  if (!userId || isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return <LandingPage />;
}
