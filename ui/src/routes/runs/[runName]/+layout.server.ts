import { error } from "@sveltejs/kit";
import type { LayoutServerLoad } from "./$types";
import { loadRunMeta } from "$lib/server/runs";
import { readTextFile, runPath, fileExists } from "$lib/server/fs";
import { join } from "node:path";

export const load: LayoutServerLoad = async ({ params }) => {
	let meta;
	try {
		meta = await loadRunMeta(params.runName);
	} catch {
		error(404, `Run not found: ${params.runName}`);
	}
	let configYaml = "";
	try {
		configYaml = await readTextFile(join(runPath(params.runName), "config.yaml"));
	} catch {
		// config may not exist
	}

	const analysisPath = join(runPath(params.runName), "analysis.md");
	const hasAnalysis = await fileExists(analysisPath);

	return { meta, configYaml, runName: params.runName, hasAnalysis };
};
