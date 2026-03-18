export interface Agent {
	name: string;
	version: string;
	model_name?: string;
	tool_definitions?: Record<string, unknown>[];
	extra?: Record<string, unknown>;
}

export interface ToolCall {
	tool_call_id: string;
	function_name: string;
	arguments: Record<string, unknown>;
}

export interface ContentPart {
	type: "text" | "image";
	text?: string;
	source?: {
		media_type: string;
		path: string;
	};
}

export interface SubagentTrajectoryRef {
	session_id: string;
	trajectory_path?: string;
	extra?: Record<string, unknown>;
}

export interface ObservationResult {
	source_call_id?: string;
	content?: string | ContentPart[];
	subagent_trajectory_ref?: SubagentTrajectoryRef[];
}

export interface Observation {
	results: ObservationResult[];
}

export interface Metrics {
	prompt_tokens?: number;
	completion_tokens?: number;
	cached_tokens?: number;
	cost_usd?: number;
	extra?: Record<string, unknown>;
}

export interface Step {
	step_id: number;
	timestamp?: string;
	source: "system" | "user" | "agent";
	model_name?: string;
	reasoning_effort?: string | number;
	message: string | ContentPart[];
	reasoning_content?: string;
	tool_calls?: ToolCall[];
	observation?: Observation;
	metrics?: Metrics;
	is_copied_context?: boolean;
	extra?: Record<string, unknown>;
}

export interface FinalMetrics {
	total_prompt_tokens?: number;
	total_completion_tokens?: number;
	total_cached_tokens?: number;
	total_cost_usd?: number;
	total_steps?: number;
	extra?: Record<string, unknown>;
}

export interface Trajectory {
	schema_version: string;
	session_id: string;
	agent: Agent;
	steps: Step[];
	notes?: string;
	final_metrics?: FinalMetrics;
	continued_trajectory_ref?: string;
	extra?: Record<string, unknown>;
}
