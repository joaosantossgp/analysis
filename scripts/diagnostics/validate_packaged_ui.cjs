const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");

function parseArgs(argv) {
  const expected = new Set(["--cdp-url", "--output-dir", "--cd-cvm", "--process-start-ms"]);
  const values = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!expected.has(key) || value === undefined || values[key] !== undefined) {
      throw new Error("Expected exactly --cdp-url, --output-dir, --cd-cvm, and --process-start-ms");
    }
    values[key] = value;
  }
  if (Object.keys(values).length !== expected.size) {
    throw new Error("Missing required CDP harness arguments");
  }
  return {
    cdpUrl: values["--cdp-url"],
    outputDir: path.resolve(values["--output-dir"]),
    cdCvm: Number(values["--cd-cvm"]),
    processStartMs: Number(values["--process-start-ms"]),
  };
}

function writeJson(filePath, value) {
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function isAllowedRequest(url) {
  return /^(?:file:|data:|blob:|http:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?\/)/.test(url);
}

function topLevelError(result) {
  return result && typeof result === "object" && Object.prototype.hasOwnProperty.call(result, "error");
}

async function waitForUiSettling(page) {
  await page.evaluate(
    () =>
      new Promise((resolve) => {
        requestAnimationFrame(() => requestAnimationFrame(resolve));
      }),
  );
  await page.waitForLoadState("networkidle", { timeout: 5_000 }).catch(() => undefined);
  await page.waitForTimeout(250);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!Number.isInteger(args.cdCvm) || !Number.isFinite(args.processStartMs)) {
    throw new Error("--cd-cvm and --process-start-ms must be numeric");
  }
  fs.mkdirSync(args.outputDir, { recursive: true });

  const repoRoot = path.resolve(__dirname, "..", "..");
  const repositoryRequire = createRequire(path.join(repoRoot, "apps", "desktop-web", "package.json"));
  const { chromium } = repositoryRequire("playwright");
  const consoleLogs = [];
  const networkLogs = [];
  const externalSuccesses = [];
  const pageErrors = [];
  let browser;

  try {
    browser = await chromium.connectOverCDP(args.cdpUrl);
    const context = browser.contexts()[0];
    const page = context
      .pages()
      .find((candidate) => !candidate.url().startsWith("devtools://"));
    if (!page) throw new Error("No pywebview page is available through CDP");

    page.on("console", (message) => {
      if (message.type() === "error") {
        consoleLogs.push({ type: message.type(), text: message.text(), location: message.location() });
      }
    });
    page.on("pageerror", (error) => pageErrors.push(error.message));
    page.on("request", (request) => {
      if (!isAllowedRequest(request.url())) networkLogs.push({ event: "request", url: request.url(), method: request.method() });
    });
    page.on("response", (response) => {
      if (!isAllowedRequest(response.url())) {
        const entry = { event: "response", url: response.url(), status: response.status(), ok: response.ok() };
        networkLogs.push(entry);
        if (response.ok()) externalSuccesses.push(entry);
      }
    });
    page.on("requestfailed", (request) => {
      if (!isAllowedRequest(request.url())) networkLogs.push({ event: "failed", url: request.url(), failure: request.failure() });
    });

    await page.waitForFunction(
      () => typeof window.pywebview?.api?.get_app_status === "function",
      undefined,
      { timeout: 60_000 },
    );
    const bridgeReadyMs = Date.now() - args.processStartMs;
    const bridgeResults = {};
    const calls = {
      get_app_status: {},
      get_companies: { page: 1, page_size: 20 },
      get_company_info: { cd_cvm: args.cdCvm },
      get_company_financial_readiness: { cd_cvm: args.cdCvm },
      get_sin_kpi_dashboard: {},
      export_company_excel: { cd_cvm: args.cdCvm, reveal: false, period_scope: "last_5_years" },
    };
    for (const [method, params] of Object.entries(calls)) {
      const startedAt = Date.now();
      const result = await page.evaluate(
        async ({ methodName, methodParams }) => window.pywebview.api[methodName](methodParams),
        { methodName: method, methodParams: params },
      );
      bridgeResults[method] = {
        result,
        utf8_json_bytes: Buffer.byteLength(JSON.stringify(result), "utf8"),
        duration_ms: Date.now() - startedAt,
      };
      if (topLevelError(result)) throw new Error(`Bridge result contains top-level error: ${method}`);
    }
    const exported = bridgeResults.export_company_excel.result;
    if (!exported?.ok || !exported.file_path) throw new Error("Excel export did not return ok: true and file_path");

    const client = await context.newCDPSession(page);
    const routes = ["#/empresas", `#/empresas/${args.cdCvm}`, "#/indicators?section=energy&sub=sin", "#/settings/diagnostics"];
    const viewports = [
      { width: 1366, height: 768, label: "1366x768" },
      { width: 1920, height: 1080, label: "1920x1080" },
    ];
    const screenshots = [];
    for (const route of routes) {
      await page.evaluate((hash) => {
        window.location.hash = hash;
      }, route);
      await waitForUiSettling(page);
      if (pageErrors.length) throw new Error(`Route rendered an uncaught error: ${route}`);
      for (const viewport of viewports) {
        await client.send("Emulation.setDeviceMetricsOverride", {
          width: viewport.width,
          height: viewport.height,
          deviceScaleFactor: 1,
          mobile: false,
        });
        const filePath = path.join(args.outputDir, `${route.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "")}-${viewport.label}.png`);
        await page.screenshot({ path: filePath, fullPage: true });
        screenshots.push(filePath);
      }
    }
    await client.send("Emulation.clearDeviceMetricsOverride");
    if (externalSuccesses.length) throw new Error(`Unexpected external request succeeded: ${externalSuccesses[0].url}`);

    writeJson(path.join(args.outputDir, "console-errors.json"), consoleLogs);
    writeJson(path.join(args.outputDir, "network-log.json"), networkLogs);
    writeJson(path.join(args.outputDir, "ui-results.json"), {
      cdp_url: args.cdpUrl,
      bridge_ready_elapsed_ms: bridgeReadyMs,
      bridge_results: bridgeResults,
      routes,
      screenshots,
      console_errors: consoleLogs.length,
      external_network_events: networkLogs.length,
    });
  } finally {
    if (browser) await browser.close();
  }
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
