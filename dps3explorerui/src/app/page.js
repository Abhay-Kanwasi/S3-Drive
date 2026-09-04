"use client";

import { useContext, useEffect } from "react";
import { useRouter } from "next/navigation";
import { getSelectedUserId } from "@/services/auth";
import { ApplicationContext } from "@/services/ContextProvider";
import { useQuery } from "react-query";
import { getExplorerAccess } from "@/services/access";
import { Loader2 } from "lucide-react";
import LandingPage from "@/components/LandingPage";
import S3ExplorerAccessBlocked from "@/components/S3ExplorerAccessBlocked";

export default function Home() {
  const router = useRouter();
  const { setCurrentUserId } = useContext(ApplicationContext);
  const userId = getSelectedUserId();

  const { data: access, isLoading, isError, error } = useQuery(
    ["explorer-access", userId],
    getExplorerAccess,
    { enabled: Boolean(userId), retry: false, staleTime: 60 * 1000, refetchOnMount: false }
  );

  const unauthorized = isError && error?.status === 401;

  useEffect(() => {
    if (!userId) router.replace("/login");
  }, [userId, router]);

  useEffect(() => {
    if (!unauthorized) return;
    setCurrentUserId("");
    router.replace("/login");
  }, [unauthorized, router, setCurrentUserId]);

  if (!userId || unauthorized || isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (access && !access.can_access) {
    return <S3ExplorerAccessBlocked access={access} />;
  }

  if (isError || !access) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center px-6">
        <p className="text-sm text-muted-foreground text-center">
          Unable to load identity for user {userId}. Try signing in again.
        </p>
      </div>
    );
  }

  return <LandingPage />;
}
