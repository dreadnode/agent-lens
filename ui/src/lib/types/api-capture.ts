export interface ApiCapture {
	timestamp: string;
	request_index: number;
	agent_context?: "main" | "subagent" | "sdk_internal";
	model: string;
	sampling_params: Record<string, unknown>;
	message_count: number;
	system_prompt?: unknown;
	system_prompt_hash: string;
	tools?: Array<{
		name: string;
		description: string;
		input_schema: Record<string, unknown>;
	}>;
	tools_hash: string;
	is_compaction: boolean;
	compacted_messages?: unknown[];
	context_management?: Record<string, unknown>;
	usage?: {
		input_tokens: number | null;
		output_tokens: number | null;
		cache_creation_input_tokens: number | null;
		cache_read_input_tokens: number | null;
		cache_creation: unknown;
		service_tier: string | null;
	};
}
