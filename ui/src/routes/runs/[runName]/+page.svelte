<script lang="ts">
	import { formatCost, formatDuration } from "$lib/utils/format";
	import { sessionKey, type SessionMeta } from "$lib/types/run";

	let { data } = $props();
	let meta = $derived(data.meta);

	let hasForks = $derived(meta.sessions.some((s: any) => s.fork_from));

	/** Group sessions: base sessions with their replicates nested underneath. */
	interface SessionGroup {
		base: SessionMeta;
		replicates: SessionMeta[];
	}

	let sessionGroups = $derived.by(() => {
		const groups: SessionGroup[] = [];
		const byIndex = new Map<number, { base: SessionMeta | null; reps: SessionMeta[] }>();

		for (const s of meta.sessions) {
			const entry = byIndex.get(s.session_index) ?? { base: null, reps: [] };
			if (s.replicate != null) {
				entry.reps.push(s);
			} else {
				entry.base = s;
			}
			byIndex.set(s.session_index, entry);
		}

		// Sort by session_index
		const indices = [...byIndex.keys()].sort((a, b) => a - b);
		for (const idx of indices) {
			const entry = byIndex.get(idx)!;
			const reps = entry.reps.sort((a, b) => (a.replicate ?? 0) - (b.replicate ?? 0));
			if (entry.base) {
				groups.push({ base: entry.base, replicates: reps });
			} else if (reps.length > 0) {
				// No plain session, first replicate is the "base"
				groups.push({ base: reps[0], replicates: reps.slice(1) });
			}
		}
		return groups;
	});

	let metrics = $derived([
		{ label: "sessions", value: meta.session_count },
		{ label: "steps", value: meta.total_steps },
		{ label: "tool_calls", value: meta.total_tool_calls },
		{ label: "file_writes", value: meta.total_file_writes },
		{ label: "compactions", value: meta.total_compaction_events },
		{ label: "subagents", value: meta.total_subagent_invocations },
	]);
</script>

{#snippet sessionRow(session: SessionMeta, isReplicate: boolean, showBorder: boolean)}
	{@const key = sessionKey(session)}
	{@const indent = isReplicate || (hasForks && session.fork_from)}
	<a
		href="/runs/{meta.run_name}/sessions/{key}"
		style="display: flex; align-items: center; justify-content: space-between; padding: 0.625rem 0.875rem; font-size: 12px; {showBorder ? 'border-top: 1px solid var(--border);' : ''} {indent ? 'padding-left: 2rem;' : ''}"
		class="session-row"
	>
		<div style="display: flex; align-items: center; gap: 0.75rem;">
			{#if isReplicate}
				<span style="color: var(--muted-foreground); font-size: 11px;">↳</span>
			{:else if session.fork_from}
				<span style="color: var(--muted-foreground);">↳</span>
			{/if}
			<span style="color: {isReplicate ? 'var(--muted-foreground)' : 'var(--foreground)'};">
				{#if isReplicate}
					r{String(session.replicate).padStart(2, "0")}
				{:else}
					session_{session.session_index}{#if session.replicate != null}<span style="color: var(--muted-foreground);"> r{String(session.replicate).padStart(2, "0")}</span>{/if}
				{/if}
			</span>
			{#if !isReplicate && session.fork_from}
				<span style="color: var(--muted-foreground); font-size: 11px;">fork↑{session.fork_from}</span>
			{/if}
			{#if session.error}
				<span style="color: var(--term-red); font-size: 11px;">[error]</span>
			{/if}
			{#if session.compaction_count > 0}
				<span style="color: var(--term-dim); font-size: 11px;">{session.compaction_count} compact</span>
			{/if}
			{#if session.subagent_count > 0}
				<span style="color: var(--term-dim); font-size: 11px;">{session.subagent_count} subagent{session.subagent_count > 1 ? "s" : ""}</span>
			{/if}
		</div>
		<div style="display: flex; align-items: center; gap: 1.5rem; color: var(--muted-foreground);">
			<span>{session.step_count} steps</span>
			<span>{session.tool_call_count} tools</span>
			<span>{session.num_turns} turns</span>
			<span style="color: var(--term-amber);">{formatCost(session.total_cost_usd)}</span>
			<span>{formatDuration(session.started_at, session.finished_at)}</span>
			<span class="arrow" style="opacity: 0.3;">→</span>
		</div>
	</a>
{/snippet}

<!-- Metrics -->
<div style="font-size: 12px; color: var(--muted-foreground); margin-bottom: 1.5rem; display: flex; flex-wrap: wrap; gap: 1.5rem;">
	{#each metrics as m}
		<span>
			<span style="color: var(--muted-foreground);">{m.label}=</span><span style="color: var(--foreground);">{m.value}</span>
		</span>
	{/each}
</div>

<!-- Sessions list -->
<div style="font-size: 11px; color: var(--muted-foreground); margin-bottom: 0.5rem; letter-spacing: 0.08em;">SESSIONS</div>
<div style="display: flex; flex-direction: column; border: 1px solid var(--border);">
	{#each sessionGroups as group, gi}
		{@render sessionRow(group.base, false, gi > 0)}
		{#each group.replicates as rep}
			{@render sessionRow(rep, true, true)}
		{/each}
	{/each}
</div>

<style>
	.session-row:hover {
		background: var(--card);
	}
	.session-row:hover .arrow {
		opacity: 1;
		color: var(--term-green);
	}
</style>
