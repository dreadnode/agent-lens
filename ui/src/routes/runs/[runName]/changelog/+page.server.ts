import type { PageServerLoad } from "./$types";
import type { ChangelogEntry } from "$lib/types/changelog";
import { readJsonlFile, runPath, fileExists } from "$lib/server/fs";
import { join } from "node:path";

export const load: PageServerLoad = async ({ params }) => {
	const changelogPath = join(runPath(params.runName), "state_changelog.jsonl");

	let entries: ChangelogEntry[] = [];
	if (await fileExists(changelogPath)) {
		const raw = await readJsonlFile<ChangelogEntry>(changelogPath);
		// Strip content_before/content_after to reduce payload, keep diffs
		entries = raw.map((e) => ({
			...e,
			content_before: "",
			content_after: "",
		}));
	}

	return { entries };
};
