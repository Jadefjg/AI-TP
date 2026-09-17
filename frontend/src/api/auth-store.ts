import type { User } from "../types";

const TOKEN_KEY = "ai-tp-access-token";
const USER_KEY = "ai-tp-current-user";

const readUser = (): User | null => {
  try {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as User;
    if (!parsed || typeof parsed !== "object" || typeof parsed.username !== "string") {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
};

export const authStore = {
  getToken: () => localStorage.getItem(TOKEN_KEY),
  getUser: (): User | null => (authStore.getToken() ? readUser() : null),
  setToken: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  setUser: (user: User) => localStorage.setItem(USER_KEY, JSON.stringify(user)),
  setSession: (token: string, user: User) => {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  },
  clear: () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  },
};
