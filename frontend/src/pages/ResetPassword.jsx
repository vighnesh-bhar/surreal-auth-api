import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { confirmPasswordReset, verifyPasswordReset } from "../services/api";

export default function ResetPassword() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const code = useMemo(() => searchParams.get("code") || "", [searchParams]);

  const [password, setPassword] = useState("");
  const [confirmPass, setConfirmPass] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [verifying, setVerifying] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function run() {
      setError("");
      setMessage("");

      if (!code) {
        setVerifying(false);
        setError("Missing reset code.");
        return;
      }

      try {
        await verifyPasswordReset(code);
        if (!cancelled) setVerifying(false);
      } catch (err) {
        if (!cancelled) {
          setVerifying(false);
          setError(err.message || "Invalid or expired reset link.");
        }
      }
    }

    run();
    return () => {
      cancelled = true;
    };
  }, [code]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setMessage("");

    if (password !== confirmPass) {
      setError("Passwords do not match.");
      return;
    }

    setSubmitting(true);
    try {
      const res = await confirmPasswordReset({ code, password, confirmPass });
      setMessage(res?.message || "Password reset successfully");
      setTimeout(() => navigate("/"), 1200);
    } catch (err) {
      setError(err.message || "Unable to reset password.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="container">
      <h2>Reset password</h2>

      {verifying ? <p>Verifying reset link...</p> : null}

      {!verifying && error ? (
        <>
          <p className="error">{error}</p>
          <p className="link">
            Back to <Link to="/">Login</Link>
          </p>
        </>
      ) : null}

      {!verifying && !error ? (
        <>
          <form onSubmit={handleSubmit}>
            <input
              type="password"
              placeholder="New password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            <input
              type="password"
              placeholder="Confirm password"
              value={confirmPass}
              onChange={(e) => setConfirmPass(e.target.value)}
              required
            />
            <button type="submit" disabled={submitting}>
              {submitting ? "Resetting..." : "Reset password"}
            </button>
          </form>

          {message ? <p className="success">{message}</p> : null}
          {error ? <p className="error">{error}</p> : null}

          <p className="link">
            Back to <Link to="/">Login</Link>
          </p>
        </>
      ) : null}
    </div>
  );
}

