<script lang="ts">
	import { renderMarkdown } from "$lib/utils/markdown";

	let { data } = $props();
	let html = $derived(renderMarkdown(data.analysisMarkdown));
</script>

<style>
	.analysis :global(h1) {
		font-size: 1.125rem;
		font-weight: 600;
		border-bottom: 1px solid var(--border);
		padding-bottom: 0.5rem;
		margin-bottom: 1rem;
		margin-top: 0;
		color: var(--foreground);
	}
	.analysis :global(h2) {
		font-size: 1rem;
		font-weight: 600;
		margin-top: 2rem;
		margin-bottom: 0.75rem;
		color: var(--foreground);
	}
	.analysis :global(h3) {
		font-size: 0.875rem;
		font-weight: 600;
		margin-top: 1.5rem;
		margin-bottom: 0.5rem;
		color: var(--foreground);
	}
	.analysis :global(p) {
		font-size: 0.875rem;
		line-height: 1.625;
		margin: 0.5rem 0;
		color: var(--foreground);
	}
	.analysis :global(ul),
	.analysis :global(ol) {
		font-size: 0.875rem;
		line-height: 1.625;
		margin: 0.5rem 0;
		padding-left: 1.5rem;
		color: var(--foreground);
	}
	.analysis :global(li) {
		margin: 0.25rem 0;
	}
	.analysis :global(pre) {
		font-size: 0.75rem;
		background: var(--muted);
		border-radius: 0.5rem;
		padding: 0.75rem 1rem;
		margin: 0.75rem 0;
		overflow-x: auto;
	}
	.analysis :global(code) {
		font-size: 0.75rem;
	}
	.analysis :global(code):not(:global(pre) :global(code)) {
		background: var(--muted);
		padding: 0.125rem 0.375rem;
		border-radius: 0.25rem;
	}
	.analysis :global(blockquote) {
		border-left: 3px solid var(--border);
		padding-left: 1rem;
		margin: 0.75rem 0;
		color: var(--muted-foreground);
		font-size: 0.875rem;
	}
	.analysis :global(hr) {
		border: none;
		border-top: 1px solid var(--border);
		margin: 1.5rem 0;
	}
	.analysis :global(strong) {
		font-weight: 600;
		color: var(--foreground);
	}
	.analysis :global(em) {
		color: var(--muted-foreground);
	}
	.analysis :global(a) {
		color: var(--foreground);
		text-decoration: underline;
		text-underline-offset: 2px;
	}
	.analysis :global(a):hover {
		opacity: 0.7;
	}
	.analysis :global(table) {
		width: 100%;
		font-size: 0.875rem;
		border-collapse: collapse;
		margin: 0.75rem 0;
	}
	.analysis :global(th),
	.analysis :global(td) {
		border: 1px solid var(--border);
		padding: 0.375rem 0.75rem;
		text-align: left;
	}
	.analysis :global(th) {
		background: var(--muted);
		font-weight: 600;
	}
</style>

<div class="analysis" style="max-width: none; color: var(--foreground);">
	{@html html}
</div>
