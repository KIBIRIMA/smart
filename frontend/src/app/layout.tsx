import "./globals.css";
import "leaflet/dist/leaflet.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Smart Transport AI — Accès Industrie",
  description: "Plateforme d'optimisation logistique : tournées, chargement 2D, multi-agences.",
  icons: { icon: "/favicon.svg" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet" />
      </head>
      <body>{children}</body>
    </html>
  );
}
