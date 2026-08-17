import forge from "node-forge";

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

function resolveHashAlg(hashAlg: string): string {
  const normalized = (hashAlg || "SHA-256").trim().toUpperCase();
  if (normalized === "SHA-256" || normalized === "SHA256") return "SHA-256";
  if (normalized === "SHA-1" || normalized === "SHA1") return "SHA-1";
  return "SHA-256";
}

function hasSubtleCrypto(): boolean {
  return typeof globalThis.crypto?.subtle?.importKey === "function";
}

async function importPublicKey(spkiB64: string, hashAlg: string): Promise<CryptoKey> {
  const subtle = globalThis.crypto.subtle;
  const binary = Uint8Array.from(atob(spkiB64), (char) => char.charCodeAt(0));
  return subtle.importKey(
    "spki",
    binary,
    { name: "RSA-OAEP", hash: resolveHashAlg(hashAlg) },
    false,
    ["encrypt"],
  );
}

async function encryptWithSubtle(
  challenge: LoginChallenge,
  payload: Record<string, unknown>,
): Promise<string> {
  const publicKey = await importPublicKey(challenge.public_key, challenge.hash_alg);
  const body = new TextEncoder().encode(
    JSON.stringify({ challenge_id: challenge.challenge_id, ...payload }),
  );
  const encrypted = await globalThis.crypto.subtle.encrypt(
    { name: "RSA-OAEP" },
    publicKey,
    body,
  );
  return base64FromBytes(new Uint8Array(encrypted));
}

function forgeMdForHash(hashAlg: string) {
  const resolved = resolveHashAlg(hashAlg);
  if (resolved === "SHA-1") return forge.md.sha1.create();
  return forge.md.sha256.create();
}

/** Fallback for non-secure contexts (http://LAN-IP) where crypto.subtle is unavailable. */
function encryptWithForge(
  challenge: LoginChallenge,
  payload: Record<string, unknown>,
): string {
  const der = forge.util.decode64(challenge.public_key);
  const asn1 = forge.asn1.fromDer(der);
  const publicKey = forge.pki.publicKeyFromAsn1(asn1);
  const body = JSON.stringify({ challenge_id: challenge.challenge_id, ...payload });
  const md = forgeMdForHash(challenge.hash_alg);
  const encrypted = publicKey.encrypt(body, "RSA-OAEP", {
    md,
    mgf1: { md: forgeMdForHash(challenge.hash_alg) },
  });
  return forge.util.encode64(encrypted);
}

export async function encryptChallengePayload(
  challenge: LoginChallenge,
  payload: Record<string, unknown>,
): Promise<string> {
  if (hasSubtleCrypto()) {
    return encryptWithSubtle(challenge, payload);
  }
  // http://192.168.x.x etc. is not a Secure Context → SubtleCrypto is undefined.
  return encryptWithForge(challenge, payload);
}

export async function encryptLoginPassword(
  challenge: LoginChallenge,
  password: string,
): Promise<string> {
  return encryptChallengePayload(challenge, { password });
}
