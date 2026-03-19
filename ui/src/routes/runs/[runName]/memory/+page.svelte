<script lang="ts">
	let { data } = $props();
	let view = $state<"side-by-side" | "init" | "final">("side-by-side");
</script>

<div class="flex items-center gap-3 mb-6">
	<h2 class="text-sm font-medium">{data.memoryFile}: Init vs Final</h2>
	<div class="flex gap-0.5 bg-muted rounded-md p-0.5">
		{#each [["side-by-side", "Side by Side"], ["init", "Initial"], ["final", "Final"]] as [v, label]}
			<button
				onclick={() => (view = v as typeof view)}
				class="px-2.5 py-1 text-xs rounded transition-colors {view === v ? 'bg-background text-foreground shadow-sm font-medium' : 'text-muted-foreground hover:text-foreground'}"
			>
				{label}
			</button>
		{/each}
	</div>
</div>

{#if view === "side-by-side"}
	<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
		<div>
			<div class="text-[11px] font-medium text-muted-foreground uppercase tracking-wide mb-1.5">Initial</div>
			<pre class="text-xs font-mono bg-muted/30 rounded-lg border border-border p-3 whitespace-pre-wrap overflow-auto max-h-[70vh]">{data.init || "(empty)"}</pre>
		</div>
		<div>
			<div class="text-[11px] font-medium text-muted-foreground uppercase tracking-wide mb-1.5">Final</div>
			<pre class="text-xs font-mono bg-muted/30 rounded-lg border border-border p-3 whitespace-pre-wrap overflow-auto max-h-[70vh]">{data.final || "(empty)"}</pre>
		</div>
	</div>
{:else if view === "init"}
	<pre class="text-xs font-mono bg-muted/30 rounded-lg border border-border p-4 whitespace-pre-wrap overflow-auto max-h-[70vh]">{data.init || "(empty)"}</pre>
{:else}
	<pre class="text-xs font-mono bg-muted/30 rounded-lg border border-border p-4 whitespace-pre-wrap overflow-auto max-h-[70vh]">{data.final || "(empty)"}</pre>
{/if}
