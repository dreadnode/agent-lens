<script lang="ts">
	import { formatCost, formatDate, formatDuration } from "$lib/utils/format";
	import { sessionKey } from "$lib/types/run";
	import ChatView from "$lib/components/chat/ChatView.svelte";

	let { data } = $props();

	const statCards = [
		{ label: "Sessions", value: data.run.session_count },
		{ label: "Steps", value: data.run.total_steps },
		{ label: "Tool calls", value: data.run.total_tool_calls },
		{ label: "Cost", value: formatCost(data.run.total_cost_usd) },
		{ label: "Compactions", value: data.run.total_compaction_events },
		{ label: "Subagents", value: data.run.total_subagent_invocations }
	];

	let expandedSession = $state<string | null>(
		data.run.sessions.length === 1 ? sessionKey(data.run.sessions[0]) : null
	);

	function toggleSession(key: string) {
		expandedSession = expandedSession === key ? null : key;
	}
</script>

<svelte:head>
	<title>{data.run.run_name} • AgentLens</title>
</svelte:head>

<div style="display: flex; flex-direction: column; gap: 2rem;">
	<div style="display: flex; flex-direction: column; gap: 0.75rem;">
		<a href="/" class="text-sm text-muted-foreground hover:text-foreground transition-colors">
			← All runs
		</a>
		<div class="flex items-start justify-between" style="gap: 1.5rem;">
			<div style="display: flex; flex-direction: column; gap: 0.625rem;">
				<div class="flex items-center flex-wrap" style="gap: 0.5rem;">
					<h1 class="text-2xl font-semibold tracking-tight">{data.run.run_name}</h1>
					{#if data.run.errors.length > 0}
						<span class="rounded-full bg-destructive/12 text-destructive text-xs font-medium border border-destructive/20" style="padding: 0.2rem 0.55rem;">
							{data.run.errors.length} error{data.run.errors.length === 1 ? "" : "s"}
						</span>
					{/if}
				</div>

				<div class="flex items-center flex-wrap text-sm text-muted-foreground" style="gap: 0.5rem 0.75rem;">
					<span>{data.run.provider}</span>
					<span>&middot;</span>
					<span class="font-mono text-xs">{data.run.model}</span>
					<span>&middot;</span>
					<span>{data.run.session_mode}</span>
					<span>&middot;</span>
					<span>{formatDate(data.run.started_at)}</span>
					<span>&middot;</span>
					<span>{formatDuration(data.run.started_at, data.run.finished_at)}</span>
				</div>

				{#if data.run.hypothesis}
					<p class="text-sm text-foreground/85 max-w-3xl">{data.run.hypothesis}</p>
				{/if}

				<div class="flex flex-wrap" style="gap: 0.5rem;">
					{#each data.run.tags as tag}
						<span class="rounded-full text-xs border border-border text-foreground/80" style="padding: 0.2rem 0.6rem;">{tag}</span>
					{/each}
				</div>
			</div>
		</div>
	</div>

	<div class="grid" style="grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr)); gap: 0.75rem;">
		{#each statCards as stat}
			<div class="rounded-lg border border-border bg-card" style="padding: 1rem;">
				<div class="text-xs uppercase tracking-wide text-muted-foreground">{stat.label}</div>
				<div class="text-xl font-semibold" style="margin-top: 0.375rem;">{stat.value}</div>
			</div>
		{/each}
	</div>

	{#each data.run.sessions as session, i}
		{@const key = sessionKey(session)}
		{@const traj = data.sessionTrajectories[i]}
		{@const isExpanded = expandedSession === key}
		<section class="rounded-lg border border-border overflow-hidden">
			<button
				class="w-full flex items-center justify-between border-b border-border bg-muted/40 hover:bg-muted/60 transition-colors cursor-pointer"
				style="padding: 0.9rem 1.1rem;"
				onclick={() => toggleSession(key)}
			>
				<div class="flex items-center" style="gap: 1rem;">
					<h2 class="text-sm font-semibold">Session #{key}</h2>
					<div class="flex items-center text-xs text-muted-foreground" style="gap: 0.75rem;">
						<span>{session.step_count} steps</span>
						<span>{session.num_turns} turns</span>
						<span>{session.tool_call_count} tool calls</span>
						<span>{formatCost(session.total_cost_usd)}</span>
						<span>{formatDuration(session.started_at, session.finished_at)}</span>
						{#if session.error}
							<span class="text-destructive">Failed</span>
						{/if}
					</div>
				</div>
				<span class="text-muted-foreground text-xs">{isExpanded ? "▼" : "▶"}</span>
			</button>

			{#if isExpanded}
				<div style="padding: 1rem 1.1rem;">
					{#if traj?.trajectory && traj.trajectory.steps.length > 0}
						<ChatView
							steps={traj.trajectory.steps}
							runName={data.run.run_name}
							sessionIndex={key}
							hasRawDumps={traj.hasRawDumps}
						/>
					{:else if session.error}
						<pre class="rounded-md bg-muted/50 border border-border text-xs whitespace-pre-wrap break-words" style="padding: 0.75rem;">{session.error}</pre>
					{:else}
						<p class="text-sm text-muted-foreground">No trajectory data available.</p>
					{/if}
				</div>
			{/if}
		</section>
	{/each}

	{#if data.run.errors.length > 0}
		<section class="rounded-lg border border-border" style="padding: 1rem 1.1rem;">
			<h2 class="text-sm font-semibold">Errors</h2>
			{#each data.run.errors as runError}
				<pre class="rounded-md bg-muted/50 border border-border text-xs whitespace-pre-wrap break-words" style="padding: 0.75rem; margin-top: 0.625rem;">{runError}</pre>
			{/each}
		</section>
	{/if}
</div>
