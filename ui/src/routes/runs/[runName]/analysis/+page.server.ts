import type { PageServerLoad } from "./$types";
import { readTextFile, runPath } from "$lib/server/fs";
import { join } from "node:path";
import { error } from "@sveltejs/kit";

export const load: PageServerLoad = async ({ params }) => {
	try {
		const content = await readTextFile(join(runPath(params.runName), "analysis.md"));
		return { analysisMarkdown: content };
	} catch {
		return error(404, "No analysis found for this run");
	}
};
