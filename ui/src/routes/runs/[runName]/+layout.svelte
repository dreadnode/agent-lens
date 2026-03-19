<script lang="ts">
	import { page } from "$app/state";
	import { formatCost, formatDuration } from "$lib/utils/format";
	import { sessionKey } from "$lib/types/run";

	let { data, children } = $props();
	let meta = $derived(data.meta);

	let activeSessionIdx = $derived.by(() => {
		const m = page.url.pathname.match(/\/sessions\/([^/]+)/);
		return m ? m[1] : null;
	});

	let tabs = $derived([
		{ href: `/runs/${meta.run_name}`, label: "overview", exact: true },
		...(data.hasAnalysis ? [{ href: `/runs/${meta.run_name}/analysis`, label: "analysis", exact: false }] : []),
		{ href: `/runs/${meta.run_name}/memory`, label: "memory", exact: false },
		{ href: `/runs/${meta.run_name}/changelog`, label: "changelog", exact: false },
		{ href: `/runs/${meta.run_name}/config`, label: "config", exact: false },
	]);
</script>

<!-- Breadcrumb + run name -->
<div style="margin-bottom: 1.25rem;">
	<div style="display: flex; align-items: center; gap: 0.375rem; font-size: 12px; color: var(--muted-foreground); margin-bottom: 0.75rem;">
		<a href="/" style="color: var(--muted-foreground);">runs/</a>
		<span style="color: var(--term-dim);">/</span>
		<span style="color: var(--foreground);">{meta.run_name}</span>
	</div>

	<!-- Run metadata line -->
	<div style="display: flex; align-items: center; flex-wrap: wrap; gap: 0.5rem; font-size: 12px; color: var(--muted-foreground);">
		<span class="meta-pill" style="color: var(--foreground);">{meta.model}</span>
		<span class="meta-pill">{meta.provider}</span>
		<span class="meta-pill">{meta.session_mode}</span>
		<span class="meta-pill">{meta.total_steps} steps</span>
		<span class="meta-pill" style="color: var(--term-amber);">{formatCost(meta.total_cost_usd)}</span>
		<span class="meta-pill">{formatDuration(meta.started_at, meta.finished_at)}</span>
		{#each meta.tags as tag}
			<span class="meta-pill" style="color: var(--term-cyan);">#{tag}</span>
		{/each}
	</div>

	{#if meta.hypothesis}
		<p style="color: var(--muted-foreground); font-size: 12px; margin-top: 0.5rem; font-style: italic;">// {meta.hypothesis}</p>
	{/if}
</div>

<!-- Tab nav -->
<nav style="display: flex; align-items: center; gap: 0.25rem; margin-bottom: 0.25rem; flex-wrap: wrap;">
	{#each tabs as tab}
		{@const isActive = tab.exact ? page.url.pathname === tab.href : page.url.pathname.startsWith(tab.href)}
		<a
			href={tab.href}
			class="term-tab {isActive ? 'active' : ''}"
		>
			[{tab.label}]
		</a>
	{/each}
</nav>

<!-- Session pills (only shown on run-level pages) -->
{#if activeSessionIdx === null}
	<div style="display: flex; align-items: center; flex-wrap: wrap; gap: 0.25rem; padding: 0.625rem 0 1.25rem; border-top: 1px solid var(--border);">
		<span style="font-size: 11px; color: var(--muted-foreground); margin-right: 0.25rem;">sessions:</span>
		{#each meta.sessions as session}
			{@const key = sessionKey(session)}
			<a
				href="/runs/{meta.run_name}/sessions/{key}"
				style="font-size: 11px; padding: 0.125rem 0.375rem; border: 1px solid var(--border); color: var(--muted-foreground);"
				class="session-pill-inactive"
			>
				[{session.session_index}{#if session.replicate != null}r{session.replicate}{/if}{#if session.fork_from}↑{session.fork_from}{/if}]
				{#if session.error}
					<span style="color: var(--term-red);">!</span>
				{/if}
				<span style="color: var(--term-dim);">({session.step_count})</span>
			</a>
		{/each}
	</div>
{:else}
	<div style="border-top: 1px solid var(--border); margin-bottom: 1.25rem;"></div>
{/if}

{@render children()}
