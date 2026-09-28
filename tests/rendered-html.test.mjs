import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the Aradhana Intelligence System shell", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>Aradhana Intelligence System<\/title>/i);
  assert.match(html, /Aradhana company operations, AI workforce and production command centre\./i);
  assert.match(html, /INITIALIZING OBSIDIAN CONTROL PLANE/);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape|react-loading-skeleton/i);
});

test("keeps live control-plane integrations in the dashboard", async () => {
  const [page, layout, packageJson, loginRoute, webauthn, cloudflareAccess, supervisorRoute] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
    readFile(new URL("../app/api/auth/login/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/api/_lib/webauthn.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/api/_lib/cloudflare-access.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/api/supervisor/health/route.ts", import.meta.url), "utf8"),
  ]);

  assert.match(page, /\/api\/control\/snapshot/);
  assert.match(page, /\/api\/supervisor\/chat/);
  assert.match(page, /\/api\/items/);
  assert.match(layout, /title:\s*"Aradhana Intelligence System"/);
  assert.doesNotMatch(packageJson, /react-loading-skeleton/);
  assert.doesNotMatch(page, /codex-preview|_sites-preview|SkeletonPreview/);
  assert.doesNotMatch(layout, /codex-preview|_sites-preview|SkeletonPreview/);
  assert.match(loginRoute, /requiresPasskey/);
  assert.match(webauthn, /MAX_CREDENTIALS = 2/);
  assert.match(webauthn, /requireUserVerification: true/);
  assert.doesNotMatch(webauthn, /face_image|biometric_template/i);
  assert.match(cloudflareAccess, /jwtVerify\(/);
  assert.match(cloudflareAccess, /createRemoteJWKSet/);
  assert.match(cloudflareAccess, /cf-access-jwt-assertion/);
  assert.match(cloudflareAccess, /AIS_ALLOWED_EMAILS/);
  assert.match(loginRoute, /requireCloudflareAccess/);
  assert.match(supervisorRoute, /await requireSession\(request\)/);
});
