import { onlineManager } from "@tanstack/react-query";
import { afterEach, describe, expect, it } from "vitest";
import { queryClient } from "./query";

// Bridge calls go to the local pywebview process, not the network (#575).
describe("shared query client while the browser reports offline", () => {
  afterEach(() => {
    onlineManager.setOnline(true);
    queryClient.clear();
  });

  it("still runs bridge queries", async () => {
    onlineManager.setOnline(false);
    const result = queryClient.fetchQuery({ queryKey: ["offline-read"], queryFn: async () => 655 });
    await expect(result).resolves.toBe(655);
  });

  it("still runs bridge mutations", async () => {
    onlineManager.setOnline(false);
    const mutation = queryClient.getMutationCache().build(queryClient, { mutationFn: async () => "saved" });
    await expect(mutation.execute(undefined)).resolves.toBe("saved");
  });
});
