<script lang="ts">
	import ThinkingBlock from "./ThinkingBlock.svelte";
	import InputDiff from "./InputDiff.svelte";
	import { renderMarkdown } from "$lib/utils/markdown";

	interface ContentBlock {
		type: string;
		text?: string;
		thinking?: string;
		name?: string;
		input?: Record<string, unknown>;
		id?: string;
	}

	interface Sample {
		id?: string;
		content?: ContentBlock[];
		usage?: {
			input_tokens?: number;
			output_tokens?: number;
		};
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

	let {
		samples,
		variants: rawVariants = null,
		runName = "",
		sessionIndex = 0,
		requestIndex = undefined as number | undefined,
	}: {
		samples: Sample[];
		variants?: VariantData[] | null;
		runName?: string;
		sessionIndex?: number | string;
		requestIndex?: number;
	} = $props();

	let variants = $derived(rawVariants ?? []);

	// Source: "vanilla" or variant id
	let activeSource = $state<string>("vanilla");
	let activeTab = $state(0);

	// Auto-select first variant with samples if vanilla is empty
	$effect(() => {
		if (samples.length === 0 && variants.length > 0 && activeSource === "vanilla") {
			const withSamples = variants.find((v: VariantData) => v.samples.length > 0);
			if (withSamples) activeSource = withSamples.id;
			else activeSource = variants[0].id;
		}
	});

	let activeSamples = $derived.by(() => {
		if (activeSource === "vanilla") return samples;
		const v = variants.find((vr: VariantData) => vr.id === activeSource);
		return v?.samples ?? [];
	});

	let activeVariant = $derived.by(() => {
		if (activeSource === "vanilla") return null;
		return variants.find((vr: VariantData) => vr.id === activeSource) ?? null;
	});

	let activeSample = $derived(activeSamples[activeTab]);

	function getBlocks(sample: Sample): ContentBlock[] {
		return sample.content ?? [];
	}

	const TOOL_INPUT_LIMIT = 500;

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
</script>

<div
	class="rounded-lg border {activeVariant
		? 'border-violet-400/40 dark:border-violet-500/30 bg-violet-50 dark:bg-violet-950/10'
		: 'border-amber-400/40 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-950/10'}"
>
	<!-- Source tabs (when variants exist) -->
	{#if variants.length > 0}
		<div
			class="flex items-center gap-1 px-3 py-1.5 border-b border-border overflow-x-auto"
		>
			<button
				onclick={() => {
					activeSource = "vanilla";
					activeTab = 0;
				}}
				class="px-2 py-0.5 text-[10px] rounded transition-colors {activeSource === 'vanilla'
					? 'bg-amber-200 dark:bg-amber-500/20 text-amber-900 dark:text-amber-200 font-medium'
					: 'text-muted-foreground hover:text-foreground'}"
			>
				Original ({samples.length})
			</button>
			{#each variants as variant}
				<button
					onclick={() => {
						activeSource = variant.id;
						activeTab = 0;
					}}
					class="px-2 py-0.5 text-[10px] rounded transition-colors {activeSource ===
					variant.id
						? 'bg-violet-200 dark:bg-violet-500/20 text-violet-900 dark:text-violet-200 font-medium'
						: 'text-muted-foreground hover:text-foreground'}"
				>
					{variant.label} ({variant.samples.length})
				</button>
			{/each}
		</div>
	{/if}

	<!-- Variant diff -->
	{#if activeVariant}
		<div class="px-3 pt-2">
			<InputDiff edits={activeVariant.edits} />
		</div>
	{/if}

	<!-- Sample tab bar -->
	<div class="flex items-center gap-1 px-3 py-2 border-b border-border overflow-x-auto">
		<span class="text-[11px] text-muted-foreground font-medium mr-2"
			>{activeVariant ? activeVariant.label : "Resamples"}</span
		>
		{#each activeSamples as _, i}
			<button
				onclick={() => (activeTab = i)}
				class="px-2 py-0.5 text-[11px] rounded transition-colors {activeTab === i
					? activeVariant
						? 'bg-violet-200 dark:bg-violet-500/20 text-violet-900 dark:text-violet-200 font-medium'
						: 'bg-amber-200 dark:bg-amber-500/20 text-amber-900 dark:text-amber-200 font-medium'
					: 'text-muted-foreground hover:text-foreground'}"
			>
				#{i + 1}
			</button>
		{/each}
		{#if runName && requestIndex !== undefined}
			<a
				href="/runs/{runName}/sessions/{sessionIndex}/resamples?request={requestIndex}"
				class="ml-auto text-[11px] text-muted-foreground hover:text-foreground transition-colors"
			>
				Full view &rarr;
			</a>
		{/if}
	</div>

	<!-- Active sample content -->
	{#if activeSample}
		<div class="px-4 py-3 space-y-3">
			{#if activeSample.error}
				<div class="text-xs text-destructive bg-destructive/10 rounded px-3 py-2">
					Error: {activeSample.error}
				</div>
			{:else}
				{#each getBlocks(activeSample) as block, blockIdx}
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
						{@const toolId = `${activeSource}-${activeTab}-${blockIdx}`}
						{@const full = block.input ? formatToolInput(block.input) : ""}
						{@const isLong = block.input ? isToolInputLong(block.input) : false}
						{@const isExpanded = expandedToolInputs.has(toolId)}
						<div class="rounded-md border border-border bg-muted/30 px-3 py-2">
							<div class="text-[11px] text-muted-foreground font-medium mb-1">
								Tool: <span class="font-mono">{block.name}</span>
							</div>
							{#if block.input}
								<pre
									class="text-[10px] text-muted-foreground font-mono whitespace-pre-wrap">{isLong && !isExpanded ? full.slice(0, TOOL_INPUT_LIMIT) + "\n..." : full}</pre>
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

				<!-- Usage summary -->
				{#if activeSample.usage}
					<div
						class="flex items-center gap-3 pt-2 border-t border-border text-[10px] text-muted-foreground tabular-nums"
					>
						{#if activeSample.usage.input_tokens}
							<span>{activeSample.usage.input_tokens.toLocaleString()} input</span>
						{/if}
						{#if activeSample.usage.output_tokens}
							<span>{activeSample.usage.output_tokens.toLocaleString()} output</span>
						{/if}
						{#if activeSample.stop_reason}
							<span>stop: {activeSample.stop_reason}</span>
						{/if}
					</div>
				{/if}
			{/if}
		</div>
	{:else if activeSamples.length === 0}
		<div class="px-4 py-3 text-xs text-muted-foreground">No samples yet</div>
	{/if}
</div>
