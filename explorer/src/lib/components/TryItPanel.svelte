<script lang="ts">
  import type { FunctionMeta } from '$lib/types';
  import { Button } from '$lib/components/ui/button';

  let { fn }: { fn: FunctionMeta } = $props();

  // Build flat form values from parameters
  let values = $state<Record<string, any>>({});

  let loading = $state(false);
  let response = $state<any>(null);
  let responseError = $state<string | null>(null);
  let status = $state<number | null>(null);

  const defaultValues = $derived(
    Object.fromEntries(fn.parameters.map(p => [p.name, p.default ?? '']))
  );

  // Reset when function changes
  $effect(() => {
    values = { ...defaultValues };
    response = null;
    responseError = null;
    status = null;
  });

  async function send() {
    loading = true;
    response = null;
    responseError = null;
    status = null;
    try {
      const res = await fetch(fn.route, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      });
      status = res.status;
      const text = await res.text();
      response = text ? JSON.parse(text) : null;
    } catch (e) {
      responseError = (e as Error).message;
    } finally {
      loading = false;
    }
  }
</script>

<div class="flex flex-col gap-6">
  <!-- Parameters -->
  {#if fn.parameters.length === 0}
    <p class="text-xs text-zinc-600">No parameters</p>
  {:else}
    <div class="flex flex-col gap-3">
      <p class="text-xs text-zinc-500 uppercase tracking-wider">Parameters</p>
        {#each fn.parameters as p}
        <div class="flex flex-col gap-1">
            <label class="flex flex-col gap-1">
            <span class="text-xs text-zinc-400">
                {p.name}
                <span class="text-zinc-600 ml-1">{p.type}</span>
                {#if p.required}<span class="text-red-500 ml-1">*</span>{/if}
            </span>
            <input
                type="text"
                bind:value={values[p.name]}
                placeholder={p.default != null ? String(p.default) : p.type}
                class="bg-zinc-800 border border-zinc-700 rounded-md px-3 py-1.5 text-xs text-zinc-300 placeholder-zinc-600 outline-none focus:border-zinc-500 w-full"
            />
            </label>
        </div>
        {/each}
    </div>
  {/if}

  <!-- Send -->
  <Button onclick={send} disabled={loading} class="w-fit">
    {loading ? 'Sending...' : 'Send'}
  </Button>

  <!-- Response -->
  {#if responseError}
    <p class="text-xs text-red-400">{responseError}</p>
  {:else if response !== null}
    <div class="flex flex-col gap-2">
      <div class="flex items-center gap-2">
        <p class="text-xs text-zinc-500 uppercase tracking-wider">Response</p>
        {#if status !== null}
          <span class="text-xs px-1.5 py-0.5 rounded {status < 300 ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'}">
            {status}
          </span>
        {/if}
      </div>
      <pre class="bg-zinc-800 border border-zinc-700 rounded-md p-4 text-xs text-zinc-300 overflow-auto max-h-96">{JSON.stringify(response, null, 2)}</pre>
    </div>
  {/if}
</div>
