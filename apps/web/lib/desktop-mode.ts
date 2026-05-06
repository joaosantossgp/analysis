export function isDesktopServerMode(
  env: { [key: string]: string | undefined } = process.env,
): boolean {
  return env.ANALISYS_DESKTOP_MODE === "1";
}
