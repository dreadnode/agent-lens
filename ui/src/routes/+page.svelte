<script lang="ts">
	import { formatCost, formatDate } from "$lib/utils/format";

	let { data } = $props();
	let search = $state("");

	let filtered = $derived(
		data.runs.filter((r) => {
			if (!search) return true;
			const q = search.toLowerCase();
			return (
				r.run_name.toLowerCase().includes(q) ||
				r.model.toLowerCase().includes(q) ||
				r.tags.some((t: string) => t.toLowerCase().includes(q))
			);
		})
	);
</script>

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
						<th class="text-right font-medium" style="padding: 0.875rem 1.25rem;">Cost</th>
						<th class="text-left font-medium" style="padding: 0.875rem 1.25rem;">Tags</th>
						<th class="text-right font-medium" style="padding: 0.875rem 1.25rem;">Date</th>
					</tr>
				</thead>
				<tbody>
					{#each filtered as run}
						<tr
							class="border-b border-border last:border-b-0 hover:bg-muted/30 transition-colors cursor-pointer"
							onclick={() => window.location.href = `/runs/${run.run_name}`}
						>
							<td style="padding: 1rem 1.25rem;">
								<span class="font-medium text-sm">
									{run.run_name}
								</span>
								{#if run.errors.length > 0}
									<span class="inline-block rounded-full bg-destructive" style="margin-left: 0.375rem; width: 0.375rem; height: 0.375rem;"></span>
								{/if}
								<div class="flex items-center" style="gap: 0.5rem; margin-top: 0.375rem;">
									<span class="text-xs text-muted-foreground">{run.provider}</span>
									<span class="text-xs text-muted-foreground/70">&middot;</span>
									<span class="text-xs text-muted-foreground">{run.session_mode}</span>
								</div>
							</td>
							<td style="padding: 1rem 1.25rem;" class="text-muted-foreground font-mono text-xs">{run.model}</td>
							<td style="padding: 1rem 1.25rem;" class="text-center tabular-nums">{run.session_count}</td>
							<td style="padding: 1rem 1.25rem;" class="text-right tabular-nums">{run.total_steps}</td>
							<td style="padding: 1rem 1.25rem;" class="text-right tabular-nums font-mono text-xs">
								{formatCost(run.total_cost_usd)}
							</td>
							<td style="padding: 1rem 1.25rem;">
								<div class="flex flex-wrap" style="gap: 0.375rem;">
									{#each run.tags as tag}
										<span class="rounded-full text-xs border border-border text-foreground/80" style="padding: 0.125rem 0.5rem;">{tag}</span>
									{/each}
								</div>
							</td>
							<td style="padding: 1rem 1.25rem;" class="text-right text-muted-foreground text-xs whitespace-nowrap tabular-nums">
								{formatDate(run.started_at)}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>
