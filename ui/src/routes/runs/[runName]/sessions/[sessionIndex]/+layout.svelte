<script lang="ts">
	import { page } from "$app/state";
	import { goto } from "$app/navigation";
	import { sessionKey } from "$lib/types/run";

	let { data, children } = $props();
	let sessionIndex = $derived(data.sessionIndex);
	let subagentFiles = $derived(data.subagentFiles);
	let resamples = $derived(data.resamples);
	let runName = $derived(data.meta.run_name);
	let sessions = $derived(data.meta.sessions);

	let basePath = $derived(`/runs/${runName}/sessions/${sessionIndex}`);
	let currentPath = $derived(page.url.pathname);

	let subPage = $derived.by(() => {
		const after = currentPath.slice(basePath.length);
		if (after.startsWith("/memory")) return "/memory";
		if (after.startsWith("/api")) return "/api";
		if (after.startsWith("/resamples")) return "/resamples";
		return "";
	});

	let resampleTotal = $derived(Object.values(resamples).reduce((a: number, b: number) => a + b, 0));

	function handleSessionChange(e: Event) {
		const select = e.target as HTMLSelectElement;
		goto(`/runs/${runName}/sessions/${select.value}${subPage}`);
	}

	let subTabs = $derived([
		{ href: basePath, label: "trajectory", exact: true },
		{ href: `${basePath}/memory`, label: "memory_diff", exact: false },
		{ href: `${basePath}/api`, label: "api_captures", exact: false },
		{ href: `${basePath}/resamples`, label: `resamples${resampleTotal > 0 ? ':' + resampleTotal : ''}`, exact: false },
	]);
</script>

<!-- Session nav -->
<div style="display: flex; align-items: center; flex-wrap: wrap; gap: 0.375rem; margin-bottom: 1.25rem;">
	<!-- Session selector -->
	<select
		value={String(sessionIndex)}
		onchange={handleSessionChange}
		style="background: var(--card); border: 1px solid var(--border); color: var(--foreground); padding: 0.25rem 0.5rem; font-size: 12px; cursor: pointer; outline: none; appearance: none; padding-right: 1.5rem;"
	>
		{#each sessions as session}
			{@const key = sessionKey(session)}
			<option value={key} style="background: var(--background);">
				session_{session.session_index}{#if session.replicate != null}r{session.replicate}{/if}{#if session.fork_from}↑{session.fork_from}{/if}{session.error ? " !" : ""} ({session.step_count})
			</option>
		{/each}
	</select>

	<span style="color: var(--border); margin: 0 0.25rem;">│</span>

	<!-- Sub-page tabs -->
	{#each subTabs as tab}
		{@const isActive = tab.exact ? currentPath === tab.href : currentPath.startsWith(tab.href)}
		<a
			href={tab.href}
			class="term-tab {isActive ? 'active' : ''}"
		>
			[{tab.label}]
		</a>
	{/each}

	{#if subagentFiles.length > 0}
		<span style="color: var(--border); margin: 0 0.25rem;">│</span>
		{#each subagentFiles as f}
			<a
				href="/runs/{runName}/sessions/{sessionIndex}/subagents/{f}"
				class="term-tab"
				style="color: var(--term-blue);"
			>
				[{f.replace(".json", "")}]
			</a>
		{/each}
	{/if}
</div>

{@render children()}
