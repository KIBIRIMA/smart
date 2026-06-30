"use client";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { Kpi, Mission, Tournee, Machine, Vehicule, Chauffeur, Client, Agence } from "@/types";

export const useKpi = () => useSWR<Kpi>("/dashboard/kpi", fetcher, { refreshInterval: 30000 });
export const useMissions = (qs = "") => useSWR<Mission[]>(`/missions${qs}`, fetcher);
export const useTournees = () => useSWR<Tournee[]>("/tournees", fetcher);
export const useMachines = () => useSWR<Machine[]>("/machines", fetcher);
export const useVehicules = () => useSWR<Vehicule[]>("/vehicules", fetcher);
export const useChauffeurs = () => useSWR<Chauffeur[]>("/chauffeurs", fetcher);
export const useClients = () => useSWR<Client[]>("/clients", fetcher);
export const useAgences = () => useSWR<Agence[]>("/agences", fetcher);
export const useHistory = () => useSWR("/optimizer/history", fetcher);
