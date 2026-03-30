import { useCallback, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/auth";
import { login as apiLogin, getMe } from "@/api/auth";

export function useAuth() {
  const { user, token, isAuthenticated, login, logout, setUser } =
    useAuthStore();
  const navigate = useNavigate();

  useEffect(() => {
    if (token && !user) {
      getMe()
        .then(setUser)
        .catch(() => {
          logout();
        });
    }
  }, [token, user, setUser, logout]);

  const handleLogin = useCallback(
    async (username: string, password: string) => {
      const response = await apiLogin({ username, password });
      login(response.access_token, response.user);
      navigate("/");
    },
    [login, navigate]
  );

  const handleLogout = useCallback(() => {
    logout();
    navigate("/login");
  }, [logout, navigate]);

  return {
    user,
    token,
    isAuthenticated,
    login: handleLogin,
    logout: handleLogout,
  };
}
