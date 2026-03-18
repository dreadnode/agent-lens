<script lang="ts">
	import "../app.css";

	let { children } = $props();
	let dark = $state(false);

	function toggleDark() {
		dark = !dark;
		document.documentElement.classList.toggle("dark", dark);
	}
</script>

<svelte:head>
	<title>AgentLens</title>
</svelte:head>

<div class="min-h-screen bg-background text-foreground">
	<header class="sticky top-0 z-50 border-b border-border bg-background/95 backdrop-blur supports-backdrop-filter:bg-background/80">
		<div class="max-w-7xl mx-auto flex items-center" style="padding: 0 1.5rem; height: 3.5rem; gap: 1rem;">
			<a href="/" class="text-sm font-semibold tracking-tight hover:text-foreground/80 transition-colors">AgentLens</a>
			<div style="flex: 1;"></div>
			<button
				onclick={toggleDark}
				class="text-xs rounded-md bg-secondary text-secondary-foreground hover:bg-accent transition-colors"
				style="padding: 0.375rem 0.75rem;"
			>
				{dark ? "Light" : "Dark"}
			</button>
		</div>
	</header>
	<main class="max-w-7xl mx-auto" style="padding: 2.5rem 1.5rem;">
		{@render children()}
	</main>
</div>
