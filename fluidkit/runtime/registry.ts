const _registry = new Map<string, Function>();

export function registerRemoteFunction(key: string, fn: Function): void {
  _registry.set(key, fn);
}

export function getRemoteFunction(key: string): Function | undefined {
  return _registry.get(key);
}
