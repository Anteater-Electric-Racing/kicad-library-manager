/** Narrow bridge to the Mac window; browser development remains supported. */
type CloseState = { dirty: boolean; busy: boolean };
type DesktopWindow = Window & {
  webkit?: {
    messageHandlers?: { manager?: { postMessage: (message: unknown) => void } };
  };
  managerCloseState?: () => CloseState;
};
const guards = new Map<string, CloseState>();
let requests = 0;
const host = window as DesktopWindow;
export const isDesktop = () => !!host.webkit?.messageHandlers?.manager;
export function desktopMessage(message: unknown) {
  host.webkit?.messageHandlers?.manager?.postMessage(message);
}
host.managerCloseState = () => ({
  dirty: [...guards.values()].some((value) => value.dirty),
  busy: requests > 0 || [...guards.values()].some((value) => value.busy),
});
function publish() {
  desktopMessage({ type: "state", ...host.managerCloseState!() });
}
export function closeGuard(name: string, state?: CloseState) {
  if (state) guards.set(name, state);
  else guards.delete(name);
  publish();
}
export function requestStarted() {
  requests++;
  publish();
}
export function requestFinished() {
  requests = Math.max(0, requests - 1);
  publish();
}

type NativeResponse = { id: string; value?: unknown; error?: string };
const replies = new Map<
  string,
  { resolve: (value: any) => void; reject: (error: Error) => void }
>();
(host as any).managerNativeResponse = (response: NativeResponse) => {
  const reply = replies.get(response.id);
  if (!reply) return;
  replies.delete(response.id);
  if (response.error) reply.reject(new Error(response.error));
  else reply.resolve(response.value);
};
export function nativeRequest<T>(type: string, value?: string): Promise<T> {
  const id = crypto.randomUUID();
  return new Promise<T>((resolve, reject) => {
    replies.set(id, { resolve, reject });
    desktopMessage({ type, id, value });
  });
}
export const readClipboard = () =>
  isDesktop()
    ? nativeRequest<string>("read-clipboard")
    : navigator.clipboard.readText();
export const writeClipboard = (value: string) =>
  isDesktop()
    ? nativeRequest<void>("write-clipboard", value)
    : navigator.clipboard.writeText(value);
