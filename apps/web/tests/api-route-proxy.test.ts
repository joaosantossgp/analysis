import test from "node:test";
import assert from "node:assert/strict";

import { proxyJsonRoute } from "../lib/api-route-proxy.ts";

type FetchMock = typeof globalThis.fetch;

function withFetchMock(mock: FetchMock) {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = mock;

  return () => {
    globalThis.fetch = originalFetch;
  };
}

test("proxyJsonRoute returns upstream JSON with no-store headers", async () => {
  let capturedInput: RequestInfo | URL | undefined;
  const restore = withFetchMock((async (input) => {
    capturedInput = input;
    return new Response(JSON.stringify({ ok: true }), { status: 202 });
  }) as FetchMock);

  try {
    const response = await proxyJsonRoute({
      upstreamPath: "/health",
      fallbackMessage: "Falha controlada.",
    });

    assert.equal(response.status, 202);
    assert.equal(response.headers.get("cache-control"), "no-store");
    assert.match(String(capturedInput), /\/health$/);
    assert.deepEqual(await response.json(), { ok: true });
  } finally {
    restore();
  }
});

test("proxyJsonRoute posts JSON bodies to the upstream API", async () => {
  let capturedInit: RequestInit | undefined;
  const restore = withFetchMock((async (_input, init) => {
    capturedInit = init;
    return new Response(JSON.stringify({ accepted: true }), { status: 200 });
  }) as FetchMock);

  try {
    const response = await proxyJsonRoute({
      upstreamPath: "/refresh/batch",
      method: "POST",
      body: { mode: "missing" },
      fallbackMessage: "Falha controlada.",
    });

    assert.equal(response.status, 200);
    assert.equal(capturedInit?.method, "POST");
    assert.equal(capturedInit?.body, JSON.stringify({ mode: "missing" }));
    assert.equal(new Headers(capturedInit?.headers).get("content-type"), "application/json");
  } finally {
    restore();
  }
});

test("proxyJsonRoute preserves upstream detail errors", async () => {
  const restore = withFetchMock((async () =>
    new Response(
      JSON.stringify({
        detail: {
          code: "invalid_request",
          message: "Intervalo invalido.",
        },
      }),
      { status: 422 },
    )) as FetchMock);

  try {
    const response = await proxyJsonRoute({
      upstreamPath: "/base-health",
      fallbackMessage: "Falha controlada.",
    });

    assert.equal(response.status, 422);
    assert.deepEqual(await response.json(), {
      error: {
        code: "invalid_request",
        message: "Intervalo invalido.",
      },
    });
  } finally {
    restore();
  }
});

test("proxyJsonRoute maps network and invalid JSON failures", async () => {
  let restore = withFetchMock((async () => {
    throw new TypeError("fetch failed");
  }) as FetchMock);

  try {
    const response = await proxyJsonRoute({
      upstreamPath: "/health",
      fallbackMessage: "Falha controlada.",
      networkMessage: "Nao foi possivel conectar a API da V2.",
    });

    assert.equal(response.status, 503);
    assert.deepEqual(await response.json(), {
      error: {
        code: "network_error",
        message: "Nao foi possivel conectar a API da V2.",
      },
    });
  } finally {
    restore();
  }

  restore = withFetchMock((async () => new Response("not-json", { status: 200 })) as FetchMock);

  try {
    const response = await proxyJsonRoute({
      upstreamPath: "/health",
      fallbackMessage: "Falha controlada.",
      invalidResponseMessage: "Resposta invalida.",
    });

    assert.equal(response.status, 502);
    assert.deepEqual(await response.json(), {
      error: {
        code: "invalid_response",
        message: "Resposta invalida.",
      },
    });
  } finally {
    restore();
  }
});
