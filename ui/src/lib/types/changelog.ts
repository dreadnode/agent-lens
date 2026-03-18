export interface ChangelogEntry {
	timestamp: string;
	session_index: number;
	step_id: number;
	file_path: string;
	diff: string;
	content_before: string;
	content_after: string;
	diff_stats: {
		added: number;
		removed: number;
	};
}
