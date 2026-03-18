export interface SessionMeta {
	session_index: number;
	session_id: string | null;
	resumed_from: string | null;
	fork_from?: number | null;
	replicate?: number;
	replicate_count?: number;
	step_count: number;
	tool_call_count: number;
	num_turns: number;
	total_cost_usd: number | null;
	compaction_count: number;
	subagent_count: number;
	error: string | null;
	started_at: string;
	finished_at: string;
}

/** Derive URL-safe session key from session meta (e.g. "2" or "2_r01"). */
export function sessionKey(s: SessionMeta): string {
	if (s.replicate != null) {
		return `${s.session_index}_r${String(s.replicate).padStart(2, "0")}`;
	}
	return String(s.session_index);
}

export interface RunMeta {
	run_name: string;
	hypothesis?: string;
	model: string;
	provider: string;
	sdk_version?: string;
	harness_version?: string;
	session_mode: "isolated" | "chained" | "forked";
	work_dir: string;
	repo_name: string | null;
	tags: string[];
	session_count: number;
	sessions: SessionMeta[];
	started_at: string;
	finished_at: string;
	total_steps: number;
	total_tool_calls: number;
	total_cost_usd: number | null;
	total_file_writes: number;
	total_compaction_events: number;
	total_subagent_invocations: number;
	errors: string[];
}
