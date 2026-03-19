<script lang="ts">
	import { formatTokens } from "$lib/utils/format";

	let { data } = $props();
	let expandedRow = $state<number | null>(null);
	let expandedTools = $state<Set<string>>(new Set());

	function toggleTool(key: string) {
		const next = new Set(expandedTools);
		if (next.has(key)) next.delete(key);
		else next.add(key);
		expandedTools = next;
	}
</script>

<h2 class="text-sm font-medium mb-6">Session {data.sessionIndex} API Captures</h2>

{#if data.captures.length === 0}
	<p class="text-sm text-muted-foreground py-8 text-center">
		No API captures available. Enable <code class="text-xs bg-muted px-1 py-0.5 rounded">capture_api_requests: true</code> in config.
	</p>
{:else}
	<div class="rounded-lg border border-border overflow-hidden">
		<table class="w-full text-sm">
			<thead>
				<tr class="bg-muted/50 border-b border-border text-xs text-muted-foreground">
					<th class="text-left px-4 py-2.5 font-medium">#</th>
					<th class="text-left px-4 py-2.5 font-medium">Context</th>
					<th class="text-left px-4 py-2.5 font-medium">Model</th>
					<th class="text-right px-4 py-2.5 font-medium">Messages</th>
					<th class="text-right px-4 py-2.5 font-medium">Input</th>
					<th class="text-right px-4 py-2.5 font-medium">Output</th>
					<th class="text-right px-4 py-2.5 font-medium">Cache</th>
					<th class="text-center px-4 py-2.5 font-medium">Compaction</th>
				</tr>
			</thead>
			<tbody>
				{#each data.captures as cap}
					<tr
						class="border-b border-border last:border-b-0 hover:bg-muted/30 cursor-pointer transition-colors {cap.agent_context === 'subagent' ? 'bg-blue-500/5' : ''} {cap.agent_context === 'sdk_internal' ? 'bg-muted/20' : ''}"
						onclick={() => expandedRow = expandedRow === cap.request_index ? null : cap.request_index}
					>
						<td class="px-4 py-2.5 tabular-nums text-muted-foreground">{cap.request_index}</td>
						<td class="px-4 py-2.5">
							{#if cap.agent_context === "subagent"}
								<span class="px-1.5 py-0.5 rounded text-[11px] bg-blue-500/10 text-blue-700 dark:text-blue-400 font-medium">subagent</span>
							{:else if cap.agent_context === "sdk_internal"}
								<span class="px-1.5 py-0.5 rounded text-[11px] bg-muted text-muted-foreground font-medium">internal</span>
							{:else if cap.agent_context === "main"}
								<span class="px-1.5 py-0.5 rounded text-[11px] bg-green-500/10 text-green-700 dark:text-green-400 font-medium">main</span>
							{/if}
						</td>
						<td class="px-4 py-2.5 font-mono text-xs text-muted-foreground">{cap.model}</td>
						<td class="px-4 py-2.5 text-right tabular-nums">{cap.message_count}</td>
						<td class="px-4 py-2.5 text-right tabular-nums font-mono text-xs">{formatTokens(cap.usage?.input_tokens)}</td>
						<td class="px-4 py-2.5 text-right tabular-nums font-mono text-xs">{formatTokens(cap.usage?.output_tokens)}</td>
						<td class="px-4 py-2.5 text-right tabular-nums font-mono text-xs">{formatTokens(cap.usage?.cache_read_input_tokens)}</td>
						<td class="px-4 py-2.5 text-center">
							{#if cap.is_compaction}
								<span class="px-1.5 py-0.5 rounded text-[11px] bg-destructive/10 text-destructive font-medium">compacted</span>
							{/if}
						</td>
					</tr>
					{#if expandedRow === cap.request_index}
						<tr>
							<td colspan="8" class="px-4 py-3 bg-muted/20 border-b border-border">
								<div class="space-y-3 text-xs">
									{#if cap.system_prompt}
										<div>
											<div class="text-[11px] font-medium text-muted-foreground uppercase tracking-wide mb-1.5">System Prompt</div>
											<pre class="font-mono bg-muted/50 rounded-md p-3 whitespace-pre-wrap max-h-60 overflow-auto border border-border/50">{JSON.stringify(cap.system_prompt, null, 2)}</pre>
										</div>
									{:else}
										<div class="text-muted-foreground">System prompt: hash {cap.system_prompt_hash}</div>
									{/if}
									{#if cap.tools}
										<div>
											<div class="text-[11px] font-medium text-muted-foreground uppercase tracking-wide mb-1.5">Tools ({cap.tools.length})</div>
											<div class="space-y-1">
												{#each cap.tools as tool}
													{@const toolKey = `${cap.request_index}-${tool.name}`}
													<div class="rounded border border-border/50 overflow-hidden">
														<button
															class="w-full flex items-center gap-2 px-2 py-1 text-left hover:bg-muted/50 transition-colors"
															onclick={() => toggleTool(toolKey)}
														>
															<span class="text-[10px] text-muted-foreground/60">{expandedTools.has(toolKey) ? '▼' : '▶'}</span>
															<span class="text-[11px] font-mono font-medium">{tool.name}</span>
														</button>
														{#if expandedTools.has(toolKey)}
															<div class="px-2 py-2 border-t border-border/50 space-y-2 bg-muted/20">
																{#if tool.description}
																	<div>
																		<div class="text-[10px] font-medium text-muted-foreground uppercase tracking-wide mb-1">Description</div>
																		<pre class="font-mono text-[11px] bg-muted/50 rounded p-2 whitespace-pre-wrap max-h-40 overflow-auto border border-border/30 leading-relaxed">{tool.description}</pre>
																	</div>
																{/if}
																{#if tool.input_schema}
																	<div>
																		<div class="text-[10px] font-medium text-muted-foreground uppercase tracking-wide mb-1">Input Schema</div>
																		<pre class="font-mono text-[11px] bg-muted/50 rounded p-2 whitespace-pre-wrap max-h-40 overflow-auto border border-border/30 leading-relaxed">{JSON.stringify(tool.input_schema, null, 2)}</pre>
																	</div>
																{/if}
															</div>
														{/if}
													</div>
												{/each}
											</div>
										</div>
									{:else}
										<div class="text-muted-foreground">Tools: hash {cap.tools_hash}</div>
									{/if}
									{#if cap.sampling_params && Object.keys(cap.sampling_params).length > 0}
										<div>
											<div class="text-[11px] font-medium text-muted-foreground uppercase tracking-wide mb-1.5">Sampling</div>
											<pre class="font-mono bg-muted/50 rounded-md p-2 border border-border/50">{JSON.stringify(cap.sampling_params, null, 2)}</pre>
										</div>
									{/if}
								</div>
							</td>
						</tr>
					{/if}
				{/each}
			</tbody>
		</table>
	</div>
{/if}
