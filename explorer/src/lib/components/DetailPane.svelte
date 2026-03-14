<script lang="ts">
  import { state } from '$lib/state.svelte';
  import { vsCodeUrl, shortPath, BADGE_COLOR } from '$lib/utils';
  import { Badge } from '$lib/components/ui/badge';
  import { ScrollArea } from '$lib/components/ui/scroll-area';
  import TryItPanel from '$lib/components/TryItPanel.svelte';
</script>

<div class="flex-1 flex flex-col h-screen overflow-hidden">
  {#if !state.selected}
    <div class="flex-1 flex items-center justify-center">
      <p class="text-zinc-600 text-sm">Select a function to inspect</p>
    </div>
  {:else}
    {@const fn = state.selected}

    <!-- Header -->
    <div class="px-6 py-4 border-b border-zinc-800 flex items-start justify-between gap-4">
      <div>
        <div class="flex items-center gap-2 mb-1">
          <Badge class="text-[10px] px-1.5 py-0 border {BADGE_COLOR[fn.decorator_type] ?? ''}">
            {fn.decorator_type}
          </Badge>
          <span class="text-zinc-100 font-semibold text-sm">{fn.name}</span>
        </div>
        <p class="text-xs text-zinc-600">
          <span class="text-zinc-500">POST</span>
          <span class="ml-1">{fn.route}</span>
        </p>
        {#if fn.docstring}
          <p class="text-xs text-zinc-500 mt-1">{fn.docstring}</p>
        {/if}
      </div>

      {#if fn.file_path}
        <a
          href={vsCodeUrl(fn.file_path)}
          class="text-xs text-zinc-600 hover:text-zinc-400 transition-colors shrink-0"
          title={fn.file_path}
        >
          {shortPath(fn.file_path)} ↗
        </a>
      {/if}
    </div>

    <!-- Body — TryItPanel goes here next -->
    <ScrollArea class="flex-1">
      <div class="p-6">
        <TryItPanel fn={fn} />
      </div>
    </ScrollArea>
  {/if}
</div>
