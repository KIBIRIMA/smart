"use client";
import { C } from "@/lib/theme";
import type { ReactNode } from "react";

export default function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 18 }}>
      <div>
        <h1 style={{ fontSize: 22, fontWeight: 900, letterSpacing: "-.02em" }}>{title}</h1>
        {subtitle && <p style={{ color: C.textMid, fontSize: 12, marginTop: 2 }}>{subtitle}</p>}
      </div>
      {actions && <div style={{ display: "flex", gap: 8 }}>{actions}</div>}
    </div>
  );
}
