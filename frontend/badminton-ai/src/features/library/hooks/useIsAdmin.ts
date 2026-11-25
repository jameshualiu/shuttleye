import { useEffect, useState } from "react";
import { useAuthUser } from "@/auth/hooks/useAuthUser";
import { isAdmin } from "../libraryData";

/** True once the signed-in user is known to have the admin claim. isAdmin() reads
 *  auth.currentUser, so it only runs after Firebase has resolved the session. */
export function useIsAdmin(): boolean {
  const { user, loading } = useAuthUser();
  const [admin, setAdmin] = useState(false);

  useEffect(() => {
    if (loading || !user) return;
    let cancelled = false;
    isAdmin().then((a) => {
      if (!cancelled) setAdmin(a);
    });
    return () => {
      cancelled = true;
    };
  }, [loading, user]);

  return admin && !loading && !!user;
}
