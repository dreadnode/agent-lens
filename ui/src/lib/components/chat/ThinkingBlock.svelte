<script lang="ts">
	let { content }: { content: string } = $props();
	let expanded = $state(false);

	let lines = $derived(content.split("\n"));
	let preview = $derived(lines.slice(0, 3).join("\n"));
	let needsTruncation = $derived(lines.length > 3);
</script>

<button
	onclick={() => (expanded = !expanded)}
	class="w-full text-left group"
>
	<div class="rounded-md px-3 py-2 bg-muted/40 border border-border hover:border-foreground/20 transition-colors">
		<div class="flex items-center gap-1.5 text-[11px] text-muted-foreground mb-1">
			<span class="inline-block w-3 text-center transition-transform {expanded ? 'rotate-90' : ''}">&rsaquo;</span>
			<span class="font-medium uppercase tracking-wide">Thinking</span>
			{#if !expanded && needsTruncation}
				<span class="ml-auto">{lines.length} lines</span>
			{/if}
		</div>
		{#if expanded}
			<pre class="text-xs text-muted-foreground font-mono whitespace-pre-wrap italic leading-relaxed ml-[18px]">{content}</pre>
		{:else if needsTruncation}
			<pre class="text-xs text-muted-foreground font-mono whitespace-pre-wrap italic leading-relaxed ml-[18px] line-clamp-3">{preview}</pre>
		{:else}
			<pre class="text-xs text-muted-foreground font-mono whitespace-pre-wrap italic leading-relaxed ml-[18px]">{content}</pre>
		{/if}
	</div>
</button>
