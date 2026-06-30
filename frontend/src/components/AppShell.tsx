"use client";
import { useAuth } from "@/hooks/useAuth";
import Sidebar from "./Sidebar";
import Navbar from "./Navbar";
import { Spinner } from "./ui";
import { C } from "@/lib/theme";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();

  if (isLoading || !user) {
    return (
      <div style={{ height: "100vh", display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 12 }}>
        <Spinner size={28} />
        <span style={{ color: C.textMid, fontSize: 12 }}>Chargement de la plateforme…</span>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <Sidebar />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <Navbar />
        <main style={{ flex: 1, overflowY: "auto", padding: "22px 26px 48px", background: C.bg }} className="fade-up">
          {children}
        </main>
      </div>
    </div>
  );
}
