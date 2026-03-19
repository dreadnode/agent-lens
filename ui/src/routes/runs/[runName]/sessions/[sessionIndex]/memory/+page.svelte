<script lang="ts">
	import DiffBlock from "$lib/components/diff/DiffBlock.svelte";

	let { data } = $props();
	let view = $state<"diff" | "before" | "after">("diff");
</script>

<style>
	:global(.seg-btn-inactive):hover {
		background: var(--background) !important;
		color: var(--foreground) !important;
	}
</style>

<div class="flex items-center" style="gap: 0.875rem; margin-bottom: 1.75rem;">
	<h2 class="text-sm font-medium">Session {data.sessionIndex} — {data.memoryFile}</h2>
	<div class="flex rounded-md" style="gap: 0.25rem; padding: 0.25rem; background: var(--muted);">
		{#each [["diff", "Diff"], ["before", "Before"], ["after", "After"]] as [v, label]}
			<button
				onclick={() => (view = v as typeof view)}
				style="padding: 0.375rem 0.75rem; cursor: pointer; {view === v ? 'background: var(--background); color: var(--foreground); box-shadow: 0 1px 2px rgba(0,0,0,0.05);' : 'color: var(--muted-foreground);'}"
				class="text-xs rounded transition-colors {view === v ? 'font-medium' : 'seg-btn-inactive'}"
			>
				{label}
			</button>
		{/each}
	</div>
</div>

{#if view === "diff"}
	{#if data.patch}
		<DiffBlock content={data.patch} />
	{:else}
		<p class="text-sm text-muted-foreground py-8 text-center">No changes in this session.</p>
	{/if}
{:else if view === "before"}
	<pre class="text-xs font-mono bg-muted/30 rounded-lg border border-border p-4 whitespace-pre-wrap overflow-auto max-h-[70vh]">{data.before || "(empty)"}</pre>
{:else}
	<pre class="text-xs font-mono bg-muted/30 rounded-lg border border-border p-4 whitespace-pre-wrap overflow-auto max-h-[70vh]">{data.after || "(empty)"}</pre>
{/if}
