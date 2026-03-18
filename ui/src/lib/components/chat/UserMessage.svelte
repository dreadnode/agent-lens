<script lang="ts">
	let { text, isFirst = false, stepId = 0 }: {
		text: string;
		isFirst?: boolean;
		stepId?: number;
	} = $props();
</script>

<div class="flex justify-end" id="step-{stepId}">
	<div class="max-w-2xl">
		{#if isFirst}
			<div class="text-[11px] text-muted-foreground mb-1 text-right">Session Prompt</div>
		{/if}
		<div class="bg-primary text-primary-foreground rounded-lg px-4 py-3 text-sm">
			<pre class="whitespace-pre-wrap font-sans leading-relaxed">{text}</pre>
		</div>
		<a href="#step-{stepId}" class="text-[11px] text-muted-foreground/70 hover:text-muted-foreground mt-1 text-right block transition-colors">Step {stepId}</a>
	</div>
</div>
