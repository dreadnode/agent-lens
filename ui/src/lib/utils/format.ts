export function formatCost(cost: number | null | undefined): string {
	if (cost == null) return "—";
	if (cost < 0.01) return `$${cost.toFixed(4)}`;
	return `$${cost.toFixed(2)}`;
}

export function formatTokens(n: number | null | undefined): string {
	if (n == null) return "—";
	return n.toLocaleString();
}

export function formatDuration(startedAt: string, finishedAt: string): string {
	const ms = new Date(finishedAt).getTime() - new Date(startedAt).getTime();
	if (ms < 1000) return `${ms}ms`;
	const secs = Math.floor(ms / 1000);
	if (secs < 60) return `${secs}s`;
	const mins = Math.floor(secs / 60);
	const remainSecs = secs % 60;
	if (mins < 60) return `${mins}m ${remainSecs}s`;
	const hours = Math.floor(mins / 60);
	const remainMins = mins % 60;
	return `${hours}h ${remainMins}m`;
}

export function formatDate(iso: string): string {
	const d = new Date(iso);
	return d.toLocaleDateString("en-US", {
		month: "short",
		day: "numeric",
		hour: "2-digit",
		minute: "2-digit",
	});
}

export function truncate(s: string, maxLen: number): string {
	if (s.length <= maxLen) return s;
	return s.slice(0, maxLen) + "…";
}
