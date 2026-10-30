import { Suspense } from "react";
import LoginPage from "@/components/auth/LoginPage";

export const metadata = {
  title: "Sign in — Crowdpod",
  description: "Sign in to test your ideas on a simulated crowd.",
};

export default function Page() {
  return (
    <Suspense fallback={<div className="auth-loading-fallback">Loading Crowdpod...</div>}>
      <LoginPage />
    </Suspense>
  );
}
