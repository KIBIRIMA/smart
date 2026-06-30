"use client";
import { useEffect } from "react";
import { MapContainer, TileLayer, Marker, Popup, Polyline, CircleMarker, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { C, TC } from "@/lib/theme";
import type { Tournee, Mission, Agence } from "@/types";

// Icônes Leaflet par défaut cassées avec bundlers → on définit des divIcons.
const pin = (color: string, letter: string) =>
  L.divIcon({
    className: "",
    html: `<div style="background:${color};width:26px;height:26px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);
      border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center">
      <span style="transform:rotate(45deg);color:#fff;font-size:11px;font-weight:700">${letter}</span></div>`,
    iconSize: [26, 26], iconAnchor: [13, 26], popupAnchor: [0, -24],
  });

function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length) map.fitBounds(L.latLngBounds(points), { padding: [40, 40] });
  }, [points, map]);
  return null;
}

export default function MapView({
  tournees = [], missions = [], depot, height = 480,
}: { tournees?: Tournee[]; missions?: Mission[]; depot?: Agence | null; height?: number }) {
  const center: [number, number] = depot ? [depot.lat, depot.lng] : [48.75, 2.4];
  const allPoints: [number, number][] = [
    ...(depot ? [[depot.lat, depot.lng] as [number, number]] : []),
    ...missions.filter((m) => m.lat && m.lng).map((m) => [m.lat!, m.lng!] as [number, number]),
  ];

  return (
    <MapContainer center={center} zoom={10} style={{ height, width: "100%", borderRadius: 10, background: C.navyMid }} scrollWheelZoom>
      <TileLayer
        attribution='&copy; OpenStreetMap'
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
      />
      {allPoints.length > 1 && <FitBounds points={allPoints} />}

      {/* Itinéraires des tournées */}
      {tournees.map((t, i) =>
        t.itineraire?.length > 1 ? (
          <Polyline key={`l${t.id}`} positions={t.itineraire as [number, number][]}
            pathOptions={{ color: t.couleur || TC[i % TC.length], weight: 3, opacity: 0.8, dashArray: "6 4" }} />
        ) : null
      )}

      {/* Dépôt */}
      {depot && (
        <Marker position={[depot.lat, depot.lng]} icon={pin(C.orange, "D")}>
          <Popup><b>Dépôt — {depot.nom}</b><br />{depot.adresse}</Popup>
        </Marker>
      )}

      {/* Missions */}
      {missions.filter((m) => m.lat && m.lng).map((m) => {
        const col = m.type_op === "livraison" ? C.cyan : C.orange;
        return (
          <CircleMarker key={`m${m.id}`} center={[m.lat!, m.lng!]} radius={7}
            pathOptions={{ color: col, fillColor: col, fillOpacity: 0.5, weight: 2 }}>
            <Popup>
              <b>{m.client_nom}</b><br />
              {m.type_op === "livraison" ? "Livraison" : "Récupération"} — {m.machine_modele}<br />
              <span style={{ color: "#666" }}>{m.adresse}</span>
            </Popup>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
