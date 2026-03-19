<script lang="ts">
	import ThinkingBlock from "$lib/components/chat/ThinkingBlock.svelte";
	import InputDiff from "$lib/components/chat/InputDiff.svelte";
	import MessageEditor from "$lib/components/chat/MessageEditor.svelte";
	import { renderMarkdown } from "$lib/utils/markdown";

	let { data } = $props();
	let runName = $derived(data.meta.run_name);
	let sessionIndex = $derived(data.sessionIndex);
	let resampleGroups = $derived(data.resampleGroups);
	let hasRawDumps = $derived(data.hasRawDumps);
	let mainRequestIndices = $derived(data.mainRequestIndices);

	// Which request to focus
	let focusedRequest = $state<number | null>(null);

	$effect(() => {
		const params = new URLSearchParams(window.location.search);
		const req = params.get("request");
		if (req) {
			focusedRequest = parseInt(req);
		} else if (resampleGroups.length > 0) {
			focusedRequest = resampleGroups[0].requestIndex;
		}
	});

	// ---------- Types ----------
	interface ContentBlock {
		type: string;
		text?: string;
		thinking?: string;
		name?: string;
		input?: Record<string, unknown>;
	}

	interface Sample {
		content?: ContentBlock[];
		usage?: { input_tokens?: number; output_tokens?: number };
		stop_reason?: string;
		error?: string;
	}

	interface VariantEdit {
		path: string;
		original: string;
		replacement: string;
	}

	interface VariantData {
		id: string;
		label: string;
		edits: VariantEdit[];
		samples: Sample[];
	}

	interface ResampleGroup {
		requestIndex: number;
		sampleCount: number;
		variants: { id: string; label: string; edits: VariantEdit[]; sampleCount: number }[];
	}

	// ---------- Loaded data ----------
	let loadedSamples = $state<Sample[]>([]);
	let loadedVariants = $state<VariantData[]>([]);
	let rawMessages = $state<unknown[] | null>(null);
	let isLoading = $state(false);
	let loadError = $state<string | null>(null);

	// Track which sample tab is active per source
	let activeTabs = $state<Record<string, number>>({});

	function getActiveTab(sourceId: string): number {
		return activeTabs[sourceId] ?? 0;
	}

	function setActiveTab(sourceId: string, idx: number) {
		activeTabs = { ...activeTabs, [sourceId]: idx };
	}

	// Track which source cards are collapsed
	let collapsedSources = $state<Set<string>>(new Set());

	function toggleCollapse(sourceId: string) {
		const next = new Set(collapsedSources);
		if (next.has(sourceId)) next.delete(sourceId);
		else next.add(sourceId);
		collapsedSources = next;
	}

	// Fetch full data when focused request changes
	$effect(() => {
		if (focusedRequest !== null) {
			loadRequestData(focusedRequest);
		}
	});

	async function loadRequestData(reqIdx: number) {
		isLoading = true;
		loadError = null;
		try {
			const params = new URLSearchParams({
				runName,
				sessionIndex: String(sessionIndex),
				requestIndex: String(reqIdx),
				includeRaw: "true",
			});
			const resp = await fetch(`/api/resample?${params}`);
			if (!resp.ok) throw new Error(`${resp.status}: ${await resp.text()}`);
			const result = await resp.json();
			loadedSamples = result.samples ?? [];
			loadedVariants = result.variants ?? [];
			rawMessages = result.rawMessages ?? null;
			activeTabs = {};
			collapsedSources = new Set();
		} catch (e: unknown) {
			loadError = e instanceof Error ? e.message : String(e);
		} finally {
			isLoading = false;
		}
	}

	// Silently reload after creating new resamples/variants
	async function reloadData() {
		if (focusedRequest === null) return;
		try {
			const params = new URLSearchParams({
				runName,
				sessionIndex: String(sessionIndex),
				requestIndex: String(focusedRequest),
				includeRaw: "true",
			});
			const resp = await fetch(`/api/resample?${params}`);
			if (!resp.ok) return;
			const result = await resp.json();
			loadedSamples = result.samples ?? [];
			loadedVariants = result.variants ?? [];
			rawMessages = result.rawMessages ?? null;
		} catch {
			// silent
		}
	}

	// ---------- Resample form ----------
	let showResampleForm = $state(false);
	let resampleRequestIdx = $state(1);
	let resampleCount = $state(5);
	let isResampling = $state(false);
	let resampleError = $state<string | null>(null);

	// ---------- Editor ----------
	let showEditor = $state(false);
	let isLoadingEditor = $state(false);

	// ---------- Helpers ----------
	function getBlocks(sample: Sample): ContentBlock[] {
		return sample.content ?? [];
	}

	function getThinking(sample: Sample): string {
		return getBlocks(sample)
			.filter((b) => b.type === "thinking" && b.thinking)
			.map((b) => b.thinking!)
			.join("\n\n---\n\n");
	}

	function getText(sample: Sample): string {
		return getBlocks(sample)
			.filter((b) => b.type === "text" && b.text)
			.map((b) => b.text!)
			.join("\n\n");
	}

	function getToolCalls(sample: Sample): ContentBlock[] {
		return getBlocks(sample).filter((b) => b.type === "tool_use");
	}

	const TOOL_INPUT_LIMIT = 300;

	function formatToolInput(input: Record<string, unknown>): string {
		return JSON.stringify(input, null, 2);
	}

	function isToolInputLong(input: Record<string, unknown>): boolean {
		return JSON.stringify(input, null, 2).length > TOOL_INPUT_LIMIT;
	}

	let expandedToolInputs = $state<Set<string>>(new Set());

	function toggleToolInput(id: string) {
		const next = new Set(expandedToolInputs);
		if (next.has(id)) next.delete(id);
		else next.add(id);
		expandedToolInputs = next;
	}

	function sampleStats(samples: Sample[]) {
		if (samples.length === 0) return null;
		const avgTokens = Math.round(
			samples.reduce((sum, s) => sum + (s.usage?.output_tokens ?? 0), 0) / samples.length,
		);
		const toolSets = [...new Set(samples.map((s) => getToolCalls(s).map((t) => t.name).join(", ")))];
		const stops = [...new Set(samples.map((s) => s.stop_reason ?? "?"))];
		return { avgTokens, toolSets, stops };
	}

	// ---------- Actions ----------
	async function doResample() {
		isResampling = true;
		resampleError = null;
		try {
			const resp = await fetch("/api/resample", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					runName,
					sessionIndex,
					requestIndex: resampleRequestIdx,
					count: resampleCount,
				}),
			});
			if (!resp.ok) throw new Error(`${resp.status}: ${await resp.text()}`);
			showResampleForm = false;
			focusedRequest = resampleRequestIdx;
			await reloadData();
		} catch (e: unknown) {
			resampleError = e instanceof Error ? e.message : String(e);
		} finally {
			isResampling = false;
		}
	}

	async function addMoreSamples(isVariant: boolean, variantId?: string) {
		if (focusedRequest === null) return;
		isResampling = true;
		resampleError = null;
		try {
			const body: Record<string, unknown> = {
				runName,
				sessionIndex,
				requestIndex: focusedRequest,
				count: 3,
			};
			// For variants, we need to re-run with the same edits
			if (isVariant && variantId) {
				const variant = loadedVariants.find((v) => v.id === variantId);
				if (variant) {
					body.variant = { label: variant.label, edits: variant.edits };
					// Override: append to existing variant dir by using same label
				}
			}
			const resp = await fetch("/api/resample", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify(body),
			});
			if (!resp.ok) throw new Error(`${resp.status}: ${await resp.text()}`);
			await reloadData();
		} catch (e: unknown) {
			resampleError = e instanceof Error ? e.message : String(e);
		} finally {
			isResampling = false;
		}
	}

	function openEditor() {
		if (!rawMessages || rawMessages.length === 0) {
			resampleError = "No raw API messages available for this request";
			return;
		}
		showEditor = true;
	}

	async function handleEditorSubmit(
		edits: { path: string; original: string; replacement: string }[],
		label: string,
		count: number,
	) {
		if (focusedRequest === null) return;
		isResampling = true;
		resampleError = null;
		try {
			const resp = await fetch("/api/resample", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					runName,
					sessionIndex,
					requestIndex: focusedRequest,
					count,
					variant: { label, edits },
				}),
			});
			if (!resp.ok) throw new Error(`${resp.status}: ${await resp.text()}`);
			await reloadData();
			showEditor = false;
		} catch (e: unknown) {
			resampleError = e instanceof Error ? e.message : String(e);
		} finally {
			isResampling = false;
		}
	}

	let totalSamples = $derived(
		loadedSamples.length +
			loadedVariants.reduce((sum, v) => sum + v.samples.length, 0),
	);
</script>

<!-- Request selector bar -->
<div class="flex flex-wrap items-center border-b border-border" style="gap: 0.5rem; margin-bottom: 1.75rem; padding-bottom: 1.125rem;">
	{#if resampleGroups.length === 0}
		<p class="text-sm text-muted-foreground">No resamples yet.</p>
	{:else}
		{#each resampleGroups as group}
			{@const total = group.sampleCount + group.variants.reduce((s: number, v: { sampleCount: number }) => s + v.sampleCount, 0)}
			<button
				onclick={() => {
					focusedRequest = group.requestIndex;
				}}
				style="padding: 0.5rem 0.875rem;"
				class="text-sm rounded-md border transition-colors {focusedRequest ===
				group.requestIndex
					? 'border-primary/50 bg-primary/10 text-foreground font-medium'
					: 'border-border text-muted-foreground hover:text-foreground hover:bg-accent'}"
			>
				Request #{group.requestIndex}
				<span class="text-muted-foreground/60" style="margin-left: 0.375rem;">
					{total} sample{total !== 1 ? "s" : ""}
					{#if group.variants.length > 0}
						<span class="text-violet-600 dark:text-violet-400/80">
							· {group.variants.length} variant{group.variants.length !== 1 ? "s" : ""}
						</span>
					{/if}
				</span>
			</button>
		{/each}
	{/if}

	<button
		onclick={() => (showResampleForm = !showResampleForm)}
		style="padding: 0.5rem 0.875rem; margin-left: 0.5rem;"
		class="text-sm rounded-md border border-dashed border-border text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
	>
		+ New resample
	</button>
</div>

<!-- New resample form -->
{#if showResampleForm}
	<div class="mb-6 p-4 rounded-lg border border-border bg-muted/30 max-w-lg">
		<div class="flex items-center gap-3">
			<label class="text-xs text-muted-foreground">
				Request #:
				<input
					type="number"
					bind:value={resampleRequestIdx}
					min="1"
					max={mainRequestIndices.length || 999}
					class="w-20 px-2 py-1 text-xs rounded border border-border bg-background ml-1"
				/>
			</label>
			<label class="text-xs text-muted-foreground">
				Count:
				<input
					type="number"
					bind:value={resampleCount}
					min="1"
					max="20"
					class="w-16 px-2 py-1 text-xs rounded border border-border bg-background ml-1"
				/>
			</label>
			<button
				onclick={doResample}
				disabled={isResampling || !hasRawDumps}
				class="px-4 py-1.5 text-xs rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
			>
				{isResampling ? "Resampling..." : "Run"}
			</button>
		</div>
		{#if !hasRawDumps}
			<p class="text-xs text-destructive mt-2">
				No raw dumps available. Re-run with API capture enabled.
			</p>
		{/if}
		{#if resampleError}
			<p class="text-xs text-destructive mt-2">{resampleError}</p>
		{/if}
	</div>
{/if}

<!-- Focused request detail -->
{#if focusedRequest !== null}
	{#if isLoading}
		<div class="text-xs text-muted-foreground py-8 text-center">Loading...</div>
	{:else if loadError}
		<div class="text-xs text-destructive py-4">{loadError}</div>
	{:else}
		<!-- Action bar -->
		<div class="flex items-center" style="gap: 0.625rem; margin-bottom: 1.25rem;">
			<h3 class="text-sm font-medium text-foreground">Request #{focusedRequest}</h3>
			<span class="text-xs text-muted-foreground/60">{totalSamples} total samples</span>
			<div style="margin-left: auto; display: flex; align-items: center; gap: 0.5rem;">
				{#if hasRawDumps}
					<button
						onclick={openEditor}
						style="padding: 0.375rem 0.75rem;"
						class="text-xs rounded-md border border-dashed border-violet-500/40 text-violet-600 dark:text-violet-400/80 hover:bg-violet-100 dark:hover:bg-violet-500/10 transition-colors"
					>
						+ Edit & Resample
					</button>
				{/if}
			</div>
		</div>

		{#if resampleError && !showEditor}
			<p class="text-xs text-destructive mb-4">{resampleError}</p>
		{/if}

		<!-- Editor panel -->
		{#if showEditor && rawMessages}
			<div class="mb-6 p-4 rounded-lg border border-violet-400/40 dark:border-violet-500/30 bg-violet-50 dark:bg-violet-950/10">
				<div class="flex items-center justify-between mb-3">
					<h3 class="text-xs font-medium text-violet-700 dark:text-violet-300">Edit messages & resample</h3>
					<button
						onclick={() => (showEditor = false)}
						disabled={isResampling}
						class="text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-30">&times; Close</button
					>
				</div>
				{#if isResampling}
					<div class="py-6 text-center text-xs text-violet-600 dark:text-violet-400/80">
						Running variant... this may take a moment
					</div>
				{:else}
					<MessageEditor
						messages={rawMessages as any}
						lastN={8}
						onsubmit={handleEditorSubmit}
					/>
				{/if}
				{#if resampleError}
					<p class="text-xs text-destructive mt-2">{resampleError}</p>
				{/if}
			</div>
		{/if}

		<!-- ALL SOURCES shown vertically -->
		<div class="space-y-4">
			<!-- Original samples -->
			{#if loadedSamples.length > 0}
				{@const stats = sampleStats(loadedSamples)}
				{@const isCollapsed = collapsedSources.has("vanilla")}
				<div class="rounded-lg border border-amber-400/40 dark:border-amber-500/30 bg-amber-50/50 dark:bg-amber-950/10">
					<!-- Source header -->
					<button
						onclick={() => toggleCollapse("vanilla")}
						class="w-full flex items-center text-left hover:bg-amber-100/50 dark:hover:bg-amber-500/5 transition-colors rounded-t-lg"
						style="gap: 0.75rem; padding: 0.75rem 1rem;"
					>
						<span class="text-xs text-muted-foreground/60 transition-transform {isCollapsed ? '' : 'rotate-90'}">&rsaquo;</span>
						<span class="text-sm font-medium text-amber-800 dark:text-amber-300">Original</span>
						<span class="text-xs text-muted-foreground">{loadedSamples.length} samples</span>
						{#if stats}
							<span class="text-xs text-muted-foreground/60 tabular-nums" style="margin-left: auto;">
								avg {stats.avgTokens.toLocaleString()} tokens · stop: {stats.stops.join(", ")}
							</span>
						{/if}
					</button>

					{#if !isCollapsed}
						<!-- Sample tabs + content -->
						<div class="border-t border-amber-300/30 dark:border-amber-500/20">
							<div class="flex items-center overflow-x-auto" style="gap: 0.25rem; padding: 0.625rem 1rem;">
								{#each loadedSamples as _, i}
									<button
										onclick={() => setActiveTab("vanilla", i)}
										style="padding: 0.25rem 0.625rem;"
										class="text-xs rounded transition-colors {getActiveTab('vanilla') === i
											? 'bg-amber-200 dark:bg-amber-500/20 text-amber-900 dark:text-amber-200 font-medium'
											: 'text-muted-foreground hover:text-foreground'}"
									>
										#{i + 1}
									</button>
								{/each}
								<button
									onclick={() => addMoreSamples(false)}
									disabled={isResampling}
									style="padding: 0.25rem 0.625rem;"
									class="text-xs text-muted-foreground/50 hover:text-foreground transition-colors disabled:opacity-30"
								>
									+more
								</button>
							</div>

							{#if loadedSamples[getActiveTab("vanilla")]}
								{@render sampleContent(loadedSamples[getActiveTab("vanilla")], "vanilla")}
							{/if}
						</div>
					{/if}
				</div>
			{/if}

			<!-- Variants -->
			{#each loadedVariants as variant}
				{@const stats = sampleStats(variant.samples)}
				{@const isCollapsed = collapsedSources.has(variant.id)}
				<div class="rounded-lg border border-violet-400/40 dark:border-violet-500/30 bg-violet-50/50 dark:bg-violet-950/10">
					<!-- Variant header -->
					<button
						onclick={() => toggleCollapse(variant.id)}
						class="w-full flex items-center text-left hover:bg-violet-100/50 dark:hover:bg-violet-500/5 transition-colors rounded-t-lg"
						style="gap: 0.75rem; padding: 0.75rem 1rem;"
					>
						<span class="text-xs text-muted-foreground/60 transition-transform {isCollapsed ? '' : 'rotate-90'}">&rsaquo;</span>
						<span class="text-sm font-medium text-violet-800 dark:text-violet-300">{variant.label}</span>
						<span class="text-xs text-muted-foreground">{variant.samples.length} samples</span>
						{#if stats}
							<span class="text-xs text-muted-foreground/60 tabular-nums" style="margin-left: auto;">
								avg {stats.avgTokens.toLocaleString()} tokens · stop: {stats.stops.join(", ")}
							</span>
						{/if}
					</button>

					{#if !isCollapsed}
						<div class="border-t border-violet-300/30 dark:border-violet-500/20">
							<!-- Diff -->
							{#if variant.edits.length > 0}
								<div class="px-4 pt-2">
									<InputDiff edits={variant.edits} expanded={true} />
								</div>
							{/if}

							<!-- Samples -->
							{#if variant.samples.length > 0}
								<div class="flex items-center overflow-x-auto" style="gap: 0.25rem; padding: 0.625rem 1rem;">
									{#each variant.samples as _, i}
										<button
											onclick={() => setActiveTab(variant.id, i)}
											style="padding: 0.25rem 0.625rem;"
											class="text-xs rounded transition-colors {getActiveTab(variant.id) === i
												? 'bg-violet-200 dark:bg-violet-500/20 text-violet-900 dark:text-violet-200 font-medium'
												: 'text-muted-foreground hover:text-foreground'}"
										>
											#{i + 1}
										</button>
									{/each}
								</div>

								{#if variant.samples[getActiveTab(variant.id)]}
									{@render sampleContent(variant.samples[getActiveTab(variant.id)], variant.id)}
								{/if}
							{:else}
								<div class="px-4 py-3 text-xs text-muted-foreground/50">No samples yet</div>
							{/if}
						</div>
					{/if}
				</div>
			{/each}

			<!-- Empty state -->
			{#if loadedSamples.length === 0 && loadedVariants.length === 0}
				<div class="text-center py-8 text-sm text-muted-foreground/50">
					No resamples for this request yet.
					{#if hasRawDumps}
						<button
							onclick={() => { resampleRequestIdx = focusedRequest ?? 1; showResampleForm = true; }}
							class="text-primary hover:underline ml-1"
						>
							Create one
						</button>
					{/if}
				</div>
			{/if}
		</div>
	{/if}
{/if}

<!-- Snippet: render a single sample's content -->
{#snippet sampleContent(sample: Sample, sourceId: string)}
	<div class="px-4 py-3 space-y-3">
		{#if sample.error}
			<div class="text-xs text-destructive bg-destructive/10 rounded px-3 py-2">
				Error: {sample.error}
			</div>
		{:else}
			{#each getBlocks(sample) as block, blockIdx}
				{#if block.type === "thinking" && block.thinking}
					<ThinkingBlock content={block.thinking} />
				{:else if block.type === "text" && block.text}
					{@const html = renderMarkdown(block.text)}
					<div
						class="text-sm prose prose-sm dark:prose-invert max-w-none prose-p:my-1.5 prose-headings:my-2 prose-ul:my-1.5 prose-ol:my-1.5 prose-li:my-0.5 prose-pre:my-2 prose-pre:bg-muted prose-pre:text-xs prose-code:text-xs prose-code:before:content-none prose-code:after:content-none"
						style="color: var(--foreground);"
					>
						{@html html}
					</div>
				{:else if block.type === "tool_use"}
					{@const toolId = `${sourceId}-${blockIdx}`}
					{@const full = block.input ? formatToolInput(block.input) : ""}
					{@const isLong = block.input ? isToolInputLong(block.input) : false}
					{@const isExpanded = expandedToolInputs.has(toolId)}
					<div class="rounded-md border border-border/50 bg-muted/30 px-3 py-2">
						<div class="text-[11px] text-muted-foreground font-medium mb-1">
							Tool: <span class="font-mono">{block.name}</span>
						</div>
						{#if block.input}
							<pre class="text-[10px] text-muted-foreground/80 font-mono whitespace-pre-wrap">{isLong && !isExpanded ? full.slice(0, TOOL_INPUT_LIMIT) + "\n..." : full}</pre>
							{#if isLong}
								<button
									onclick={() => toggleToolInput(toolId)}
									class="text-[10px] text-primary hover:underline mt-1"
								>
									{isExpanded ? "Show less" : "Show more"}
								</button>
							{/if}
						{/if}
					</div>
				{/if}
			{/each}

			{#if sample.usage}
				<div
					class="flex items-center gap-3 pt-2 border-t border-border/50 text-[10px] text-muted-foreground/60 tabular-nums"
				>
					{#if sample.usage.input_tokens}
						<span>{sample.usage.input_tokens.toLocaleString()} input</span>
					{/if}
					{#if sample.usage.output_tokens}
						<span>{sample.usage.output_tokens.toLocaleString()} output</span>
					{/if}
					{#if sample.stop_reason}
						<span>stop: {sample.stop_reason}</span>
					{/if}
				</div>
			{/if}
		{/if}
	</div>
{/snippet}
