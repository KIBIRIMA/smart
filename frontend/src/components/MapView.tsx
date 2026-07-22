"use client";
import { useEffect, useMemo, useState, useRef } from "react";
import { MapContainer, TileLayer, Marker, Popup, Polyline, CircleMarker, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { C, TC } from "@/lib/theme";
import type { Tournee, Mission, Agence } from "@/types";


// Icônes Leaflet par défaut cassées avec bundlers → divIcons.
const pin = (color: string, letter: string) =>
  L.divIcon({
    className: "",
    html: `<div style="background:${color};width:26px;height:26px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);
      border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center">
      <span style="transform:rotate(45deg);color:#fff;font-size:11px;font-weight:700">${letter}</span></div>`,
    iconSize: [26, 26], iconAnchor: [13, 26], popupAnchor: [0, -24],
  });

// Pastille numérotée = ordre de passage.
const numDot = (n: number, color: string) =>
  L.divIcon({
    className: "",
    html: `<div style="background:${color};width:20px;height:20px;border-radius:50%;border:2px solid #fff;
      box-shadow:0 1px 4px rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;
      color:#fff;font-size:10px;font-weight:800">${n}</div>`,
    iconSize: [20, 20], iconAnchor: [10, 10], popupAnchor: [0, -10],
  });

const PURPLE = (C as any).purple || "#8B5CF6";

function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap();
  const done = useRef(false);
  useEffect(() => {
    if (!done.current && points.length) {
      map.fitBounds(L.latLngBounds(points), { padding: [40, 40] });
      done.current = true;
    }
  }, [points, map]);
  return null;
}

// Flèches de sens au milieu de chaque segment.
function ArrowHeads({ path, color }: { path: [number, number][]; color: string }) {
  const arrows = useMemo(() => {
    const out: { pos: [number, number]; angle: number }[] = [];
    for (let i = 0; i < path.length - 1; i++) {
      const [aLat, aLng] = path[i], [bLat, bLng] = path[i + 1];
      const mid: [number, number] = [(aLat + bLat) / 2, (aLng + bLng) / 2];
      const angle = (Math.atan2(bLat - aLat, bLng - aLng) * 180) / Math.PI;
      out.push({ pos: mid, angle: -angle });
    }
    return out;
  }, [path]);
  return (
    <>
      {arrows.map((a, i) => (
        <Marker key={i} position={a.pos} interactive={false}
          icon={L.divIcon({
            className: "",
            html: `<div style="transform:rotate(${a.angle}deg);color:${color};font-size:16px;line-height:1;
              text-shadow:0 0 3px rgba(0,0,0,.8)">&#10163;</div>`,
            iconSize: [16, 16], iconAnchor: [8, 8],
          })} />
      ))}
    </>
  );
}

export default function MapView({
  tournees = [], missions = [], depot, height = 480, selectedId,
}: {
  tournees?: Tournee[]; missions?: Mission[]; depot?: Agence | null;
  height?: number; selectedId?: number | "all";
}) {
  const [hoverId, setHoverId] = useState<number | null>(null);
  const center: [number, number] = depot ? [depot.lat, depot.lng] : [48.75, 2.4];

  const memePoint = (a: [number, number], b: [number, number]) =>
    Math.abs(a[0] - b[0]) < 1e-5 && Math.abs(a[1] - b[1]) < 1e-5;

  const boucle = (t: Tournee): [number, number][] => {
    const pts = (((t as any).itineraire || []) as [number, number][]).filter(
      (p) => Array.isArray(p) && p.length === 2 && p[0] != null && p[1] != null
    );
    if (!pts.length || !depot) return pts;
    const d: [number, number] = [depot.lat, depot.lng];
    const out = [...pts];
    if (!memePoint(out[0], d)) out.unshift(d);
    if (!memePoint(out[out.length - 1], d)) out.push(d);
    return out;
  };

  const visibles = useMemo(() => {
    if (selectedId == null || selectedId === "all") return tournees;
    return tournees.filter((t: any) => t.id === selectedId);
  }, [tournees, selectedId]);

  const focusUnique = visibles.length === 1;

  const allPoints: [number, number][] = [
    ...(depot ? [[depot.lat, depot.lng] as [number, number]] : []),
    ...visibles.flatMap((t) => boucle(t)),
  ];

  return (
    <MapContainer center={center} zoom={10} style={{ height, width: "100%", borderRadius: 10, background: C.navyMid }} scrollWheelZoom>
      <TileLayer attribution='&copy; OpenStreetMap'
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" />
      {allPoints.length > 1 && <FitBounds points={allPoints} />}

      {visibles.map((t, i) => {
        const path = boucle(t);
        if (path.length < 2) return null;
        const color = (t as any).couleur || TC[i % TC.length];
        const estompe = hoverId != null && hoverId !== (t as any).id;
        const opacity = estompe ? 0.15 : 0.85;
        const cible = focusUnique || hoverId === (t as any).id;
        return (
          <div key={`grp${(t as any).id}`}>
            <Polyline positions={path}
              pathOptions={{ color, weight: estompe ? 2 : 3.5, opacity }}
              eventHandlers={{
                mouseover: () => setHoverId((t as any).id),
                mouseout: () => setHoverId(null),
              }} />
            {cible && (
              <>
                <ArrowHeads path={path} color={color} />
                {path.map((p, k) => {
                  const estDepot = depot && memePoint(p, [depot.lat, depot.lng]);
                  if (estDepot) return null;
                  return (
                    <Marker key={`n${k}`} position={p} icon={numDot(k, color)}>
                      <Popup>Arrêt {k} — {(t as any).chauffeur_nom || `tournée ${(t as any).id}`}</Popup>
                    </Marker>
                  );
                })}
              </>
            )}
          </div>
        );
      })}

      {depot && (
        <Marker position={[depot.lat, depot.lng]} icon={pin(C.orange, "D")}>
          <Popup><b>Dépôt — {depot.nom}</b><br />{depot.adresse}</Popup>
        </Marker>
      )}

      {!focusUnique && missions.filter((m) => m.lat && m.lng).map((m) => {
        const col = m.type_op === "livraison" ? C.cyan : PURPLE;
        return (
          <CircleMarker key={`m${m.id}`} center={[m.lat!, m.lng!]} radius={6}
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
