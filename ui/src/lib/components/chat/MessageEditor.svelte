<script lang="ts">
	interface ContentBlock {
		type: string;
		text?: string;
		thinking?: string;
		name?: string;
		input?: Record<string, unknown>;
		content?: string | ContentBlock[];
	}

	interface Edit {
		path: string;
		original: string;
		replacement: string;
	}

	interface MessageEditorProps {
		messages: { role: string; content: string | ContentBlock[] }[];
		responseContent?: ContentBlock[] | null;
		lastN?: number;
		onsubmit: (edits: Edit[], label: string, count: number) => void;
	}

	let { messages, responseContent = null, lastN = 8, onsubmit }: MessageEditorProps = $props();

	let hasResponse = $derived(responseContent && responseContent.length > 0);

	// Find the last assistant message in the input — primary edit target
	let lastAssistantIdx = $derived.by(() => {
		for (let i = messages.length - 1; i >= 0; i--) {
			if (messages[i].role === "assistant") return i;
		}
		return messages.length - 1;
	});

	let currentMsg = $derived(messages[lastAssistantIdx]);
	let currentMsgIdx = $derived(lastAssistantIdx);

	// Messages after the last assistant message (tool_results, etc.)
	let afterMessages = $derived(messages.slice(lastAssistantIdx + 1));

	// Previous messages: up to lastN before the current assistant message
	let prevStart = $derived(Math.max(0, lastAssistantIdx - (lastN - 1)));
	let prevMessages = $derived(messages.slice(prevStart, lastAssistantIdx));

	// Track edits
	let edits = $state<Edit[]>([]);
	let label = $state("");
	let count = $state(3);

	// Expand/collapse sections
	let showPrevious = $state(false);
	let showResponse = $state(false);

	function getBlockText(block: ContentBlock): string {
		if (block.type === "text") return block.text || "";
		if (block.type === "thinking") return block.thinking || "";
		if (block.type === "tool_result") {
			if (typeof block.content === "string") return block.content;
			if (Array.isArray(block.content)) {
				return block.content
					.filter((b) => b.type === "text")
					.map((b) => b.text || "")
					.join("\n");
			}
			return "";
		}
		return "";
	}

	function handleEdit(absIdx: number, blockIdx: number, field: string, newValue: string) {
		const msg = messages[absIdx];
		if (!msg || !Array.isArray(msg.content)) return;

		const block = msg.content[blockIdx] as ContentBlock;
		const original = field === "thinking" ? (block.thinking || "") : (block.text || "");

		if (newValue === original) {
			edits = edits.filter((e) => e.path !== `messages[${absIdx}].content[${blockIdx}].${field}`);
			return;
		}

		const path = `messages[${absIdx}].content[${blockIdx}].${field}`;
		const existing = edits.findIndex((e) => e.path === path);
		const edit: Edit = { path, original, replacement: newValue };
		if (existing >= 0) {
			edits[existing] = edit;
			edits = [...edits];
		} else {
			edits = [...edits, edit];
		}
	}

	function handleToolResultEdit(absIdx: number, blockIdx: number, newValue: string) {
		const msg = messages[absIdx];
		if (!msg || !Array.isArray(msg.content)) return;

		const block = msg.content[blockIdx] as ContentBlock;
		let original = "";
		let field = "content";

		if (typeof block.content === "string") {
			original = block.content;
		} else if (Array.isArray(block.content)) {
			const textBlock = block.content.find((b) => b.type === "text");
			if (textBlock) {
				original = textBlock.text || "";
				field = "content[0].text";
			}
		}

		if (newValue === original) {
			edits = edits.filter((e) => !e.path.startsWith(`messages[${absIdx}].content[${blockIdx}]`));
			return;
		}

		const path = `messages[${absIdx}].content[${blockIdx}].${field}`;
		const existing = edits.findIndex((e) => e.path === path);
		const edit: Edit = { path, original, replacement: newValue };
		if (existing >= 0) {
			edits[existing] = edit;
			edits = [...edits];
		} else {
			edits = [...edits, edit];
		}
	}

	function handleSubmit() {
		if (edits.length === 0) return;
		onsubmit(edits, label || `${edits.length} edit${edits.length > 1 ? "s" : ""}`, count);
	}

	function isSystemReminder(block: ContentBlock): boolean {
		return block.type === "text" && (block.text?.trimStart().startsWith("<system-reminder>") ?? false);
	}

	function systemReminderLabel(text: string): string {
		const inner = text.replace(/<\/?system-reminder>/g, "").trim();
		const firstLine = inner.split("\n")[0].trim();
		if (firstLine.length > 60) return firstLine.slice(0, 60) + "...";
		return firstLine || "system-reminder";
	}

	let expandedReminders = $state<Set<string>>(new Set());

	function toggleReminder(key: string) {
		const next = new Set(expandedReminders);
		if (next.has(key)) next.delete(key);
		else next.add(key);
		expandedReminders = next;
	}

	function roleBadgeClass(role: string): string {
		switch (role) {
			case "user":
				return "bg-blue-100 dark:bg-blue-500/20 text-blue-700 dark:text-blue-300";
			case "assistant":
				return "bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300";
			default:
				return "bg-muted text-muted-foreground";
		}
	}
</script>

{#snippet messageCard(msg: { role: string; content: string | ContentBlock[] }, absIdx: number, highlight: boolean)}
	<div class="rounded-md border overflow-hidden {highlight ? 'border-violet-400/60 dark:border-violet-500/40 ring-1 ring-violet-400/20' : 'border-border'}">
		<!-- Role header -->
		<div class="px-3 py-1.5 border-b border-border bg-muted/30 flex items-center gap-2">
			<span class="text-[10px] font-medium px-1.5 py-0.5 rounded {roleBadgeClass(msg.role)}">
				{msg.role}
			</span>
			<span class="text-[10px] text-muted-foreground/70 font-mono">
				msg[{absIdx}]
			</span>
			{#if highlight}
				<span class="text-[9px] text-violet-600 dark:text-violet-400 font-medium ml-auto">current</span>
			{/if}
		</div>

		<!-- Content blocks -->
		<div class="px-3 py-2 space-y-2">
			{#if typeof msg.content === "string"}
				<pre class="text-[10px] font-mono text-muted-foreground whitespace-pre-wrap">{msg.content}</pre>
			{:else if Array.isArray(msg.content)}
				{#each msg.content as block, blockIdx}
					{#if block.type === "thinking"}
						<div>
							<div class="text-[9px] text-muted-foreground/50 uppercase tracking-wider mb-0.5">thinking <span class="normal-case text-muted-foreground/40">(read-only — signature-protected)</span></div>
							<pre class="w-full text-[10px] font-mono bg-muted/10 border border-border/30 rounded px-2 py-1.5 text-muted-foreground/40 italic whitespace-pre-wrap max-h-[120px] overflow-y-auto">{block.thinking || ""}</pre>
						</div>
					{:else if isSystemReminder(block)}
						{@const rKey = `${absIdx}-${blockIdx}`}
						{@const isOpen = expandedReminders.has(rKey)}
						<div class="rounded border border-border/60 bg-muted/10 overflow-hidden">
							<button
								onclick={() => toggleReminder(rKey)}
								class="w-full flex items-center gap-1.5 px-2 py-1 text-left hover:bg-muted/30 transition-colors"
							>
								<span class="text-[9px] text-muted-foreground/60 transition-transform {isOpen ? 'rotate-90' : ''}">&rsaquo;</span>
								<span class="text-[9px] text-muted-foreground/60 uppercase tracking-wider">system-reminder</span>
								<span class="text-[9px] text-muted-foreground/60 truncate">{systemReminderLabel(block.text || "")}</span>
							</button>
							{#if isOpen}
								<div class="px-2 pb-1.5">
									<textarea
										value={block.text || ""}
										oninput={(e) => handleEdit(absIdx, blockIdx, "text", e.currentTarget.value)}
										class="w-full text-[10px] font-mono bg-background border border-border/50 rounded px-2 py-1.5 resize-y min-h-[60px] text-muted-foreground/70"
										rows="4"
									></textarea>
								</div>
							{/if}
						</div>
					{:else if block.type === "text"}
						<div>
							<div class="text-[9px] text-muted-foreground/70 uppercase tracking-wider mb-0.5">text</div>
							<textarea
								value={block.text || ""}
								oninput={(e) => handleEdit(absIdx, blockIdx, "text", e.currentTarget.value)}
								class="w-full text-[10px] font-mono bg-background border border-border/50 rounded px-2 py-1.5 resize-y min-h-[40px]"
								rows={highlight ? 6 : 2}
							></textarea>
						</div>
					{:else if block.type === "tool_use"}
						<div class="rounded bg-muted/20 px-2 py-1.5">
							<span class="text-[9px] text-muted-foreground/70 uppercase tracking-wider">tool_use</span>
							<span class="text-[10px] font-mono text-muted-foreground ml-1">{block.name}</span>
						</div>
					{:else if block.type === "tool_result"}
						<div>
							<div class="text-[9px] text-muted-foreground/70 uppercase tracking-wider mb-0.5">tool_result</div>
							<textarea
								value={getBlockText(block)}
								oninput={(e) => handleToolResultEdit(absIdx, blockIdx, e.currentTarget.value)}
								class="w-full text-[10px] font-mono bg-background border border-border/50 rounded px-2 py-1.5 resize-y min-h-[40px]"
								rows={highlight ? 5 : 3}
							></textarea>
						</div>
					{:else}
						<div class="text-[10px] text-muted-foreground/50">
							[{block.type}]
						</div>
					{/if}
				{/each}
			{/if}
		</div>
	</div>
{/snippet}

<div class="space-y-3">
	<!-- Response reference (read-only, collapsible — shows what this request produced) -->
	{#if hasResponse && responseContent}
		{@const responseText = responseContent.filter((b: ContentBlock) => b.type === "text").map((b: ContentBlock) => b.text || "").join(" ")}
		<div class="rounded-md border border-border/50 bg-muted/20 overflow-hidden">
			<button
				onclick={() => (showResponse = !showResponse)}
				class="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-muted/40 transition-colors"
			>
				<span class="text-[9px] text-muted-foreground/60 transition-transform {showResponse ? 'rotate-90' : ''}">&rsaquo;</span>
				<span class="text-[9px] text-muted-foreground/70 uppercase tracking-wider">output</span>
				<span class="text-[10px] text-muted-foreground/60 truncate">{responseText.slice(0, 80)}{responseText.length > 80 ? "..." : ""}</span>
			</button>
			{#if showResponse}
				<div class="px-3 pb-2 space-y-1.5">
					{#each responseContent as block}
						{#if block.type === "text"}
							<pre class="text-[10px] font-mono text-muted-foreground whitespace-pre-wrap">{block.text}</pre>
						{:else if block.type === "tool_use"}
							<div class="text-[10px] text-muted-foreground">tool_use: {block.name}</div>
						{/if}
					{/each}
				</div>
			{/if}
		</div>
	{/if}

	<!-- Previous messages (expandable) -->
	{#if prevMessages.length > 0}
		<button
			onclick={() => (showPrevious = !showPrevious)}
			class="flex items-center gap-1.5 text-[10px] text-muted-foreground/70 hover:text-muted-foreground transition-colors"
		>
			<span class="transition-transform {showPrevious ? 'rotate-90' : ''}">&rsaquo;</span>
			{prevMessages.length} previous message{prevMessages.length > 1 ? "s" : ""}
			{#if prevStart > 0}
				<span class="text-muted-foreground/60">(showing from msg[{prevStart}])</span>
			{/if}
		</button>

		{#if showPrevious}
			<div class="space-y-2 pl-2 border-l-2 border-border/60">
				{#each prevMessages as msg, i}
					{@render messageCard(msg, prevStart + i, false)}
				{/each}
			</div>
		{/if}
	{/if}

	<!-- Last assistant message (primary edit target) -->
	{#if currentMsg}
		<div class="text-[10px] text-muted-foreground mb-1">
			Last input message (msg[{currentMsgIdx}] of {messages.length}) — edit to change model behavior
		</div>
		{@render messageCard(currentMsg, currentMsgIdx, true)}
	{/if}

	<!-- Messages after the assistant message (tool_results, etc.) -->
	{#if afterMessages.length > 0}
		<div class="space-y-2 opacity-60">
			{#each afterMessages as msg, i}
				{@render messageCard(msg, lastAssistantIdx + 1 + i, false)}
			{/each}
		</div>
	{/if}

	<!-- Submit bar -->
	<div class="flex items-center gap-3 p-3 rounded-lg border border-border bg-muted/30">
		<label class="text-xs text-muted-foreground">
			Label:
			<input
				type="text"
				bind:value={label}
				placeholder="describe the edit"
				class="ml-1 px-2 py-1 text-xs rounded border border-border bg-background w-48"
			/>
		</label>
		<label class="text-xs text-muted-foreground">
			Count:
			<input
				type="number"
				bind:value={count}
				min="1"
				max="20"
				class="ml-1 w-14 px-2 py-1 text-xs rounded border border-border bg-background"
			/>
		</label>
		<button
			onclick={handleSubmit}
			disabled={edits.length === 0}
			class="px-4 py-1.5 text-xs rounded bg-amber-600 text-white hover:bg-amber-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
		>
			Run variant ({edits.length} edit{edits.length > 1 ? "s" : ""})
		</button>
		{#if edits.length > 0}
			<span class="text-[10px] text-amber-600 dark:text-amber-400/80">{edits.map((e) => e.path.split(".").pop()).join(", ")}</span>
		{/if}
	</div>
</div>
