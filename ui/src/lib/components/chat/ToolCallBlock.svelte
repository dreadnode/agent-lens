<script lang="ts">
	import type { ToolCall, ObservationResult } from "$lib/types/atif";
	import { truncate } from "$lib/utils/format";

	let { call, result, runName = "", sessionIndex = 0 as number | string }: {
		call: ToolCall;
		result?: ObservationResult;
		runName?: string;
		sessionIndex?: number | string;
	} = $props();
	let argsExpanded = $state(false);
	let resultExpanded = $state(false);

	const toolIcons: Record<string, string> = {
		Read: "\u{1F4C4}",
		Write: "\u{1F4DD}",
		Edit: "\u270F\uFE0F",
		MultiEdit: "\u270F\uFE0F",
		Bash: "\u{1F4BB}",
		Glob: "\u{1F50D}",
		Grep: "\u{1F50E}",
		Agent: "\u{1F916}",
		WebFetch: "\u{1F310}",
		WebSearch: "\u{1F310}",
		TodoWrite: "\u2611\uFE0F",
	};

	function getToolSummary(name: string, args: Record<string, unknown>): string {
		switch (name) {
			case "Read":
				return String(args.file_path || "");
			case "Write":
				return String(args.file_path || "");
			case "Edit":
			case "MultiEdit":
				return String(args.file_path || "");
			case "Bash":
				return args.description
					? String(args.description)
					: truncate(String(args.command || ""), 80);
			case "Glob":
				return String(args.pattern || "");
			case "Grep":
				return `${args.pattern || ""} ${args.path ? "in " + args.path : ""}`;
			case "Agent":
				return `${args.description || ""} (${args.subagent_type || "general"})`;
			default:
				return "";
		}
	}

	function getResultText(r: ObservationResult): string {
		if (!r.content) return "";
		if (typeof r.content === "string") return r.content;
		return r.content
			.filter((p) => p.type === "text" && p.text)
			.map((p) => p.text!)
			.join("\n");
	}

	let isAgentCall = $derived(call.function_name === "Agent");
	let subagentRef = $derived(result?.subagent_trajectory_ref?.[0]);
	let subagentFilename = $derived(subagentRef?.trajectory_path || "");
	let subagentName = $derived(
		subagentRef?.extra?.subagent_name as string || call.arguments.description as string || ""
	);

	let summary = $derived(getToolSummary(call.function_name, call.arguments));
	let resultText = $derived(result ? getResultText(result) : "");
	let resultLines = $derived(resultText.split("\n"));
	let resultNeedsTruncation = $derived(resultLines.length > 15);
	let resultPreview = $derived(resultLines.slice(0, 15).join("\n"));
	let icon = $derived(toolIcons[call.function_name] || "\u{1F527}");
</script>

<div class="border-l-2 {isAgentCall ? 'border-blue-500' : 'border-border'} pl-3 py-1.5">
	<!-- Header -->
	<div class="flex items-center gap-2 min-w-0">
		<span class="text-xs shrink-0">{icon}</span>
		<span class="text-xs font-semibold shrink-0">{call.function_name}</span>
		{#if summary}
			<span class="text-xs text-muted-foreground font-mono truncate">{summary}</span>
		{/if}
		<button
			onclick={() => (argsExpanded = !argsExpanded)}
			class="text-xs text-muted-foreground hover:text-foreground ml-auto shrink-0 transition-colors"
		>
			{argsExpanded ? "hide args" : "args"}
		</button>
	</div>

	<!-- Subagent trajectory link -->
	{#if isAgentCall && subagentFilename}
		<a
			href="/runs/{runName}/sessions/{sessionIndex}/subagents/{subagentFilename}"
			class="inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline mt-1.5"
		>
			View subagent trajectory &rarr;
		</a>
	{/if}

	<!-- Expandable args -->
	{#if argsExpanded}
		<pre class="text-xs font-mono bg-muted/50 rounded p-2.5 mt-2 overflow-x-auto whitespace-pre-wrap max-h-60 overflow-y-auto">{JSON.stringify(call.arguments, null, 2)}</pre>
	{/if}

	<!-- Tool result -->
	{#if resultText}
		<div class="mt-2">
			<div class="bg-muted/30 rounded p-2.5">
				{#if resultExpanded || !resultNeedsTruncation}
					<pre class="text-xs font-mono whitespace-pre-wrap overflow-x-auto max-h-80 overflow-y-auto">{resultText}</pre>
				{:else}
					<pre class="text-xs font-mono whitespace-pre-wrap overflow-x-auto">{resultPreview}</pre>
					<button
						onclick={() => (resultExpanded = true)}
						class="text-xs text-primary hover:underline mt-2 block"
					>
						Show all ({resultLines.length} lines)
					</button>
				{/if}
			</div>
		</div>
	{/if}
</div>
