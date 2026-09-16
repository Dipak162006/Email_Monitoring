import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { ShieldCheck, Mail, Lock, Eye, EyeOff, ArrowRight, AlertCircle } from "lucide-react";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const from = (location.state as any)?.from?.pathname || "/dashboard";

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (isLoading) return;
    setError(null);
    setIsLoading(true);

    try {
      await login({ email, password });
      navigate(from, { replace: true });
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to sign in. Please verify your credentials.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div>
      {/* Icon and Header */}
      <div className="h-10 w-10 rounded-2xl bg-indigo-50 border border-indigo-100/80 flex items-center justify-center text-indigo-600 mx-auto mb-2">
        <ShieldCheck className="h-5 w-5" />
      </div>
      <h2 className="text-xl font-bold text-slate-900 tracking-tight text-center">
        Welcome back
      </h2>
      <p className="text-xs text-slate-500 text-center mt-0.5 mb-4 sm:mb-5">
        Sign in to access your workspace.
      </p>

      {/* Error Banner */}
      {error && (
        <div className="mb-3 p-2.5 rounded-xl bg-rose-50 border border-rose-200/80 flex items-start space-x-2 text-rose-700 text-xs">
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5 text-rose-500" />
          <span>{error}</span>
        </div>
      )}

      {/* Login Form */}
      <form onSubmit={handleSubmit} className="space-y-3 sm:space-y-3.5">
        <Input
          label="Email Address"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="alex@pulsemail.io"
          disabled={isLoading}
          leftIcon={<Mail className="h-4 w-4" />}
        />

        <Input
          label="Password"
          type={showPassword ? "text" : "password"}
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••••••"
          disabled={isLoading}
          leftIcon={<Lock className="h-4 w-4" />}
          rightElement={
            <button
              type="button"
              onClick={() => setShowPassword((prev) => !prev)}
              aria-label={showPassword ? "Hide password" : "Show password"}
              className="text-slate-400 hover:text-slate-600 focus:outline-none p-1 transition-colors"
            >
              {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          }
        />

        <Button
          type="submit"
          isLoading={isLoading}
          disabled={isLoading}
          className="w-full h-10 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-medium text-xs shadow-xs gap-1.5 mt-1.5"
        >
          <span>Sign in to workspace</span>
          <ArrowRight className="h-4 w-4" />
        </Button>
      </form>

      {/* Bottom Switch Link */}
      <p className="text-center text-xs text-slate-500 mt-3.5 sm:mt-4">
        Don&apos;t have an account?{" "}
        <Link to="/register" className="font-semibold text-indigo-600 hover:text-indigo-700 transition-colors">
          Sign up
        </Link>
      </p>
    </div>
  );
}
