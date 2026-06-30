"use client";
import type { TokenPair } from "@/types";

const API = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
const ACCESS = "sta_access";
const REFRESH = "sta_refresh";

export const tokens = {
  get access() { return typeof window !== "undefined" ? localStorage.getItem(ACCESS) : null; },
  get refresh() { return typeof window !== "undefined" ? localStorage.getItem(REFRESH) : null; },
  set(p: TokenPair) { localStorage.setItem(ACCESS, p.access_token); localStorage.setItem(REFRESH, p.refresh_token); },
  clear() { localStorage.removeItem(ACCESS); localStorage.removeItem(REFRESH); },
};

async function refreshAccess(): Promise<boolean> {
  const r = tokens.refresh;
  if (!r) return false;
  const res = await fetch(`${API}/auth/refresh`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: r }),
  });
  if (!res.ok) return false;
  tokens.set(await res.json());
  return true;
}

export async function apiFetch<T = any>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(init.headers);
  if (tokens.access) headers.set("Authorization", `Bearer ${tokens.access}`);
  if (!headers.has("Content-Type") && init.body) headers.set("Content-Type", "application/json");

  const res = await fetch(`${API}${path}`, { ...init, headers });

  if (res.status === 401 && retry && (await refreshAccess())) {
    return apiFetch<T>(path, init, false);
  }
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `Erreur ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export async function login(email: string, password: string): Promise<void> {
  const body = new URLSearchParams({ username: email, password });
  const res = await fetch(`${API}/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body,
  });
  if (!res.ok) throw new Error("Email ou mot de passe incorrect");
  tokens.set(await res.json());
}

export const fetcher = <T = any>(path: string) => apiFetch<T>(path);
export { API };
