declare function importScripts(...urls: string[]): void;
declare const occtimportjs: (options?: any) => Promise<any>;
let engine: Promise<any> | undefined;
self.onmessage = async (event: MessageEvent) => {
  try {
    if (!engine) {
      importScripts("/vendor/occt-import-js.js");
      engine = occtimportjs({
        locateFile: (name: string) => "/vendor/" + name,
      });
    }
    const importer = await engine;
    const result = importer.ReadStepFile(new Uint8Array(event.data), {
      linearUnit: "millimeter",
      linearDeflectionType: "absolute_value",
      linearDeflection: 0.025,
      angularDeflection: 0.3,
    });
    if (!result.success)
      throw new Error(
        "The STEP file could not be read. Its original bytes are preserved.",
      );
    self.postMessage({ result });
  } catch (error) {
    self.postMessage({ error: String(error) });
  }
};
