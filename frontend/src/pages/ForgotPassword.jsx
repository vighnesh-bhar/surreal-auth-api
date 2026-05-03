import { useState } from "react";
import { Link } from "react-router-dom";
import { requestPasswordReset } from "../services/api";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setMessage("");
    setLoading(true);

    try {
      const res = await requestPasswordReset(email);
      setMessage(
        res?.message ||
          "If your email exists, a password reset link has been sent."
      );
    } catch (err) {
      setError(err.message || "Unable to request password reset.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container">
      <h2>Forgot password</h2>
      <p>Enter your email and we’ll send you a reset link.</p>

      <form onSubmit={handleSubmit}>
        <input
          type="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <button type="submit" disabled={loading}>
          {loading ? "Sending..." : "Send reset link"}
        </button>
      </form>

      {error ? <p className="error">{error}</p> : null}
      {message ? <p className="success">{message}</p> : null}

      <p className="link">
        Back to <Link to="/">Login</Link>
      </p>
    </div>
  );
}

