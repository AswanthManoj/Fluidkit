import type { FunctionMeta, GroupBy } from './types';

export const state = $state({
  functions: {} as Record<string, FunctionMeta>,
  selected: null as FunctionMeta | null,
  connected: false,
  groupBy: 'file' as GroupBy,
  search: '',
  error: null as string | null,
});

export function selectFunction(fn: FunctionMeta) {
  state.selected = fn;
}
