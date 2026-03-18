<script lang="ts">
	interface Edit {
		path: string;
		original: string;
		replacement: string;
	}

	let { edits, expanded = false }: { edits: Edit[]; expanded?: boolean } = $props();

	let isExpanded = $state(false);

	$effect(() => {
		isExpanded = expanded;
	});
</script>

{#if edits.length > 0}
	<button
		onclick={() => (isExpanded = !isExpanded)}
		class="w-full text-left"
	>
		<div class="rounded-md px-3 py-2 bg-muted/40 border border-border/50 hover:border-foreground/20 transition-colors">
			<div class="flex items-center gap-1.5 text-[11px] text-muted-foreground">
				<span class="inline-block w-3 text-center transition-transform {isExpanded ? 'rotate-90' : ''}">&rsaquo;</span>
				<span class="font-medium">{edits.length} edit{edits.length > 1 ? "s" : ""}</span>
			</div>

			{#if isExpanded}
				<div class="mt-2 ml-[18px] space-y-3">
					{#each edits as edit}
						<div class="text-[10px] font-mono">
							<div class="text-muted-foreground/60 mb-1">{edit.path}</div>
							<div class="rounded bg-red-100 dark:bg-red-950/30 border border-red-300 dark:border-red-500/20 px-2 py-1 text-red-800 dark:text-red-300/80 whitespace-pre-wrap break-all">- {edit.original}</div>
							<div class="rounded bg-green-100 dark:bg-green-950/30 border border-green-300 dark:border-green-500/20 px-2 py-1 text-green-800 dark:text-green-300/80 whitespace-pre-wrap break-all mt-0.5">+ {edit.replacement}</div>
						</div>
					{/each}
				</div>
			{/if}
		</div>
	</button>
{/if}
