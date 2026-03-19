<script lang="ts">
	import ChatView from "$lib/components/chat/ChatView.svelte";
	import { renderMarkdown } from "$lib/utils/markdown";

	let { data } = $props();
	let trajectory = $derived(data.trajectory);
	let runName = $derived(data.meta.run_name);
	let sessionIndex = $derived(data.sessionIndex);
	let returnValue = $derived(data.returnValue);

	let displayName = $derived(
		data.filename
			.replace(/^subagent_/, "")
			.replace(/\.json$/, "")
			.replace(/_/g, " ")
	);

	// Extract the first user step as the task prompt, pass the rest to ChatView
	let taskPrompt = $derived.by(() => {
		const first = trajectory.steps[0];
		if (first?.source === "user") {
			const msg = first.message;
			return typeof msg === "string" ? msg : "";
		}
		return null;
	});

	let chatSteps = $derived(
		taskPrompt !== null ? trajectory.steps.slice(1) : trajectory.steps
	);
</script>

<div class="flex items-center gap-3 mb-6">
	<a
		href="/runs/{runName}/sessions/{sessionIndex}"
		class="text-xs text-muted-foreground hover:text-foreground transition-colors"
	>
		&larr; Back to session
	</a>
	<span class="w-px h-4 bg-border"></span>
	<h2 class="text-sm font-medium">
		Subagent: <span class="font-mono text-muted-foreground">{displayName}</span>
	</h2>
</div>

{#if trajectory.agent}
	<div class="flex items-center gap-3 text-xs text-muted-foreground mb-4 pb-3 border-b border-border">
		<span class="font-mono">{trajectory.agent.name}</span>
		{#if trajectory.final_metrics?.total_steps}
			<span>{trajectory.final_metrics.total_steps} steps</span>
		{/if}
	</div>
{/if}

<!-- Task prompt -->
{#if taskPrompt}
	<div class="rounded-lg border border-border bg-card" style="margin-bottom: 1.5rem; padding: 1rem 1.25rem;">
		<div class="text-xs font-medium text-muted-foreground" style="margin-bottom: 0.5rem;">Task Prompt</div>
		<pre class="font-mono text-sm" style="white-space: pre-wrap; margin: 0; color: var(--foreground); line-height: 1.6;">{taskPrompt.trim()}</pre>
	</div>
{/if}

<ChatView steps={chatSteps} {runName} {sessionIndex} />

<!-- Return value -->
{#if returnValue}
	{@const html = renderMarkdown(returnValue)}
	<div class="rounded-lg border border-emerald-400/40 dark:border-emerald-500/30 bg-emerald-50 dark:bg-emerald-950/10 max-w-4xl" style="margin-top: 1.5rem; padding: 1rem 1.25rem;">
		<div class="text-xs font-medium text-emerald-700 dark:text-emerald-300" style="margin-bottom: 0.5rem;">Subagent Return Value</div>
		<div
			class="text-sm prose prose-sm dark:prose-invert max-w-none prose-p:my-1.5 prose-headings:my-2 prose-ul:my-1.5 prose-ol:my-1.5 prose-li:my-0.5 prose-pre:my-2 prose-pre:bg-muted prose-pre:text-xs prose-code:text-xs prose-code:before:content-none prose-code:after:content-none"
			style="color: var(--foreground);"
		>
			{@html html}
		</div>
	</div>
{/if}
