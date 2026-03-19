import type { LayoutServerLoad } from "./$types";
import { sessionDir, fileExists } from "$lib/server/fs";
import { join } from "node:path";
import { readdir } from "node:fs/promises";

export const load: LayoutServerLoad = async ({ params }) => {
	const dir = sessionDir(params.runName, params.sessionIndex);

	// List subagent files
	let subagentFiles: string[] = [];
	try {
		const files = await readdir(dir);
		subagentFiles = files.filter((f) => f.startsWith("subagent_") && f.endsWith(".json"));
	} catch {
		// ignore
	}

	// Scan for existing resample results (vanilla + variant samples)
	const resamples: Record<number, number> = {};
	const resamplesDir = join(dir, "resamples");
	if (await fileExists(resamplesDir)) {
		try {
			const reqDirs = await readdir(resamplesDir);
			for (const reqDir of reqDirs) {
				// Match both "request_005" (vanilla) and "request_005_v01" (variant)
				const match = reqDir.match(/^request_(\d+)(?:_v\d+)?$/);
				if (match) {
					const reqIdx = parseInt(match[1]);
					const sampleFiles = await readdir(join(resamplesDir, reqDir));
					const count = sampleFiles.filter(
						(f) => f.startsWith("sample_") && f.endsWith(".json") && !f.includes("error"),
					).length;
					if (count > 0) resamples[reqIdx] = (resamples[reqIdx] ?? 0) + count;
				}
			}
		} catch {
			// ignore
		}
	}

	return {
		sessionIndex: params.sessionIndex,
		subagentFiles,
		resamples,
	};
};
