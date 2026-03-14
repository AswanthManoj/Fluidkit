<script lang="ts">
  import './app.css';
  import { state } from '$lib/state.svelte';
  import Sidebar from '$lib/components/Sidebar.svelte';
  import DetailPane from '$lib/components/DetailPane.svelte';

  async function loadAll() {
    try {
      const res = await fetch('/meta');
      state.functions = await res.json();
    } catch (e) {
      state.error = (e as Error).message;
    }
  }

  async function loadKeys(keys: string[]) {
    try {
      const res = await fetch('/meta', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keys }),
      });
      const updated = await res.json();
      state.functions = { ...state.functions, ...updated };
    } catch (e) {
      state.error = (e as Error).message;
    }
  }

  function connectWs() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${protocol}//${location.host}/ws`);
    ws.onopen = () => { state.connected = true; };
    ws.onclose = () => {
      state.connected = false;
      setTimeout(connectWs, 2000);
    };
    ws.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.action === 'register') loadKeys(data.keys);
      if (data.action === 'unregister') {
        const updated = { ...state.functions };
        for (const key of data.keys) delete updated[key];
        state.functions = updated;
      }
    };
  }

  loadAll();
  connectWs();
</script>

<div class="flex h-screen bg-zinc-950 text-zinc-300 font-mono overflow-hidden">
  <Sidebar />
  <DetailPane />
</div>
