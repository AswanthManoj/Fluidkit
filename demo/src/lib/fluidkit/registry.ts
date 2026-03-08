const _registry = new Map<string, Function>();

export function registerRemoteFunction(key: string, fn: Function): void {
  _registry.set(key, fn);
}

export function getRemoteFunction(key: string): Function | undefined {
  return _registry.get(key);
}

export function hasFiles(obj: unknown): boolean {
  if (obj instanceof File) return true;
  if (Array.isArray(obj)) return obj.some(hasFiles);
  if (obj && typeof obj === 'object') return Object.values(obj).some(hasFiles);
  return false;
}

export function extractFiles(
  data: unknown,
  path: string = '',
  files: Array<[string, File]> = []
): { json: unknown; files: Array<[string, File]> } {
  if (data instanceof File) {
    files.push([path, data]);
    return { json: null, files };
  }
  if (Array.isArray(data)) {
    const json: unknown[] = [];
    for (let i = 0; i < data.length; i++) {
      const key = path ? `${path}[${i}]` : `[${i}]`;
      const child = extractFiles(data[i], key, files);
      json.push(child.json);
    }
    return { json, files };
  }
  if (data && typeof data === 'object') {
    const json: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(data)) {
      const key = path ? `${path}.${k}` : k;
      const child = extractFiles(v, key, files);
      json[k] = child.json;
    }
    return { json, files };
  }
  return { json: data, files };
}
