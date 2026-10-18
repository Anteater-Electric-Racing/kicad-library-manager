export type UploadEntry = { file: File; name: string };

export async function droppedFiles(
  items: DataTransferItemList,
): Promise<UploadEntry[]> {
  // Capture every entry while the drop event still owns its data store.
  const sources = Array.from(items).map((item) => ({
    entry: (item as any).webkitGetAsEntry?.(),
    file: item.getAsFile(),
  }));
  const found: UploadEntry[] = [];
  async function walk(entry: any, prefix = "") {
    if (entry.isFile) {
      const file = await new Promise<File>((res, rej) => entry.file(res, rej));
      found.push({ file, name: prefix + file.name });
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      for (;;) {
        const batch = await new Promise<any[]>((res, rej) =>
          reader.readEntries(res, rej),
        );
        if (!batch.length) break;
        for (const e of batch) await walk(e, prefix + entry.name + "/");
      }
    }
  }
  for (const { entry, file } of sources) {
    if (entry) await walk(entry);
    else {
      if (file) found.push({ file, name: file.name });
    }
  }
  return found;
}
