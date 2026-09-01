import type { AuthSession, User } from "../types";
import { encryptChallengePayload, encryptLoginPassword, type LoginChallenge } from "../utils/loginCrypto";
import { authStore } from "./auth-store";
import { req } from "./client";

export const authApi = {
  getLoginChallenge: () => req<LoginChallenge>("/auth/login-challenge"),
  login: async (body: { username: string; password: string }) => {
    const challenge = await req<LoginChallenge>("/auth/login-challenge");
    const encrypted_password = await encryptLoginPassword(challenge, body.password);
    return req<AuthSession>("/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: body.username,
        challenge_id: challenge.challenge_id,
        encrypted_password,
      }),
    });
  },
  register: async (body: {
    username: string;
    password: string;
    display_name?: string | null;
    email?: string | null;
  }) => {
    const challenge = await req<LoginChallenge>("/auth/login-challenge");
    const encrypted_password = await encryptLoginPassword(challenge, body.password);
    return req<AuthSession>("/auth/register", {
      method: "POST",
      body: JSON.stringify({
        username: body.username,
        display_name: body.display_name ?? null,
        email: body.email ?? null,
        challenge_id: challenge.challenge_id,
        encrypted_password,
      }),
    });
  },
  logout: () => req<{ ok: boolean }>("/auth/logout", { method: "POST" }),
  me: () => req<User>("/auth/me"),
  updateProfile: (body: { display_name?: string | null; email?: string | null }) =>
    req<User>("/auth/me", { method: "PATCH", body: JSON.stringify(body) }),
  changePassword: async (body: { current_password: string; new_password: string }) => {
    const authOpts = { clearTokenOn401: false } as const;
    const challenge = await req<LoginChallenge>("/auth/login-challenge", undefined, authOpts);
    const encrypted_payload = await encryptChallengePayload(challenge, {
      current_password: body.current_password,
      new_password: body.new_password,
    });
    const session = await req<AuthSession>(
      "/auth/change-password",
      {
        method: "POST",
        body: JSON.stringify({ challenge_id: challenge.challenge_id, encrypted_payload }),
      },
      authOpts,
    );
    authStore.setToken(session.access_token);
    return session;
  },
};
