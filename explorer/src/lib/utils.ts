import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { state } from './state.svelte';
import type { FunctionMeta } from './types';

export function cn(...inputs: ClassValue[]) {
	return twMerge(clsx(inputs));
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type WithoutChild<T> = T extends { child?: any } ? Omit<T, "child"> : T;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type WithoutChildren<T> = T extends { children?: any } ? Omit<T, "children"> : T;
export type WithoutChildrenOrChild<T> = WithoutChildren<WithoutChild<T>>;
export type WithElementRef<T, U extends HTMLElement = HTMLElement> = T & { ref?: U | null };



export const BADGE_COLOR: Record<string, string> = {
  query: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  command: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  form: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  prerender: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  query_batch: 'bg-teal-500/20 text-teal-400 border-teal-500/30',
};

export function grouped(): Record<string, FunctionMeta[]> {
  const fns = Object.values(state.functions).filter(fn => {
    if (!state.search) return true;
    return fn.name.toLowerCase().includes(state.search.toLowerCase()) ||
           fn.module.toLowerCase().includes(state.search.toLowerCase());
  });

  return fns.reduce<Record<string, FunctionMeta[]>>((acc, fn) => {
    const key = state.groupBy === 'file'
      ? (fn.file_path ?? 'unknown')
      : fn.decorator_type;
    (acc[key] ??= []).push(fn);
    return acc;
  }, {});
}

export function shortPath(filePath: string): string {
  return filePath.replace(/\\/g, '/').split('/src/').pop() ?? filePath;
}

export function vsCodeUrl(filePath: string): string {
  return `vscode://file/${filePath.replace(/\\/g, '/')}`;
}
