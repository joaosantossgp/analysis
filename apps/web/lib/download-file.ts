"use client";

import { ApiClientError } from "./api.ts";
import {
  bridgeDownloadCompanyExcel,
  bridgeSaveCompanyExcel,
  isDesktopMode,
} from "./desktop-bridge.ts";

type ApiErrorShape = {
  error?: {
    code?: string;
    message?: string;
  };
};

export function getFilenameFromDisposition(
  contentDisposition: string | null,
  fallbackFilename: string,
): string {
  if (!contentDisposition) {
    return fallbackFilename;
  }

  const utfMatch = contentDisposition.match(/filename\*\s*=\s*UTF-8''([^;]+)/i);
  if (utfMatch?.[1]) {
    try {
      return decodeURIComponent(utfMatch[1]);
    } catch {
      return utfMatch[1];
    }
  }

  const quotedMatch = contentDisposition.match(/filename\s*=\s*"([^"]+)"/i);
  if (quotedMatch?.[1]) {
    return quotedMatch[1];
  }

  const bareMatch = contentDisposition.match(/filename\s*=\s*([^;]+)/i);
  if (bareMatch?.[1]) {
    return bareMatch[1].trim();
  }

  return fallbackFilename;
}

async function toDownloadError(response: Response): Promise<ApiClientError> {
  let payload: ApiErrorShape | null = null;

  try {
    payload = (await response.json()) as ApiErrorShape;
  } catch {
    payload = null;
  }

  const code = payload?.error?.code ?? "unknown_error";
  const message = payload?.error?.message;

  if (response.status === 404) {
    return new ApiClientError(
      message ?? "O recurso solicitado nao foi encontrado.",
      response.status,
      code ?? "not_found",
    );
  }

  if (response.status === 422) {
    return new ApiClientError(
      message ?? "A requisicao enviada para download nao foi aceita.",
      response.status,
      code ?? "invalid_request",
    );
  }

  if (response.status >= 500) {
    return new ApiClientError(
      message ?? "A API da V2 nao conseguiu preparar o download agora.",
      response.status,
      code ?? "upstream_unavailable",
    );
  }

  return new ApiClientError(
    message ?? `Falha ao preparar download (${response.status}).`,
    response.status,
    code,
  );
}

export async function downloadFile(
  endpoint: string,
  fallbackFilename: string,
): Promise<string> {
  const bridgeDownloaded = await tryDesktopBridgeDownload(endpoint);
  if (bridgeDownloaded) {
    return bridgeDownloaded;
  }

  let response: Response;

  try {
    response = await fetch(endpoint, {
      method: "GET",
      cache: "no-store",
    });
  } catch {
    throw new ApiClientError(
      "Nao foi possivel conectar a API da V2.",
      503,
      "network_error",
    );
  }

  if (!response.ok) {
    throw await toDownloadError(response);
  }

  const blob = await response.blob();
  const filename = getFilenameFromDisposition(
    response.headers.get("content-disposition"),
    fallbackFilename,
  );
  const objectUrl = URL.createObjectURL(blob);

  try {
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = filename;
    anchor.style.display = "none";
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
  } finally {
    window.setTimeout(() => {
      URL.revokeObjectURL(objectUrl);
    }, 0);
  }

  return filename;
}

async function tryDesktopBridgeDownload(endpoint: string): Promise<string | null> {
  const companyMatch = endpoint.match(/^\/api\/companies\/(\d+)\/excel(?:\?.*)?$/);
  if (!companyMatch) {
    return null;
  }

  if (!isDesktopMode()) {
    await new Promise<void>((resolve) => {
      window.setTimeout(() => resolve(), 450);
    });
  }
  if (!isDesktopMode()) {
    return null;
  }

  if (companyMatch) {
    const cdCvm = Number(companyMatch[1]);
    try {
      const saved = await bridgeSaveCompanyExcel(cdCvm, { reveal: true });
      if (saved?.filename) {
        return saved.filename;
      }
    } catch {
      // Fallback to legacy browser-based download for environments where
      // native save bridge methods are not available.
    }
    const payload = await bridgeDownloadCompanyExcel(cdCvm);
    return downloadBase64Payload(payload.content_base64, payload.mime_type, payload.filename);
  }

  return null;
}

function base64ToUint8Array(value: string): Uint8Array {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let idx = 0; idx < binary.length; idx += 1) {
    bytes[idx] = binary.charCodeAt(idx);
  }
  return bytes;
}

function downloadBase64Payload(
  contentBase64: string,
  mimeType: string,
  filename: string,
): string {
  if (!contentBase64 || typeof contentBase64 !== "string") {
    throw new ApiClientError(
      "O desktop nao retornou o conteudo do arquivo para download.",
      500,
      "invalid_download_payload",
    );
  }
  const bytes = base64ToUint8Array(contentBase64);
  const arrayBuffer = bytes.buffer.slice(
    bytes.byteOffset,
    bytes.byteOffset + bytes.byteLength,
  ) as ArrayBuffer;
  const blob = new Blob([arrayBuffer], { type: mimeType || "application/octet-stream" });
  const objectUrl = URL.createObjectURL(blob);

  try {
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = filename;
    anchor.style.display = "none";
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
  } finally {
    window.setTimeout(() => {
      URL.revokeObjectURL(objectUrl);
    }, 0);
  }

  return filename;
}
