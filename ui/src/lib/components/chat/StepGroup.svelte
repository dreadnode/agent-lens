<script lang="ts">
	import type { StepItem } from "./ChatView.svelte";
	import ThinkingBlock from "./ThinkingBlock.svelte";
	import ToolCallBlock from "./ToolCallBlock.svelte";
	import ResamplePanel from "./ResamplePanel.svelte";
	import MessageEditor from "./MessageEditor.svelte";
	import { renderMarkdown } from "$lib/utils/markdown";

	let {
		items,
		stepIds,
		runName = "",
		sessionIndex = 0 as number | string,
		requestIndex = undefined as number | undefined,
		canResample = false,
		existingResampleCount = 0,
	}: {
		items: StepItem[];
		stepIds: number[];
		runName?: string;
		sessionIndex?: number | string;
		requestIndex?: number;
		canResample?: boolean;
		existingResampleCount?: number;
	} = $props();

	let stepRange = $derived(
		stepIds.length === 1
			? `Step ${stepIds[0]}`
			: `Steps ${stepIds[0]}\u2013${stepIds[stepIds.length - 1]}`,
	);

	// Resample state
	let showResampleForm = $state(false);
	let resampleCount = $state(5);
	let isResampling = $state(false);
	let resampleResults = $state<object[] | null>(null);
	let resampleVariants = $state<object[] | null>(null);
	let resampleError = $state<string | null>(null);

	// Editor state
	let showEditor = $state(false);
	let editorMessages = $state<unknown[] | null>(null);
	let editorResponseContent = $state<unknown[] | null>(null);
	let isLoadingEditor = $state(false);

	// Element refs for scroll-into-view
	let editorEl: HTMLDivElement | undefined = $state();
	let resultsEl: HTMLDivElement | undefined = $state();

	// Auto-load existing resamples on mount
	$effect(() => {
		if (existingResampleCount > 0 && requestIndex !== undefined && !resampleResults && !resampleVariants) {
			loadExisting();
		}
	});

	async function loadExisting() {
		if (requestIndex === undefined) return;
		try {
			const resp = await fetch(
				`/api/resample?runName=${encodeURIComponent(runName)}&sessionIndex=${sessionIndex}&requestIndex=${requestIndex}`,
			);
			if (resp.ok) {
				const data = await resp.json();
				// Always update — even if samples/variants are empty arrays, replace stale data
				resampleResults = data.samples ?? [];
				resampleVariants = data.variants ?? [];
			}
		} catch {
			// ignore
		}
	}

	let hasAnyResults = $derived(
		(resampleResults && resampleResults.length > 0) ||
			(resampleVariants && resampleVariants.length > 0),
	);

	async function doResample() {
		if (requestIndex === undefined) return;
		isResampling = true;
		resampleError = null;

		try {
			const resp = await fetch("/api/resample", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					runName,
					sessionIndex,
					requestIndex,
					count: resampleCount,
				}),
			});

			if (!resp.ok) {
				const text = await resp.text();
				throw new Error(`${resp.status}: ${text}`);
			}

			await loadExisting();
			showResampleForm = false;
			// Scroll to results after next render
			requestAnimationFrame(() => resultsEl?.scrollIntoView({ behavior: "smooth", block: "nearest" }));
		} catch (e: unknown) {
			resampleError = e instanceof Error ? e.message : String(e);
		} finally {
			isResampling = false;
		}
	}

	async function openEditor() {
		if (requestIndex === undefined) return;
		isLoadingEditor = true;
		resampleError = null;
		try {
			const resp = await fetch(
				`/api/resample?runName=${encodeURIComponent(runName)}&sessionIndex=${sessionIndex}&requestIndex=${requestIndex}&includeRaw=true`,
			);
			if (!resp.ok) {
				resampleError = `Failed to load messages: ${resp.status}`;
				return;
			}
			const data = await resp.json();
			if (!data.rawMessages || data.rawMessages.length === 0) {
				resampleError = "No raw API messages available for this request";
				return;
			}
			editorMessages = data.rawMessages;
			editorResponseContent = data.responseContent ?? null;
			showEditor = true;
			// Scroll editor into view
			requestAnimationFrame(() => editorEl?.scrollIntoView({ behavior: "smooth", block: "nearest" }));
		} catch (e) {
			resampleError = e instanceof Error ? e.message : String(e);
		} finally {
			isLoadingEditor = false;
		}
	}

	async function handleVariantSubmit(
		edits: { path: string; original: string; replacement: string }[],
		label: string,
		count: number,
	) {
		if (requestIndex === undefined) return;
		isResampling = true;
		resampleError = null;
		// Scroll progress indicator into view
		requestAnimationFrame(() => editorEl?.scrollIntoView({ behavior: "smooth", block: "nearest" }));
		try {
			const resp = await fetch("/api/resample", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					runName,
					sessionIndex,
					requestIndex,
					count,
					variant: { label, edits },
				}),
			});
			if (!resp.ok) {
				const text = await resp.text();
				throw new Error(`${resp.status}: ${text}`);
			}
			// Reload results, then close editor
			await loadExisting();
			showEditor = false;
			// Scroll to results after render
			requestAnimationFrame(() => resultsEl?.scrollIntoView({ behavior: "smooth", block: "nearest" }));
		} catch (e: unknown) {
			resampleError = e instanceof Error ? e.message : String(e);
		} finally {
			isResampling = false;
		}
	}

	let totalSamples = $derived(
		(resampleResults?.length ?? 0) +
			(resampleVariants
				? resampleVariants.reduce(
						(sum: number, v: any) => sum + (v.samples?.length ?? 0),
						0,
					)
				: 0),
	);
</script>

<div class="max-w-4xl" id="step-{stepIds[0]}">
	<!-- Hidden anchors for all step IDs in this group so deep links work -->
	{#each stepIds.slice(1) as sid}<span id="step-{sid}"></span>{/each}
	<div class="rounded-lg border border-border bg-card px-4 py-3 space-y-3">
		{#each items as item}
			{#if item.kind === "thinking"}
				<ThinkingBlock content={item.content} />
			{:else if item.kind === "text"}
				{@const html = renderMarkdown(item.content)}
				<div
					class="text-sm prose prose-sm dark:prose-invert max-w-none prose-p:my-1.5 prose-headings:my-2 prose-ul:my-1.5 prose-ol:my-1.5 prose-li:my-0.5 prose-pre:my-2 prose-pre:bg-muted prose-pre:text-xs prose-code:text-xs prose-code:before:content-none prose-code:after:content-none"
					style="color: var(--foreground);"
				>
					{@html html}
				</div>
			{:else if item.kind === "tool"}
				<ToolCallBlock call={item.call} result={item.result} {runName} {sessionIndex} />
			{/if}
		{/each}
	</div>

	<!-- Footer: step range + resample/edit buttons -->
	<div class="flex items-center gap-3 mt-1.5 ml-1">
		<a href="#step-{stepIds[0]}" class="text-xs text-muted-foreground/70 hover:text-muted-foreground transition-colors">{stepRange}</a>

		{#if canResample}
			<span class="text-muted-foreground/50">|</span>

			<button
				onclick={() => (showResampleForm = !showResampleForm)}
				class="text-xs text-muted-foreground hover:text-foreground transition-colors"
			>
				{#if totalSamples > 0}
					{totalSamples} resamples
				{:else}
					Resample
				{/if}
			</button>

			<button
				onclick={openEditor}
				disabled={isLoadingEditor}
				class="text-xs text-violet-600 dark:text-violet-400 hover:text-violet-800 dark:hover:text-violet-300 transition-colors"
			>
				{isLoadingEditor ? "Loading..." : "Edit & Resample"}
			</button>

			{#if requestIndex !== undefined}
				<span class="text-[11px] text-muted-foreground/60 font-mono"
					>req#{requestIndex}</span
				>
			{/if}
		{/if}
	</div>

	{#if resampleError && !showResampleForm && !showEditor}
		<p class="text-xs text-destructive mt-1 ml-1">{resampleError}</p>
	{/if}

	<!-- Resample form -->
	{#if showResampleForm}
		<div class="mt-2 ml-1 p-3 rounded-md border border-border bg-muted/50 max-w-sm">
			<div class="flex items-center gap-2">
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
					disabled={isResampling}
					class="px-3 py-1 text-xs rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
				>
					{isResampling ? "Resampling..." : `+ ${resampleCount} more`}
				</button>
			</div>
			{#if resampleError}
				<p class="text-xs text-destructive mt-2">{resampleError}</p>
			{/if}
		</div>
	{/if}

	<!-- Editor panel -->
	{#if showEditor && editorMessages}
		<div bind:this={editorEl} class="mt-2 ml-1 p-3 rounded-lg border border-violet-400/40 dark:border-violet-500/30 bg-violet-50 dark:bg-violet-950/10">
			<div class="flex items-center justify-between mb-2">
				<span class="text-[11px] font-medium text-violet-700 dark:text-violet-300"
					>Edit messages & resample</span
				>
				<button
					onclick={() => (showEditor = false)}
					disabled={isResampling}
					class="text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-30"
					>&times; Close</button
				>
			</div>
			{#if isResampling}
				<div class="py-4 text-center text-xs text-violet-600 dark:text-violet-300/80">
					Running variant... this may take a moment
				</div>
			{:else}
				<MessageEditor
					messages={editorMessages as any}
					responseContent={editorResponseContent as any}
					lastN={8}
					onsubmit={handleVariantSubmit}
				/>
			{/if}
			{#if resampleError}
				<p class="text-xs text-destructive mt-2">{resampleError}</p>
			{/if}
		</div>
	{/if}

	<!-- Resample results (inline) -->
	{#if hasAnyResults}
		<div bind:this={resultsEl} class="mt-2">
			<ResamplePanel
				samples={(resampleResults ?? []) as any}
				variants={resampleVariants as any}
				{runName}
				{sessionIndex}
				{requestIndex}
			/>
		</div>
	{/if}
</div>
