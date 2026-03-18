<script lang="ts">
	let { content }: { content: string } = $props();
	let lines = $derived(content.split("\n"));

	// Returns [bgStyle, textClass, borderStyle]
	function lineStyles(line: string): { bg: string; text: string; border: string } {
		if (line.startsWith("+") && !line.startsWith("+++")) {
			return {
				bg: "background: rgba(22, 163, 74, 0.12);",
				text: "diff-add",
				border: "border-left: 2px solid rgba(22, 163, 74, 0.5);",
			};
		}
		if (line.startsWith("-") && !line.startsWith("---")) {
			return {
				bg: "background: rgba(220, 38, 38, 0.12);",
				text: "diff-del",
				border: "border-left: 2px solid rgba(220, 38, 38, 0.5);",
			};
		}
		if (line.startsWith("@@")) {
			return {
				bg: "background: rgba(37, 99, 235, 0.08);",
				text: "diff-hunk",
				border: "border-left: 2px solid rgba(37, 99, 235, 0.35);",
			};
		}
		if (line.startsWith("diff ") || line.startsWith("index ") || line.startsWith("---") || line.startsWith("+++")) {
			return { bg: "", text: "diff-meta", border: "" };
		}
		return { bg: "", text: "diff-ctx", border: "" };
	}
</script>

<style>
	.diff-add { color: #15803d; }
	.diff-del { color: #b91c1c; }
	.diff-hunk { color: #1d4ed8; }
	.diff-meta { color: var(--muted-foreground); opacity: 0.8; }
	.diff-ctx { color: var(--foreground); opacity: 0.75; }

	:global(.dark) .diff-add { color: #86efac; }
	:global(.dark) .diff-del { color: #fca5a5; }
	:global(.dark) .diff-hunk { color: #93c5fd; }
</style>

<div class="rounded-lg border border-border overflow-hidden font-mono text-xs">
	{#each lines as line}
		{@const s = lineStyles(line)}
		<div class="{s.text}" style="padding: 1px 0.75rem; line-height: 1.375rem; {s.bg} {s.border}">
			<pre style="white-space: pre-wrap; margin: 0;">{line}</pre>
		</div>
	{/each}
</div>
