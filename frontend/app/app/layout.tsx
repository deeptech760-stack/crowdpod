import type { Metadata } from "next";
import "./app.css";
import AppShell from "@/components/app/AppShell";

export const metadata: Metadata = {
  title: "Workspace — Crowdpod",
  description: "Test an idea on a simulated crowd.",
};

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
