import type { PageServerLoad } from "./$types";
import { readTextFile, readJsonlFile, runPath, sessionDir, fileExists } from "$lib/server/fs";
import { join } from "node:path";
import yaml from "js-yaml";

interface WriteEvent {
	session_index: number;
	step_id: number;
	file_path: string;
	diff: string;
	content_before: string;
	content_after: string;
}

export const load: PageServerLoad = async ({ params }) => {
	const base = runPath(params.runName);
	const sessionIdx = parseInt(params.sessionIndex);

	// Get memory file name from config
	let memoryFile = "MEMORY.md";
	try {
		const configText = await readTextFile(join(base, "config.yaml"));
		const config = yaml.load(configText) as any;
		if (config?.memory_file) memoryFile = config.memory_file;
	} catch {
		// use default
	}

	let before = "";
	let after = "";
	let patch = "";

	const changelogPath = join(base, "state_changelog.jsonl");
	if (await fileExists(changelogPath)) {
		const events = await readJsonlFile<WriteEvent>(changelogPath);
		const memoryEvents = events.filter((e) => e.file_path === memoryFile);

		// Find the first memory event in this session for "before"
		// and the last memory event in this session for "after"
		const sessionEvents = memoryEvents.filter((e) => e.session_index === sessionIdx);

		if (sessionEvents.length > 0) {
			before = sessionEvents[0].content_before;
			after = sessionEvents[sessionEvents.length - 1].content_after;
			// Combine diffs from all memory writes in this session
			patch = sessionEvents.map((e) => e.diff).join("\n");
		} else {
			// No changes in this session — show the state from before this session
			const priorEvents = memoryEvents.filter((e) => e.session_index < sessionIdx);
			if (priorEvents.length > 0) {
				before = priorEvents[priorEvents.length - 1].content_after;
				after = before;
			}
		}
	}

	return { before, after, patch, sessionIndex: params.sessionIndex, memoryFile };
};
