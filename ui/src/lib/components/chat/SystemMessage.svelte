<script lang="ts">
	let { text, stepId = 0 }: { text: string; stepId?: number } = $props();
</script>

{#if text.trim()}
	<div class="flex justify-center" id="step-{stepId}">
		<div class="text-xs text-muted-foreground bg-muted/50 rounded px-3 py-1.5 max-w-lg text-center">
			{text}
			<span class="ml-2 opacity-70">Step {stepId}</span>
		</div>
	</div>
{/if}
