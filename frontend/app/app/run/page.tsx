import { Suspense } from "react";
import RunView from "@/components/app/RunView";

export const metadata = { title: "Simulation — Crowdpod" };

export default function Page() {
  return (
    <Suspense fallback={<p className="app-empty">Loading simulation…</p>}>
      <RunView />
    </Suspense>
  );
}
