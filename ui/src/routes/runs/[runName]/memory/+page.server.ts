import type { PageServerLoad } from "./$types";
import { readTextFile, readJsonlFile, runPath, fileExists } from "$lib/server/fs";
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

	// Get memory file name from config
	let memoryFile = "MEMORY.md";
	try {
		const configText = await readTextFile(join(base, "config.yaml"));
		const config = yaml.load(configText) as any;
		if (config?.memory_file) memoryFile = config.memory_file;
	} catch {
		// use default
	}

	// Get memory seed from config (initial content)
	let init = "";
	let final_ = "";

	const changelogPath = join(base, "state_changelog.jsonl");
	if (await fileExists(changelogPath)) {
		const events = await readJsonlFile<WriteEvent>(changelogPath);
		const memoryEvents = events.filter((e) => e.file_path === memoryFile);

		if (memoryEvents.length > 0) {
			init = memoryEvents[0].content_before;
			final_ = memoryEvents[memoryEvents.length - 1].content_after;
		}
	}

	return { init, final: final_, memoryFile };
};
