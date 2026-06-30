"use client";
import useSWR from "swr";
import { useRouter } from "next/navigation";
import { fetcher, tokens } from "@/lib/api";
import type { User } from "@/types";

export function useAuth(redirectOnFail = true) {
  const router = useRouter();
  const { data, error, isLoading, mutate } = useSWR<User>(
    tokens.access ? "/auth/me" : null,
    fetcher,
    { shouldRetryOnError: false, revalidateOnFocus: false }
  );

  if (redirectOnFail && !isLoading && (error || (!tokens.access))) {
    if (typeof window !== "undefined") router.replace("/login");
  }

  const logout = () => { tokens.clear(); mutate(undefined, false); router.replace("/login"); };
  return { user: data, isLoading, error, logout, mutate };
}
