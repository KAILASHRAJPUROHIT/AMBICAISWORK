import { proxyMdm } from '../api/_lib/mdm-gateway';

export async function GET(request: Request): Promise<Response> {
  return proxyMdm(request);
}

export const POST = proxyMdm;
export const PUT = proxyMdm;
export const PATCH = proxyMdm;
export const DELETE = proxyMdm;
export const HEAD = proxyMdm;
