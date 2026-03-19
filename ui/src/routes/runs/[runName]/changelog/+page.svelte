<script lang="ts">
	import DiffBlock from "$lib/components/diff/DiffBlock.svelte";

	let { data } = $props();
	let expandedEntry = $state<number | null>(null);
</script>

<h2 class="text-sm font-medium mb-6">State Changelog</h2>

{#if data.entries.length === 0}
	<p class="text-sm text-muted-foreground py-8 text-center">No file changes recorded.</p>
{:else}
	<div class="space-y-2">
		{#each data.entries as entry, i}
			<button
				onclick={() => expandedEntry = expandedEntry === i ? null : i}
				class="w-full text-left rounded-lg border border-border bg-card p-3 hover:border-foreground/20 transition-colors"
			>
				<div class="flex items-center justify-between">
					<div class="flex items-center gap-2">
						<span class="text-[11px] px-1.5 py-0.5 rounded bg-secondary text-secondary-foreground font-medium tabular-nums">S{entry.session_index}</span>
						<span class="text-xs font-mono">{entry.file_path}</span>
						<span class="text-[11px] text-muted-foreground">step {entry.step_id}</span>
					</div>
					<div class="flex gap-3 text-xs tabular-nums font-mono">
						<span class="text-green-700 dark:text-green-400">+{entry.diff_stats.added}</span>
						<span class="text-red-700 dark:text-red-400">-{entry.diff_stats.removed}</span>
					</div>
				</div>

				{#if expandedEntry === i && entry.diff}
					<div class="mt-3">
						<DiffBlock content={entry.diff} />
					</div>
				{/if}
			</button>
		{/each}
	</div>
{/if}
