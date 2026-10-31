"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "motion/react";
import {
  Mail,
  Lock,
  User,
  ArrowRight,
  ArrowLeft,
  Check,
  ShieldCheck,
  Eye,
  EyeOff,
  Sparkles,
  Loader2,
  AlertCircle,
  X,
  Users,
  UsersRound,
} from "lucide-react";
import { api } from "@/lib/api";

export function AuthLogo() {
  return (
    <Link href="/" className="auth-logo" aria-label="Return to Crowdpod home">
      <span className="auth-logo-icon">
        <UsersRound size={22} className="logo-doc" />
        <Users size={14} className="logo-layers" />
      </span>
      <span className="auth-logo-text">
        Crowd<span className="logo-brd">pod</span>
      </span>
    </Link>
  );
}

// Crowd signal bars: five bold vertical bars that rise and fall like a live poll
const signalBars = [
  { id: 1, baseHeight: 145, keyframes: [145, 95, 160, 115, 145], duration: 1.8, delay: 0 },
  { id: 2, baseHeight: 62, keyframes: [62, 85, 45, 78, 62], duration: 1.4, delay: 0.15 },
  { id: 3, baseHeight: 105, keyframes: [105, 135, 80, 120, 105], duration: 1.7, delay: 0.25 },
  { id: 4, baseHeight: 65, keyframes: [65, 48, 90, 58, 65], duration: 1.5, delay: 0.1 },
  { id: 5, baseHeight: 150, keyframes: [150, 110, 165, 130, 150], duration: 1.9, delay: 0.05 },
];

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialMode = searchParams.get("mode") === "register" ? "register" : "login";

  const [mode, setMode] = useState<"login" | "register" | "forgot">(initialMode);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [rememberMe, setRememberMe] = useState(true);
  const [agreeTerms, setAgreeTerms] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  // a failed Google sign-in comes back as ?error=...
  const [error, setError] = useState<string | null>(searchParams.get("error"));
  const [successDialog, setSuccessDialog] = useState<string | null>(null);
  const [googleReady, setGoogleReady] = useState<boolean | null>(null);
  const next = searchParams.get("next");
  const destination = next && next.startsWith("/app/") ? next : "/app/";

  useEffect(() => {
    api.authConfig().then((c) => setGoogleReady(c.google)).catch(() => setGoogleReady(false));
    // already signed in: go straight to the app
    api.me().then((m) => m.user && window.location.assign(destination)).catch(() => {});
  }, [destination]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    // Validation
    if (!email || !email.includes("@") || !email.includes(".")) {
      setError("Please enter a valid work email address.");
      return;
    }
    if (mode === "register" && password.length < 8) {
      setError("Use a password of at least 8 characters.");
      return;
    }
    if (mode === "login" && !password) {
      setError("Enter your password.");
      return;
    }
    if (mode === "register" && !name.trim()) {
      setError("Please enter your full name.");
      return;
    }
    if (mode === "register" && !agreeTerms) {
      setError("Please accept the Terms of Service to continue.");
      return;
    }

    if (mode === "forgot") {
      // There's no email service on a self-hosted Crowdpod, so no fake "link sent" message.
      setError("Password reset by email isn't available on this Crowdpod. Ask the person who runs it to reset your account, or sign in with Google.");
      return;
    }

    setLoading(true);
    try {
      if (mode === "register") await api.register(name.trim(), email.trim(), password);
      else await api.login(email.trim(), password);
      // a full page load, so the app starts fresh with the new session
      window.location.assign(destination);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't reach the Crowdpod server.");
      setLoading(false);
    }
  };

  const handleGoogleLogin = () => {
    setError(null);
    if (!googleReady) {
      setError("Google sign-in isn't set up on this Crowdpod yet. Use email and password, or ask the person who runs it to add Google sign-in.");
      return;
    }
    setLoading(true);
    window.location.assign(api.googleStartUrl());
  };

  return (
    <div className="auth-page-root">
      {/* Clean, Minimal Header: No "How it works" navigation pill bar */}
      <header className="auth-header-minimal">
        <AuthLogo />
        <Link href="/" className="auth-back-link">
          <ArrowLeft size={16} />
          <span>Back to home</span>
        </Link>
      </header>

      {/* Main Two-Column Auth Screen */}
      <main className="auth-main-container">
        <div className="auth-split-grid">
          {/* Left Column: Visual Storytelling Canvas */}
          <div className="auth-left-canvas">
            <div className="auth-hero-copy">
              <span className="auth-eyebrow">A THOUSAND HONEST OPINIONS</span>
              <h1 className="auth-title">
                Good ideas
                <br />
                <em>deserve honesty.</em>
              </h1>
              <p className="auth-description">
                Sign in to test your ideas on a crowd that can’t lie to be nice.
              </p>
            </div>

            {/* Crowd signal: big animated bars */}
            <div className="bold-voice-section">
              <div className="bold-voice-container" aria-label="Animated crowd signal">
                {signalBars.map((bar) => (
                  <motion.span
                    key={bar.id}
                    className={`bold-voice-bar bold-voice-bar-${bar.id}`}
                    animate={{
                      height: bar.keyframes,
                    }}
                    transition={{
                      duration: bar.duration,
                      repeat: Infinity,
                      repeatType: "mirror",
                      ease: "easeInOut",
                      delay: bar.delay,
                    }}
                    style={{
                      height: `${bar.baseHeight}px`,
                    }}
                  />
                ))}
              </div>
            </div>

            {/* Bottom-left Micro Note */}
            <div className="auth-bottom-note">
              <span className="square-dot" /> ONE PERSON IS NOISE. A CROWD IS SIGNAL.
            </div>
          </div>

          {/* Right Column: The White Auth Card */}
          <div className="auth-right-panel">
            <motion.div
              className="auth-card-box"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, ease: "easeOut" }}
            >
              {/* Card Header with Logo */}
              <div className="card-top-branding">
                <AuthLogo />
              </div>

              <div className="card-header-titles">
                <h2 className="card-heading">
                  {mode === "login" && "Welcome back"}
                  {mode === "register" && "Create an account"}
                  {mode === "forgot" && "Reset password"}
                </h2>
                <p className="card-subheading">
                  {mode === "login" && "Sign in to continue to your workspace."}
                  {mode === "register" && "Start testing your ideas on a simulated crowd."}
                  {mode === "forgot" && "Enter your email to receive recovery instructions."}
                </p>
              </div>

              {/* Error Alert */}
              <AnimatePresence>
                {error && (
                  <motion.div
                    className="auth-error-banner"
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                  >
                    <AlertCircle size={16} />
                    <span>{error}</span>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Main Form */}
              <form className="auth-form-body" onSubmit={handleSubmit} noValidate>
                {/* Full Name (Register Mode only) */}
                {mode === "register" && (
                  <div className="form-group">
                    <label htmlFor="auth-name">Full name</label>
                    <div className="input-field-shell">
                      <User size={18} className="field-icon" />
                      <input
                        id="auth-name"
                        type="text"
                        placeholder="Sarah Jenkins"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        required
                        autoFocus
                      />
                    </div>
                  </div>
                )}

                {/* Email Address Field */}
                <div className="form-group">
                  <label htmlFor="auth-email">Email address</label>
                  <div className="input-field-shell">
                    <Mail size={18} className="field-icon" />
                    <input
                      id="auth-email"
                      type="email"
                      placeholder="you@company.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                      autoFocus={mode !== "register"}
                    />
                  </div>
                </div>

                {/* Password Field (Login & Register) */}
                {mode !== "forgot" && (
                  <div className="form-group">
                    <div className="label-with-link">
                      <label htmlFor="auth-password">Password</label>
                      {mode === "login" && (
                        <button
                          type="button"
                          className="forgot-link-btn"
                          onClick={() => {
                            setMode("forgot");
                            setError(null);
                          }}
                        >
                          Forgot password?
                        </button>
                      )}
                    </div>
                    <div className="input-field-shell">
                      <Lock size={18} className="field-icon" />
                      <input
                        id="auth-password"
                        type={showPassword ? "text" : "password"}
                        placeholder="••••••••••••"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        required
                      />
                      <button
                        type="button"
                        className="toggle-pw-btn"
                        onClick={() => setShowPassword(!showPassword)}
                        aria-label={showPassword ? "Hide password" : "Show password"}
                      >
                        {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                      </button>
                    </div>
                  </div>
                )}

                {/* Checkbox Options */}
                {mode === "login" && (
                  <div className="checkbox-row">
                    <label className="custom-check-label">
                      <input
                        type="checkbox"
                        checked={rememberMe}
                        onChange={(e) => setRememberMe(e.target.checked)}
                      />
                      <span className="check-box-indicator">
                        {rememberMe && <Check size={13} strokeWidth={3} />}
                      </span>
                      <span>Remember me</span>
                    </label>
                  </div>
                )}

                {mode === "register" && (
                  <div className="checkbox-row">
                    <label className="custom-check-label">
                      <input
                        type="checkbox"
                        checked={agreeTerms}
                        onChange={(e) => setAgreeTerms(e.target.checked)}
                      />
                      <span className="check-box-indicator">
                        {agreeTerms && <Check size={13} strokeWidth={3} />}
                      </span>
                      <span className="terms-text">
                        I agree to the <Link href="/#terms">Terms</Link> and{" "}
                        <Link href="/#privacy">Privacy Policy</Link>
                      </span>
                    </label>
                  </div>
                )}

                {/* Primary Submit Button */}
                <button
                  type="submit"
                  className="auth-primary-btn"
                  disabled={loading}
                  aria-busy={loading}
                >
                  {loading ? (
                    <>
                      <Loader2 size={18} className="animate-spin" />
                      <span>{mode === "forgot" ? "Sending link..." : "Please wait..."}</span>
                    </>
                  ) : (
                    <>
                      <span>
                        {mode === "login" && "Sign in"}
                        {mode === "register" && "Create account"}
                        {mode === "forgot" && "Send reset link"}
                      </span>
                      <ArrowRight size={17} className="btn-arrow" />
                    </>
                  )}
                </button>
              </form>

              {/* Or continue with divider */}
              {mode !== "forgot" && (
                <>
                  <div className="auth-divider">
                    <span className="divider-line" />
                    <span className="divider-text">or continue with</span>
                    <span className="divider-line" />
                  </div>

                  {/* Google OAuth Button */}
                  <button
                    type="button"
                    className="google-oauth-btn"
                    onClick={handleGoogleLogin}
                    disabled={loading}
                  >
                    <svg
                      className="google-icon"
                      viewBox="0 0 24 24"
                      width="19"
                      height="19"
                      xmlns="http://www.w3.org/2000/svg"
                    >
                      <path
                        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                        fill="#4285F4"
                      />
                      <path
                        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                        fill="#34A853"
                      />
                      <path
                        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
                        fill="#FBBC05"
                      />
                      <path
                        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
                        fill="#EA4335"
                      />
                    </svg>
                    <span>Continue with Google{googleReady === false ? " (not set up)" : ""}</span>
                  </button>
                </>
              )}

              {/* Toggle Mode Footer */}
              <div className="auth-card-footer">
                {mode === "login" && (
                  <p>
                    New to Crowdpod?{" "}
                    <button
                      type="button"
                      className="switch-mode-link"
                      onClick={() => {
                        setMode("register");
                        setError(null);
                      }}
                    >
                      Create an account
                    </button>
                  </p>
                )}

                {mode === "register" && (
                  <p>
                    Already have an account?{" "}
                    <button
                      type="button"
                      className="switch-mode-link"
                      onClick={() => {
                        setMode("login");
                        setError(null);
                      }}
                    >
                      Sign in
                    </button>
                  </p>
                )}

                {mode === "forgot" && (
                  <p>
                    Remembered your password?{" "}
                    <button
                      type="button"
                      className="switch-mode-link"
                      onClick={() => {
                        setMode("login");
                        setError(null);
                      }}
                    >
                      Back to sign in
                    </button>
                  </p>
                )}
              </div>

              {/* Security Footnote */}
              <div className="auth-security-footnote">
                <ShieldCheck size={16} className="security-shield-icon" />
                <div className="security-copy">
                  <p>Your data is secure and never shared.</p>
                  <p>We value your privacy.</p>
                </div>
              </div>
            </motion.div>
          </div>
        </div>
      </main>

      {/* Interactive Success / Workspace Preview Dialog */}
      <AnimatePresence>
        {successDialog && (
          <div className="success-dialog-backdrop">
            <motion.div
              className="success-dialog-card"
              initial={{ opacity: 0, scale: 0.92, y: 15 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
            >
              <button
                className="close-dialog-x"
                onClick={() => setSuccessDialog(null)}
                aria-label="Close dialog"
              >
                <X size={20} />
              </button>

              <div className="success-badge-icon">
                <Check size={28} />
              </div>

              <span className="mini-label">AUTHENTICATION SUCCESSFUL</span>
              <h2>Your crowd is ready.</h2>
              <p>{successDialog}</p>

              <div className="dialog-action-buttons">
                <button
                  className="dialog-primary-action"
                  // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- static export writes nested-route payloads where the client router can't find them; use a full page load
                  onClick={() => window.location.assign("/app/")}
                >
                  <Sparkles size={16} /> Start a simulation
                </button>
                <button
                  className="dialog-secondary-action"
                  onClick={() => router.push("/")}
                >
                  Return to Home
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
