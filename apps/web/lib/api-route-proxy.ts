import { NextResponse } from "next/server.js";

import { buildApiUrl } from "./api.ts";

export type ProxyErrorPayload = {
  error?: {
    code?: string;
    message?: string;
  };
  detail?:
    | {
        code?: string;
        message?: string;
      }
    | string;
};

type FallbackMessage = string | ((status: number) => string);

type ProxyJsonRouteOptions = {
  upstreamPath: string;
  method?: string;
  body?: unknown;
  headers?: HeadersInit;
  fallbackMessage: FallbackMessage;
  networkMessage?: string;
  invalidResponseMessage?: string;
};

const NO_STORE_HEADERS = { "cache-control": "no-store" };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function buildProxyErrorResponse(
  status: number,
  payload: ProxyErrorPayload | null,
  fallbackMessage: string,
) {
  const detailCode =
    isRecord(payload?.detail) && typeof payload.detail.code === "string"
      ? payload.detail.code
      : undefined;
  const detailMessage =
    isRecord(payload?.detail) && typeof payload.detail.message === "string"
      ? payload.detail.message
      : typeof payload?.detail === "string"
        ? payload.detail
        : undefined;
  const code = payload?.error?.code ?? detailCode ?? "unknown_error";
  const message = payload?.error?.message ?? detailMessage ?? fallbackMessage;

  return NextResponse.json(
    { error: { code, message } },
    { status, headers: NO_STORE_HEADERS },
  );
}

export async function proxyJsonRoute({
  upstreamPath,
  method = "GET",
  body,
  headers,
  fallbackMessage,
  networkMessage = "Nao foi possivel conectar a API.",
  invalidResponseMessage = "A API retornou um corpo invalido.",
}: ProxyJsonRouteOptions) {
  let upstream: Response;
  const requestHeaders = new Headers(headers);
  requestHeaders.set("Accept", "application/json");
  if (body !== undefined && !requestHeaders.has("Content-Type")) {
    requestHeaders.set("Content-Type", "application/json");
  }

  try {
    upstream = await fetch(buildApiUrl(upstreamPath), {
      method,
      cache: "no-store",
      headers: requestHeaders,
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });
  } catch {
    return NextResponse.json(
      { error: { code: "network_error", message: networkMessage } },
      { status: 503, headers: NO_STORE_HEADERS },
    );
  }

  if (!upstream.ok) {
    let payload: ProxyErrorPayload | null = null;
    try {
      payload = (await upstream.json()) as ProxyErrorPayload;
    } catch {
      payload = null;
    }
    const resolvedFallback =
      typeof fallbackMessage === "function"
        ? fallbackMessage(upstream.status)
        : fallbackMessage;
    return buildProxyErrorResponse(upstream.status, payload, resolvedFallback);
  }

  let payload: unknown;
  try {
    payload = await upstream.json();
  } catch {
    return NextResponse.json(
      { error: { code: "invalid_response", message: invalidResponseMessage } },
      { status: 502, headers: NO_STORE_HEADERS },
    );
  }

  return NextResponse.json(payload, {
    status: upstream.status,
    headers: NO_STORE_HEADERS,
  });
}
