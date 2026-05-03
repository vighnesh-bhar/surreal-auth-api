import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { logout } from "../services/api";
import { refreshAuthToken } from "../services/api";

export default function Dashboard() {
  const navigate = useNavigate();
  const [error, setError] = useState("");

  useEffect(() => {
    if (!localStorage.getItem("access_token")) {
      navigate("/");
    }
  }, [navigate]);

  const handleLogout = async () => {
    const refreshToken = localStorage.getItem("refresh_token");
    setError("");

    try {
      if (refreshToken) {
        await logout(refreshToken);
      }
    } catch (err) {
      setError(err.message || "Unable to log out cleanly.");
    } finally {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      navigate("/");
    }
  };

  const handleRefreshToken = async () => {
    const refreshToken = localStorage.getItem("refresh_token");
    setError("");

    try {
        if (refreshToken) {
          const res = await refreshAuthToken(refreshToken);
          localStorage.setItem("access_token", res.access_token);
          localStorage.setItem("refresh_token", res.refresh_token);
        }
    }catch (err) {
        setError(err.message || "Unable to refresh token.");
    }finally {

    }
  };

  return (
    <div className="container">
      <h2>Dashboard</h2>
      <p>You are logged in</p>
      <button onClick={handleRefreshToken}>Refresh Token</button>
      <button onClick={handleLogout}>Logout</button>
      {error ? <p className="error">{error}</p> : null}
    </div>
  );
}