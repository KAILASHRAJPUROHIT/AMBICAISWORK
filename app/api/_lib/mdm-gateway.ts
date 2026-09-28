const MDM_ORIGIN = 'https://mdm.ambicdigital.in';

const forwardedRequestHeaders = [
  'accept',
  'content-type',
  'cookie',
  'x-mdmesh-console',
  'x-recovery-token',
];

const omittedResponseHeaders = new Set([
  'connection',
  'content-encoding',
  'content-length',
  'keep-alive',
  'transfer-encoding',
]);

function upstreamUrl(request: Request): URL {
  const incoming = new URL(request.url);
  const upstreamPath = incoming.pathname.replace(/^\/mdm(?=\/|$)/, '') || '/';
  return new URL(`${upstreamPath}${incoming.search}`, MDM_ORIGIN);
}

function rewriteCookiePath(cookie: string): string {
  return /;\s*Path=/i.test(cookie)
    ? cookie.replace(/;\s*Path=[^;]*/i, '; Path=/mdm')
    : `${cookie}; Path=/mdm`;
}

/**
 * Same-origin MDM gateway. The browser only sees ais.aradhanajewellers.com,
 * so the MDM JSESSIONID is a first-party cookie instead of an unreliable
 * third-party iframe cookie. The target is fixed: this is not an open proxy.
 */
export async function proxyMdm(request: Request): Promise<Response> {
  const headers = new Headers();
  for (const name of forwardedRequestHeaders) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  const init: RequestInit = {
    method: request.method,
    headers,
    redirect: 'manual',
  };
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    init.body = await request.arrayBuffer();
  }

  const upstream = await fetch(upstreamUrl(request), init);
  const responseHeaders = new Headers();
  upstream.headers.forEach((value, name) => {
    if (!omittedResponseHeaders.has(name.toLowerCase()) && name.toLowerCase() !== 'set-cookie') {
      responseHeaders.set(name, value);
    }
  });

  const cookieHeaders = (upstream.headers as Headers & { getSetCookie?: () => string[] }).getSetCookie?.()
    ?? (upstream.headers.get('set-cookie') ? [upstream.headers.get('set-cookie')!] : []);
  for (const cookie of cookieHeaders) responseHeaders.append('set-cookie', rewriteCookiePath(cookie));

  // Vinext canonicalises /mdm/ to /mdm. A base tag preserves the /mdm/
  // prefix for the MDM bundle's relative assets in either form.
  const isHtml = responseHeaders.get('content-type')?.includes('text/html');
  const body = isHtml
    ? (await upstream.text()).replace('<head>', '<head><base href="/mdm/">')
    : upstream.body;

  return new Response(body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}
