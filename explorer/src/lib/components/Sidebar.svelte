<script lang="ts">
  import { state, selectFunction } from '$lib/state.svelte';
  import { grouped, shortPath, BADGE_COLOR } from '$lib/utils';
  import { Badge } from '$lib/components/ui/badge';
  import { ScrollArea } from '$lib/components/ui/scroll-area';

  const groups = $derived(grouped());
</script>

<div class="flex flex-col w-72 min-w-72 border-r border-zinc-800 bg-zinc-900 h-screen">
  
  <!-- Header -->
  <div class="p-4 border-b border-zinc-800">
    <div class="flex items-center justify-between mb-3">
      <span class="text-sm font-semibold text-zinc-100">FluidKit Explorer</span>
      <div class="flex items-center gap-1.5">
        <span class="w-1.5 h-1.5 rounded-full {state.connected ? 'bg-emerald-400' : 'bg-red-400'}"></span>
        <span class="text-xs text-zinc-500">{state.connected ? 'live' : 'off'}</span>
      </div>
    </div>

    <!-- Search -->
    <input
      type="text"
      placeholder="Search..."
      bind:value={state.search}
      class="w-full bg-zinc-800 border border-zinc-700 rounded-md px-3 py-1.5 text-xs text-zinc-300 placeholder-zinc-600 outline-none focus:border-zinc-500"
    />

    <!-- Group toggle -->
    <div class="flex mt-2 bg-zinc-800 rounded-md p-0.5 text-xs">
      <button
        class="flex-1 py-1 rounded transition-colors {state.groupBy === 'file' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'}"
        onclick={() => state.groupBy = 'file'}
      >by file</button>
      <button
        class="flex-1 py-1 rounded transition-colors {state.groupBy === 'decorator' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'}"
        onclick={() => state.groupBy = 'decorator'}
      >by type</button>
    </div>
  </div>

  <!-- Function list -->
  <ScrollArea class="flex-1">
    <div class="p-2">
      {#if state.error}
        <p class="text-xs text-red-400 p-2">{state.error}</p>
      {:else if Object.keys(groups).length === 0}
        <p class="text-xs text-zinc-600 p-2">No functions found.</p>
      {:else}
        {#each Object.entries(groups) as [groupKey, fns]}
          <div class="mb-4">
            <p class="text-xs text-zinc-600 px-2 py-1 truncate" title={groupKey}>
              {state.groupBy === 'file' ? shortPath(groupKey) : `@${groupKey}`}
            </p>
            {#each fns as fn}
              <button
                class="w-full text-left px-2 py-1.5 rounded-md flex items-center gap-2 hover:bg-zinc-800 transition-colors {state.selected?.key === fn.key ? 'bg-zinc-800' : ''}"
                onclick={() => selectFunction(fn)}
              >
                <Badge class="text-[10px] px-1.5 py-0 border {BADGE_COLOR[fn.decorator_type] ?? 'bg-zinc-700 text-zinc-300'}">
                  {fn.decorator_type}
                </Badge>
                <span class="text-xs text-zinc-300 truncate">{fn.name}</span>
              </button>
            {/each}
          </div>
        {/each}
      {/if}
    </div>
  </ScrollArea>
</div>
