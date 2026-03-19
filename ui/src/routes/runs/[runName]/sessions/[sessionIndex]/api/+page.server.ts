import type { PageServerLoad } from "./$types";
import type { ApiCapture } from "$lib/types/api-capture";
import { readJsonlFile, sessionDir, fileExists } from "$lib/server/fs";
import { join } from "node:path";

export const load: PageServerLoad = async ({ params }) => {
	const dir = sessionDir(params.runName, params.sessionIndex);
	const capturePath = join(dir, "api_captures.jsonl");

	let captures: ApiCapture[] = [];
	if (await fileExists(capturePath)) {
		captures = await readJsonlFile<ApiCapture>(capturePath);
	}

	return { captures, sessionIndex: params.sessionIndex };
};
