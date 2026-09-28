import {
  generateAuthenticationOptions,
  generateRegistrationOptions,
  verifyAuthenticationResponse,
  verifyRegistrationResponse,
  type AuthenticationResponseJSON,
  type RegistrationResponseJSON,
} from "@simplewebauthn/server";
import { and, eq, gt } from "drizzle-orm";
import { getReadyDb } from "../../../db";
import { webauthnChallenges, webauthnCredentials } from "../../../db/schema";

const MAX_CREDENTIALS = 2;
const TTL_MS = 5 * 60 * 1000;
const COOKIE_PREFIX = "ais_webauthn_";

type Purpose = "login" | "assertion" | "registration";

function nowIso() {
  return new Date().toISOString();
}

function randomId() {
  return crypto.randomUUID().replaceAll("-", "");
}

function toBase64url(bytes: Uint8Array) {
  let value = "";
  for (const byte of bytes) value += String.fromCharCode(byte);
  return btoa(value).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

function fromBase64url(value: string) {
  const normalized = value.replaceAll("-", "+").replaceAll("_", "/");
  const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
  const binary = atob(padded);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

function webauthnConfig() {
  const rpID = process.env.AIS_WEBAUTHN_RP_ID || "";
  const origin = process.env.AIS_WEBAUTHN_ORIGIN || "";
  if (!rpID || !origin) throw new Error("WebAuthn requires AIS_WEBAUTHN_RP_ID and AIS_WEBAUTHN_ORIGIN.");
  return { rpID, origin };
}

export function webauthnEnabled() {
  return process.env.AIS_WEBAUTHN_ENABLED === "true";
}

export function challengeCookie(purpose: Purpose, id: string) {
  return `${COOKIE_PREFIX}${purpose}=${id}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=300`;
}

export function clearChallengeCookie(purpose: Purpose) {
  return `${COOKIE_PREFIX}${purpose}=; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=0`;
}

function readCookie(request: Request, purpose: Purpose) {
  const key = `${COOKIE_PREFIX}${purpose}=`;
  const cookie = request.headers.get("cookie") || "";
  return cookie.split(";").map((value) => value.trim()).find((value) => value.startsWith(key))?.slice(key.length) || null;
}

async function createChallenge(purpose: Purpose, challenge = randomId()) {
  const id = randomId();
  const db = await getReadyDb();
  await db.insert(webauthnChallenges).values({
    id,
    purpose,
    challenge,
    expiresAt: new Date(Date.now() + TTL_MS).toISOString(),
  });
  return { id, challenge };
}

async function consumeChallenge(request: Request, purpose: Purpose) {
  const id = readCookie(request, purpose);
  if (!id) return null;
  const db = await getReadyDb();
  const [row] = await db
    .select()
    .from(webauthnChallenges)
    .where(and(eq(webauthnChallenges.id, id), eq(webauthnChallenges.purpose, purpose), gt(webauthnChallenges.expiresAt, nowIso())))
    .limit(1);
  await db.delete(webauthnChallenges).where(eq(webauthnChallenges.id, id));
  return row || null;
}

async function requireLoginGrant(request: Request) {
  const id = readCookie(request, "login");
  if (!id) return false;
  const db = await getReadyDb();
  const [row] = await db
    .select()
    .from(webauthnChallenges)
    .where(and(eq(webauthnChallenges.id, id), eq(webauthnChallenges.purpose, "login"), gt(webauthnChallenges.expiresAt, nowIso())))
    .limit(1);
  return Boolean(row);
}

export async function credentialCount() {
  const db = await getReadyDb();
  return (await db.select().from(webauthnCredentials)).length;
}

export async function createLoginGrant() {
  const { id } = await createChallenge("login");
  return challengeCookie("login", id);
}

export async function registrationOptions() {
  const config = webauthnConfig();
  const db = await getReadyDb();
  const credentials = await db.select().from(webauthnCredentials);
  if (credentials.length >= MAX_CREDENTIALS) throw new Error("Maximum of two AIS passkeys already enrolled.");
  const { id, challenge } = await createChallenge("registration");
  const options = await generateRegistrationOptions({
    rpName: "AIS — Aradhana Intelligence System",
    rpID: config.rpID,
    userName: "ais-admin",
    userDisplayName: "AIS Administrator",
    challenge,
    attestationType: "none",
    excludeCredentials: credentials.map((credential) => ({ id: credential.id, transports: JSON.parse(credential.transports) })),
    authenticatorSelection: { authenticatorAttachment: "platform", residentKey: "required", userVerification: "required" },
  });
  return { options, cookie: challengeCookie("registration", id) };
}

export async function verifyRegistration(request: Request, response: RegistrationResponseJSON, label: string) {
  const pending = await consumeChallenge(request, "registration");
  if (!pending) throw new Error("Registration request expired. Start again.");
  const db = await getReadyDb();
  const credentials = await db.select().from(webauthnCredentials);
  if (credentials.length >= MAX_CREDENTIALS) throw new Error("Maximum of two AIS passkeys already enrolled.");
  const config = webauthnConfig();
  const verification = await verifyRegistrationResponse({
    response,
    expectedChallenge: pending.challenge,
    expectedOrigin: config.origin,
    expectedRPID: config.rpID,
    requireUserVerification: true,
  });
  if (!verification.verified || !verification.registrationInfo) throw new Error("Passkey registration could not be verified.");
  const info = verification.registrationInfo;
  await db.insert(webauthnCredentials).values({
    id: info.credential.id,
    label: label.trim().slice(0, 64) || "Windows Hello",
    publicKey: toBase64url(info.credential.publicKey),
    counter: info.credential.counter,
    transports: JSON.stringify(response.response.transports || []),
    deviceType: info.credentialDeviceType,
    backedUp: info.credentialBackedUp ? 1 : 0,
  });
  return { label: label.trim().slice(0, 64) || "Windows Hello", count: credentials.length + 1 };
}

export async function authenticationOptions(request: Request) {
  if (!await requireLoginGrant(request)) throw new Error("Password verification expired. Sign in again.");
  const config = webauthnConfig();
  const db = await getReadyDb();
  const credentials = await db.select().from(webauthnCredentials);
  if (!credentials.length) throw new Error("No AIS passkey is enrolled. An administrator must complete enrollment first.");
  const { id, challenge } = await createChallenge("assertion");
  const options = await generateAuthenticationOptions({
    rpID: config.rpID,
    challenge,
    userVerification: "required",
    allowCredentials: credentials.map((credential) => ({ id: credential.id, transports: JSON.parse(credential.transports) })),
  });
  return { options, cookie: challengeCookie("assertion", id) };
}

export async function verifyAuthentication(request: Request, response: AuthenticationResponseJSON) {
  const loginGrant = await requireLoginGrant(request);
  const pending = await consumeChallenge(request, "assertion");
  if (!loginGrant || !pending) throw new Error("Verification request expired. Sign in again.");
  const db = await getReadyDb();
  const [credential] = await db.select().from(webauthnCredentials).where(eq(webauthnCredentials.id, response.id)).limit(1);
  if (!credential) throw new Error("This passkey is not authorized for AIS.");
  const config = webauthnConfig();
  const verification = await verifyAuthenticationResponse({
    response,
    expectedChallenge: pending.challenge,
    expectedOrigin: config.origin,
    expectedRPID: config.rpID,
    requireUserVerification: true,
    credential: {
      id: credential.id,
      publicKey: fromBase64url(credential.publicKey),
      counter: credential.counter,
      transports: JSON.parse(credential.transports),
    },
  });
  if (!verification.verified) throw new Error("Passkey assertion could not be verified.");
  await db
    .update(webauthnCredentials)
    .set({ counter: verification.authenticationInfo.newCounter, lastUsedAt: nowIso() })
    .where(eq(webauthnCredentials.id, credential.id));
  const grantId = readCookie(request, "login");
  if (grantId) await db.delete(webauthnChallenges).where(eq(webauthnChallenges.id, grantId));
  return { label: credential.label };
}
