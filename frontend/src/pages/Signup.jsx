import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { signup } from "../services/api";

export default function Signup() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setMessage("");

    try {
      await signup({ name, email, password });
      setMessage("Signup successful. Please check your email to verify your account.");
      setTimeout(() => navigate("/"), 1200);
    } catch (err) {
      setError(err.message || "Unable to sign up.");
    }
  };

  return (
    <div className="container">
      <h2>Sign Up</h2>
      <form onSubmit={handleSubmit}>
        <input
          placeholder="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
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
        <button type="submit">Create account</button>
      </form>
      {error ? <p className="error">{error}</p> : null}
      {message ? <p className="success">{message}</p> : null}
      <p className="link">
        Already have an account? <Link to="/">Log in</Link>
      </p>
    </div>
  );
}