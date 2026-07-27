export type LoginChallenge = {
  challenge_id: string;
  public_key: string;
  algorithm: string;
  hash_alg: string;
  expires_in_sec: number;
};

function base64FromBytes(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
}

async function importPublicKey(spkiB64: string, hashAlg: string): Promise<CryptoKey> {
  const binary = Uint8Array.from(atob(spkiB64), (char) => char.charCodeAt(0));
  return crypto.subtle.importKey(
    "spki",
    binary,
    { name: "RSA-OAEP", hash: hashAlg },
    false,
    ["encrypt"],
  );
}

export async function encryptChallengePayload(
  challenge: LoginChallenge,
  payload: Record<string, unknown>,
): Promise<string> {
  const publicKey = await importPublicKey(challenge.public_key, challenge.hash_alg);
  const body = new TextEncoder().encode(
    JSON.stringify({ challenge_id: challenge.challenge_id, ...payload }),
  );
  const encrypted = await crypto.subtle.encrypt({ name: "RSA-OAEP" }, publicKey, body);
  return base64FromBytes(new Uint8Array(encrypted));
}

export async function encryptLoginPassword(
  challenge: LoginChallenge,
  password: string,
): Promise<string> {
  return encryptChallengePayload(challenge, { password });
}
