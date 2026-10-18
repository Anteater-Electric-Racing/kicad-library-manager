import { requestStarted, requestFinished } from "./desktop";
const fragment = new URLSearchParams(location.hash.slice(1));
if (fragment.get("token")) {
  sessionStorage.setItem("library-token", fragment.get("token")!);
  history.replaceState(null, "", location.pathname);
}
export const token = () => sessionStorage.getItem("library-token") || "";
export async function api<T = any>(path: string, data?: unknown): Promise<T> {
  if (data !== undefined) requestStarted();
  try {
    const result = await fetch(`/api/${path}`, {
      method: data === undefined ? "GET" : "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Library-Token": token(),
      },
      body: data === undefined ? undefined : JSON.stringify(data),
    });
    const body = await result.json();
    if (!result.ok) throw new Error(body.error || "Request failed");
    return body;
  } finally {
    if (data !== undefined) requestFinished();
  }
}
export function assetURL(path: string, params: Record<string, string>) {
  return `/api/${path}?${new URLSearchParams({ ...params, token: token() })}`;
}
export type Part = Record<string, string> & { recipe?: any };
export type Library = {
  name: string;
  id: string;
  path: string;
  revision: string;
  parts: Part[];
  categories: string[];
  recoveryNeeded: boolean;
  pathIssues?: (
    string | { message?: string; partID?: string; path?: string }
  )[];
};
export type Transform = { offset: number[]; rotate: number[]; scale: number[] };
export const identity = (): Transform => ({
  offset: [0, 0, 0],
  rotate: [0, 0, 0],
  scale: [1, 1, 1],
});
