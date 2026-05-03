import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { login } from "../services/api";

export default function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();

    setError("");

    try {
      const res = await login({ email, password });
      localStorage.setItem("access_token", res.access_token);
      localStorage.setItem("refresh_token", res.refresh_token);
      navigate("/dashboard");
    } catch (err) {
      setError(err.message || "Unable to log in.");
    }
  };

  return (
    <div className="container">
      <h2>Login</h2>
      <form onSubmit={handleSubmit}>
        <input
          type="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <button type="submit">Login</button>
      </form>
      {error ? <p className="error">{error}</p> : null}
      <p className="link">
        <Link to="/forgot-password">Forgot Password?</Link>
      </p>
      <p className="link">
        No account? <Link to="/signup">Create one</Link>
      </p>
    </div>
  );
}