<script lang="ts">
	import { formatCost, formatDate } from "$lib/utils/format";
	import type { RunMeta, RunGroup } from "$lib/types/run";

	let { data } = $props();
	let search = $state("");

	/**
	 * Group replay runs under their root ancestor.
	 * Walks the replay_source chain to find the original non-replay run,
	 * so replay-of-replay still groups under the original.
	 */
	function groupRuns(runs: RunMeta[]): RunGroup[] {
		const byName = new Map<string, RunMeta>();
		for (const r of runs) byName.set(r.run_name, r);

		// Find root ancestor for any run (walk replay_source chain)
		function rootAncestor(r: RunMeta): string {
			const visited = new Set<string>();
			let current = r;
			while (current.replay_source && !visited.has(current.run_name)) {
				visited.add(current.run_name);
				const parent = byName.get(current.replay_source);
				if (!parent) return current.replay_source; // parent not loaded, use name
				current = parent;
			}
			return current.run_name;
		}

		// Separate into root runs and replay descendants
		const rootRuns: RunMeta[] = [];
		const descendants = new Map<string, RunMeta[]>();

		for (const r of runs) {
			if (!r.replay_source) {
				rootRuns.push(r);
			} else {
				const root = rootAncestor(r);
				const list = descendants.get(root) ?? [];
				list.push(r);
				descendants.set(root, list);
			}
		}

		// Build groups
		const groups: RunGroup[] = [];
		const attached = new Set<string>();

		for (const r of rootRuns) {
			const replays = (descendants.get(r.run_name) ?? [])
				.sort((a, b) => a.started_at.localeCompare(b.started_at));
			for (const rp of replays) attached.add(rp.run_name);
			groups.push({ run: r, replays });
		}

		// Orphan replays (root ancestor not in current list)
		for (const [, children] of descendants) {
			for (const r of children) {
				if (!attached.has(r.run_name)) {
					groups.push({ run: r, replays: [] });
				}
			}
		}

		return groups;
	}

	let groups = $derived(groupRuns(data.runs));

	let filtered = $derived(
		groups.filter((g) => {
			if (!search) return true;
			const q = search.toLowerCase();
			const matchRun = (r: RunMeta) =>
				r.run_name.toLowerCase().includes(q) ||
				r.model.toLowerCase().includes(q) ||
				r.tags.some((t: string) => t.toLowerCase().includes(q));
			return matchRun(g.run) || g.replays.some(matchRun);
		})
	);

	// Auto-expand groups when search matches a child replay
	$effect(() => {
		if (!search) return;
		const q = search.toLowerCase();
		const matchRun = (r: RunMeta) =>
			r.run_name.toLowerCase().includes(q) ||
			r.model.toLowerCase().includes(q) ||
			r.tags.some((t: string) => t.toLowerCase().includes(q));
		const next = new Set(expandedGroups);
		let changed = false;
		for (const g of filtered) {
			if (!matchRun(g.run) && g.replays.some(matchRun) && !next.has(g.run.run_name)) {
				next.add(g.run.run_name);
				changed = true;
			}
		}
		if (changed) expandedGroups = next;
	});

	// Track which groups have their replays expanded
	let expandedGroups = $state<Set<string>>(new Set());

	function toggleReplays(runName: string) {
		const next = new Set(expandedGroups);
		if (next.has(runName)) next.delete(runName);
		else next.add(runName);
		expandedGroups = next;
	}

	/** Build a display label for a replay run. */
	function replayLabel(run: RunMeta): string {
		const si = run.sessions[0]?.session_index ?? '?';
		const turn = run.replay_turn != null ? `t${run.replay_turn}` : '';
		let label = `replay s${si} ${turn}`.trim();
		// If the source is itself a replay, note the lineage
		const source = run.replay_source ? data.runs.find((r: RunMeta) => r.run_name === run.replay_source) : null;
		if (source?.replay_source) {
			label += ` (of replay)`;
		}
		return label;
	}
</script>

{#snippet runRow(run: RunMeta, isReplay: boolean)}
	<tr
		class="border-b border-border last:border-b-0 hover:bg-muted/30 transition-colors cursor-pointer"
		onclick={() => window.location.href = `/runs/${run.run_name}`}
	>
		<td style="padding: 1rem 1.25rem; {isReplay ? 'padding-left: 2.5rem;' : ''}">
			<div style="display: flex; align-items: center; gap: 0.5rem;">
				{#if isReplay}
					<span style="color: var(--muted-foreground); font-size: 11px;">↳</span>
				{/if}
				<span class="font-medium text-sm" style="{isReplay ? 'color: var(--muted-foreground);' : ''}">
					{#if isReplay}
						{replayLabel(run)}
					{:else}
						{run.run_name}
					{/if}
				</span>
				{#if run.errors.length > 0}
					<span class="inline-block rounded-full bg-destructive" style="width: 0.375rem; height: 0.375rem;"></span>
				{/if}
			</div>
			{#if !isReplay}
				<div class="flex items-center" style="gap: 0.5rem; margin-top: 0.375rem;">
					<span class="text-xs text-muted-foreground">{run.provider}</span>
					<span class="text-xs text-muted-foreground/70">&middot;</span>
					<span class="text-xs text-muted-foreground">{run.session_mode}</span>
				</div>
			{:else}
				<div style="margin-top: 0.125rem;">
					<span class="text-xs text-muted-foreground font-mono" style="font-size: 10px; opacity: 0.7;">{run.run_name}</span>
				</div>
			{/if}
		</td>
		<td style="padding: 1rem 1.25rem;" class="text-muted-foreground font-mono text-xs">{run.model}</td>
		<td style="padding: 1rem 1.25rem;" class="text-center tabular-nums">{run.session_count}</td>
		<td style="padding: 1rem 1.25rem;" class="text-right tabular-nums">{run.total_steps}</td>
		<td style="padding: 1rem 1.25rem;" class="text-right text-xs text-muted-foreground">
			{#if !isReplay}
				{@const rs = run.resample_count ?? 0}
				{@const vs = run.variant_count ?? 0}
				{@const rps = groups.find(g => g.run.run_name === run.run_name)?.replays.length ?? 0}
				{#if rs || rps}
					<div class="flex flex-col items-end gap-0.5">
						{#if rs}<span>{rs} resample{rs !== 1 ? 's' : ''}{#if vs} ({vs} variant{vs !== 1 ? 's' : ''}){/if}</span>{/if}
						{#if rps}<span>{rps} replay{rps !== 1 ? 's' : ''}</span>{/if}
					</div>
				{:else}
					<span class="text-muted-foreground/40">—</span>
				{/if}
			{:else}
				<span class="text-muted-foreground/40">—</span>
			{/if}
		</td>
		<td style="padding: 1rem 1.25rem;" class="text-right tabular-nums font-mono text-xs">
			{formatCost(run.total_cost_usd)}
		</td>
		<td style="padding: 1rem 1.25rem;">
			<div class="flex flex-wrap" style="gap: 0.375rem;">
				{#each run.tags.filter(t => t !== 'replay') as tag}
					<span class="rounded-full text-xs border border-border text-foreground/80" style="padding: 0.125rem 0.5rem;">{tag}</span>
				{/each}
			</div>
		</td>
		<td style="padding: 1rem 1.25rem;" class="text-right text-muted-foreground text-xs whitespace-nowrap tabular-nums">
			{formatDate(run.started_at)}
		</td>
	</tr>
{/snippet}

<div style="display: flex; flex-direction: column; gap: 2rem;">
	<div class="flex items-center justify-between">
		<h1 class="text-lg font-semibold">Runs</h1>
		<input
			type="text"
			placeholder="Filter by name, model, or tag..."
			bind:value={search}
			style="height: 2.375rem; padding: 0 0.75rem; width: 18rem;"
			class="text-sm rounded-md border border-input bg-background placeholder:text-muted-foreground/70 focus:outline-none focus:ring-2 focus:ring-ring/20 focus:border-ring transition-colors"
		/>
	</div>

	{#if filtered.length === 0}
		<p class="text-muted-foreground text-sm text-center" style="padding: 3rem 0;">
			{data.runs.length === 0 ? "No runs found. Check your RUNS_DIR." : "No runs match your filter."}
		</p>
	{:else}
		<div class="rounded-lg border border-border overflow-hidden">
			<table class="w-full text-sm">
				<thead>
					<tr class="bg-muted/50 border-b border-border text-xs text-muted-foreground">
						<th class="text-left font-medium" style="padding: 0.875rem 1.25rem;">Run</th>
						<th class="text-left font-medium" style="padding: 0.875rem 1.25rem;">Model</th>
						<th class="text-center font-medium" style="padding: 0.875rem 1.25rem;">Sessions</th>
						<th class="text-right font-medium" style="padding: 0.875rem 1.25rem;">Steps</th>
						<th class="text-right font-medium" style="padding: 0.875rem 1.25rem;">Resamples</th>
						<th class="text-right font-medium" style="padding: 0.875rem 1.25rem;">Cost</th>
						<th class="text-left font-medium" style="padding: 0.875rem 1.25rem;">Tags</th>
						<th class="text-right font-medium" style="padding: 0.875rem 1.25rem;">Date</th>
					</tr>
				</thead>
				<tbody>
					{#each filtered as group}
						{@render runRow(group.run, false)}
						{#if group.replays.length > 0}
							{@const isExpanded = expandedGroups.has(group.run.run_name)}
							<tr class="border-b border-border last:border-b-0">
								<td colspan="8" style="padding: 0 1.25rem 0 2.5rem;">
									<button
										onclick={(e) => { e.stopPropagation(); toggleReplays(group.run.run_name); }}
										class="flex items-center gap-1.5 py-1.5 text-[11px] text-muted-foreground/70 hover:text-muted-foreground transition-colors"
									>
										<span class="transition-transform {isExpanded ? 'rotate-90' : ''}" style="font-size: 10px;">▶</span>
										{group.replays.length} replay{group.replays.length !== 1 ? 's' : ''}
									</button>
								</td>
							</tr>
							{#if isExpanded}
								{#each group.replays as replay}
									{@render runRow(replay, true)}
								{/each}
							{/if}
						{/if}
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>
