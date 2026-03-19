<script lang="ts">
	import { onMount } from "svelte";
	import { afterNavigate } from "$app/navigation";
	import ChatView from "$lib/components/chat/ChatView.svelte";
	import { formatCost } from "$lib/utils/format";

	let { data } = $props();
	let trajectory = $derived(data.trajectory);
	let sessionIndex = $derived(data.sessionIndex);
	let runName = $derived(data.meta.run_name);
	let mainRequestIndices = $derived(data.mainRequestIndices);
	let hasRawDumps = $derived(data.hasRawDumps);
	let resamples = $derived(data.resamples);
	let sessionPrompt = $derived(data.sessionPrompt);

	function scrollToHash(hash: string) {
		if (!hash) return;
		const el = document.getElementById(hash.replace("#", ""));
		if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
	}

	// Cross-page deep links (SvelteKit client navigation)
	afterNavigate((nav) => {
		const hash = nav.to?.url.hash;
		if (!hash) return;
		setTimeout(() => scrollToHash(hash), 200);
	});

	// Same-page hash clicks + full page loads
	onMount(() => {
		if (location.hash) {
			setTimeout(() => scrollToHash(location.hash), 200);
		}
		const onHashChange = () => scrollToHash(location.hash);
		window.addEventListener("hashchange", onHashChange);
		return () => window.removeEventListener("hashchange", onHashChange);
	});
</script>

<!-- User prompt -->
{#if sessionPrompt}
	<div style="margin-bottom: 1.25rem; border: 1px solid var(--border); padding: 0.75rem 1rem;">
		<div style="font-size: 11px; color: var(--muted-foreground); margin-bottom: 0.375rem;">// session prompt</div>
		<pre style="white-space: pre-wrap; margin: 0; color: var(--foreground); font-size: 12px; line-height: 1.6;">{sessionPrompt.trim()}</pre>
	</div>
{/if}

<!-- Metrics bar -->
{#if trajectory.final_metrics}
	<div style="display: flex; align-items: center; gap: 1.25rem; font-size: 11px; color: var(--muted-foreground); border-bottom: 1px solid var(--border); margin-bottom: 1.25rem; padding-bottom: 0.625rem; flex-wrap: wrap;">
		{#if trajectory.final_metrics.total_steps}
			<span>steps={trajectory.final_metrics.total_steps}</span>
		{/if}
		{#if trajectory.final_metrics.total_prompt_tokens}
			<span>prompt_tok={trajectory.final_metrics.total_prompt_tokens.toLocaleString()}</span>
		{/if}
		{#if trajectory.final_metrics.total_completion_tokens}
			<span>completion_tok={trajectory.final_metrics.total_completion_tokens.toLocaleString()}</span>
		{/if}
		{#if trajectory.final_metrics.total_cost_usd}
			<span style="color: var(--term-amber);">cost={formatCost(trajectory.final_metrics.total_cost_usd)}</span>
		{/if}
	</div>
{/if}

<!-- Chat view -->
<ChatView steps={trajectory.steps} {runName} {sessionIndex} {mainRequestIndices} {hasRawDumps} {resamples} />
