// Focused check of an already-running, isolated Windows packaged app.
// Launch with the path/network isolation documented in the validation record.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { spawn } = require("node:child_process");
const { createRequire } = require("node:module");
const requireWeb = createRequire(path.resolve(__dirname, "../../apps/desktop-web/package.json"));
const { chromium } = requireWeb("playwright");

const [cdpUrl, evidenceArg, expectedSha, python, mode = "exercise"] = process.argv.slice(2);
assert(process.platform === "win32", "This validation requires Windows");
assert(cdpUrl && evidenceArg && /^[a-f0-9]{40}$/.test(expectedSha || "") && python,
  "Usage: node validate_packaged_storage.cjs <loopback-CDP-URL> <evidence-dir> <full-build-SHA> <python.exe> [exercise|restart|ui]");
assert(["exercise", "restart", "ui"].includes(mode), "Unknown mode");
assert.equal(new URL(cdpUrl).hostname, "127.0.0.1");
const evidenceDir = path.resolve(evidenceArg);
const dataRoot = path.join(evidenceDir, "fixture");
for (let cursor = dataRoot; ; cursor = path.dirname(cursor)) {
  if (fs.existsSync(cursor)) assert(!fs.lstatSync(cursor).isSymbolicLink(), "Symlink/reparse data roots are not allowed");
  if (path.dirname(cursor) === cursor) break;
}
const snapshot = path.join(dataRoot, "metadata/storage_inventory_v1.json");
const temporary = `${snapshot}.tmp`;
const results = { status: "running", mode, expected_sha: expectedSha, started_utc: new Date().toISOString(), scans: [] };
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const hash = file => crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
const readSnapshot = () => JSON.parse(fs.readFileSync(snapshot, "utf8"));
const equalPath = (a, b) => path.resolve(a).toLowerCase() === path.resolve(b).toLowerCase();

async function until(check, message, timeout = 15000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const value = await check();
    if (value) return value;
    await sleep(10);
  }
  throw new Error(message);
}

async function holdSnapshot() {
  // Python's Windows rb handle does not grant FILE_SHARE_DELETE.
  // EOF also releases it if the harness exits unexpectedly.
  const child = spawn(python, ["-u", "-c",
    "import sys\nwith open(sys.argv[1], 'rb') as reader:\n print('locked', flush=True)\n sys.stdin.readline()",
    snapshot], { windowsHide: true, stdio: ["pipe", "pipe", "pipe"] });
  let output = "";
  let error = "";
  child.stdout.on("data", chunk => { output += chunk; });
  child.stderr.on("data", chunk => { error += chunk; });
  const release = async () => {
    child.stdin.end("release\n");
    await until(() => child.exitCode !== null, "Lock helper did not exit");
    assert.equal(child.exitCode, 0, error);
  };
  try {
    await until(() => {
      if (child.exitCode !== null) throw new Error(`Lock helper failed: ${error}`);
      return output.includes("locked");
    }, "Lock helper did not become ready");
    return { release };
  } catch (error) {
    child.stdin.end();
    throw error;
  }
}

async function main() {
  let browser;
  let held;
  try {
    browser = await chromium.connectOverCDP(cdpUrl);
    const page = browser.contexts()[0].pages()[0];
    await page.waitForFunction(() => typeof window.pywebview?.api?.get_app_status === "function");
    const call = (method, params = {}) => page.evaluate(
      async ({ method, params }) => window.pywebview.api[method](params), { method, params });
    const identity = await call("get_app_status");
    assert(!identity.error, JSON.stringify(identity));
    assert.equal(identity.runtime.frozen, true);
    assert.equal(identity.runtime.version, "0.30.0-rc.1");
    assert(expectedSha.startsWith(identity.runtime.build_commit) && identity.runtime.build_commit.length >= 7);
    assert(equalPath(identity.paths.data.path, dataRoot), "App does not use the isolated fixture");
    for (const [key, item] of Object.entries(identity.paths)) {
      const relative = path.relative(dataRoot, item.path);
      assert(!relative.startsWith("..") && !path.isAbsolute(relative), `Runtime path escapes fixture: ${key}`);
    }
    results.runtime = identity.runtime;
    results.paths = identity.paths;
    const start = async () => {
      const result = await call("start_storage_inventory_scan");
      assert.equal(result.started, true, JSON.stringify(result));
      return result.scan_status.scan_id;
    };
    const finish = async scanId => until(async () => {
      const state = await call("get_storage_inventory_scan_status");
      assert.equal(state.scan_id, scanId);
      return state.status !== "running" ? state : null;
    }, "Inventory scan did not finish");
    const success = state => assert(["succeeded", "partial"].includes(state.status), JSON.stringify(state));

    if (mode === "ui") {
      await page.evaluate(() => { window.location.hash = "#/settings/storage"; });
      const refresh = page.getByRole("button", { name: "Refresh inventory", exact: true });
      const failure = page.getByRole("alert").filter({ hasText: "Storage scan failed" });
      const summary = page.locator("article").filter({ has: page.getByRole("heading", { name: "Storage Summary", exact: true }) });
      const metric = label => summary.getByText(label, { exact: true }).locator("..").innerText();
      const ready = async () => until(async () =>
        await refresh.isVisible() && await refresh.isEnabled(),
      "UI did not restore the enabled Refresh inventory button");
      const uiStart = async () => {
        await ready();
        const previous = await call("get_storage_inventory_scan_status");
        await refresh.click();
        const state = await until(async () => {
          const current = await call("get_storage_inventory_scan_status");
          return current.scan_id && current.scan_id !== previous.scan_id ? current : null;
        }, "UI click did not start a new storage scan");
        return state.scan_id;
      };
      const uiFinish = async scanId => {
        const state = await finish(scanId);
        await ready();
        assert.equal(await page.getByRole("button", { name: "Scanning...", exact: true }).count(), 0);
        results.scans.push(state);
        return state;
      };
      const screenshot = async name => {
        await summary.scrollIntoViewIfNeeded();
        await page.screenshot({ path: path.join(evidenceDir, `storage-ui-${name}.png`) });
      };

      await ready();
      const normal = await uiFinish(await uiStart());
      success(normal);
      assert.equal(readSnapshot().scan_status.scan_id, normal.scan_id);
      assert.equal(await failure.count(), 0);
      await screenshot("normal");
      results.normal = { scan_status: normal, button_enabled: true };

      const previousSnapshot = readSnapshot();
      const previousHash = hash(snapshot);
      const previousMetrics = { local_data: await metric("Local data"), files: await metric("Files") };
      held = await holdSnapshot();
      const failed = await uiFinish(await uiStart());
      assert.equal(failed.status, "failed", JSON.stringify(failed));
      assert.match(failed.error, /WinError (5|32|33)/);
      await failure.waitFor({ state: "visible" });
      const failureText = await failure.innerText();
      assert(failureText.includes(failed.error), "UI omitted the real worker error");
      assert.match(failureText, /cached|previous|last successful/i, "UI did not identify the preserved snapshot");
      assert.equal(hash(snapshot), previousHash);
      const cached = await call("get_storage_inventory");
      assert.equal(cached.scanned_at, previousSnapshot.scanned_at);
      assert.equal(await metric("Local data"), previousMetrics.local_data);
      assert.equal(await metric("Files"), previousMetrics.files);
      await screenshot("failed");
      results.persistent = {
        scan_status: failed, button_enabled: true, failure_text: failureText,
        prior_snapshot_sha256: previousHash, cached_metrics: previousMetrics,
      };
      await held.release(); held = null;

      const recovered = await uiFinish(await uiStart());
      success(recovered);
      await failure.waitFor({ state: "hidden" });
      assert.equal(readSnapshot().scan_status.scan_id, recovered.scan_id);
      await screenshot("recovered");
      results.recovery = { scan_status: recovered, button_enabled: true, old_failure_cleared: true };

      const beforeTransient = hash(snapshot);
      held = await holdSnapshot();
      const transientId = await uiStart();
      await until(() => fs.existsSync(temporary), "UI-triggered writer did not reach serialization");
      const blocked = await call("get_storage_inventory_scan_status");
      assert.equal(blocked.status, "running", "Transient scan failed before the reader could release");
      assert.equal(hash(snapshot), beforeTransient);
      await held.release(); held = null;
      const transient = await uiFinish(transientId);
      success(transient);
      assert.equal(await failure.count(), 0);
      assert.equal(readSnapshot().scan_status.scan_id, transientId);
      assert(!fs.existsSync(temporary), "Unexpected pending temporary snapshot");
      await screenshot("transient");
      results.transient = {
        blocked, recovered: transient, button_enabled: true,
        previous_snapshot_preserved_while_locked: true, persistent_failure_visible: false,
      };
      results.final_snapshot_sha256 = hash(snapshot);
      results.final_scanned_at = readSnapshot().scanned_at;
    } else if (mode === "restart") {
      const previous = JSON.parse(fs.readFileSync(path.join(evidenceDir, "storage-exercise.json"), "utf8"));
      assert.equal(previous.status, "pass");
      const latest = await call("get_storage_inventory");
      assert.equal(hash(snapshot), previous.final_snapshot_sha256);
      assert.equal(latest.scanned_at, previous.final_scanned_at);
      assert.equal(latest.scan_status.status, "idle", "Restart unexpectedly rescanned");
      results.cached_snapshot = { sha256: hash(snapshot), scanned_at: latest.scanned_at, scan_status: latest.scan_status };
    } else {
      for (let index = 0; index < 20; index++) {
        const state = await finish(await start());
        success(state);
        const saved = readSnapshot();
        assert.equal(saved.scan_status.scan_id, state.scan_id);
        results.scans.push(state);
      }
      assert(!fs.existsSync(temporary), "Unexpected pending temporary snapshot");
      const beforeTransient = hash(snapshot);
      held = await holdSnapshot();
      const transientId = await start();
      await until(() => fs.existsSync(temporary), "Writer did not reach serialization");
      await sleep(50);
      const blocked = await call("get_storage_inventory_scan_status");
      assert.equal(blocked.status, "running", "Scan failed before the reader could release");
      assert.equal(hash(snapshot), beforeTransient);
      await held.release(); held = null;
      const recovered = await finish(transientId);
      success(recovered);
      assert.equal(readSnapshot().scan_status.scan_id, transientId);
      results.transient = { blocked, recovered, previous_snapshot_preserved_while_locked: true };

      const beforePermanent = hash(snapshot);
      held = await holdSnapshot();
      const failed = await finish(await start());
      assert.equal(failed.status, "failed", JSON.stringify(failed));
      assert.match(failed.error, /WinError (5|32|33)/);
      assert.equal(hash(snapshot), beforePermanent);
      const cached = await call("get_storage_inventory");
      assert.equal(cached.scan_status.status, "failed");
      assert.equal(cached.scanned_at, readSnapshot().scanned_at);
      results.persistent = { failed, prior_snapshot_sha256: beforePermanent, cached_snapshot_readable: true };
      await page.evaluate(() => { window.location.hash = "#/settings/storage"; });
      await sleep(500);
      await page.screenshot({ path: path.join(evidenceDir, "storage-locked.png") });
      await held.release(); held = null;

      const recoveredAfterFailure = await finish(await start());
      success(recoveredAfterFailure);
      assert.equal(readSnapshot().scan_status.scan_id, recoveredAfterFailure.scan_id);
      results.recovery = recoveredAfterFailure;
      results.final_snapshot_sha256 = hash(snapshot);
      results.final_scanned_at = readSnapshot().scanned_at;
      await page.reload();
      await page.waitForFunction(() => typeof window.pywebview?.api?.get_storage_inventory === "function");
      await sleep(500);
      await page.screenshot({ path: path.join(evidenceDir, "storage-recovered.png") });
    }
    results.status = "pass";
  } catch (error) {
    results.status = "failed";
    results.error = error.stack || String(error);
    process.exitCode = 1;
  } finally {
    try { if (held) await held.release(); } catch (error) { results.cleanup_error = String(error); results.status = "failed"; process.exitCode = 1; }
    if (browser) await browser.close();
    results.finished_utc = new Date().toISOString();
    fs.writeFileSync(path.join(evidenceDir, `storage-${mode}.json`), JSON.stringify(results, null, 2) + "\n");
    console.log(JSON.stringify({ status: results.status, mode, scans: results.scans.length, error: results.error }));
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
