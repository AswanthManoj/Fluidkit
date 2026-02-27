<script lang="ts">
	import favicon from '$lib/assets/favicon.svg';

	let { children } = $props();
</script>

<svelte:head><link rel="icon" href={favicon} /></svelte:head>

{@render children()}

<style>
	:global(*) { box-sizing: border-box; }
	:global(body) {
		margin: 0;
		background: #0c0a09;
		color: #d6d3d1;
		font-family: 'Inter', system-ui, -apple-system, sans-serif;
	}
	:global(a) { color: #68D7EF; }
</style>
