<script lang="ts">
	let { data } = $props();
</script>

<h2 class="text-sm font-medium" style="margin-bottom: 1rem;">Run Configuration</h2>
<pre style="padding: 1.25rem 1.5rem; font-size: 12px; font-family: var(--font-mono); background: var(--muted); border: 1px solid var(--border); border-radius: 0.5rem; white-space: pre-wrap; overflow: auto; max-height: 80vh; line-height: 1.7;">{data.configYaml || "(no config.yaml found)"}</pre>
