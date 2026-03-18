import { join } from "node:path";
import type { RunMeta } from "$lib/types/run";
import { runsDir, readJsonFile, listDirectories, fileExists } from "./fs";

export async function listRuns(): Promise<RunMeta[]> {
	const base = runsDir();
	const dirs = await listDirectories(base);
	const runs: RunMeta[] = [];

	for (const dir of dirs) {
		const metaPath = join(base, dir, "run_meta.json");
		if (await fileExists(metaPath)) {
			try {
				const meta = await readJsonFile<RunMeta>(metaPath);
				runs.push(meta);
			} catch {
				// Skip malformed run directories
			}
		}
	}

	return runs.sort((a, b) => b.started_at.localeCompare(a.started_at));
}

export async function loadRunMeta(runName: string): Promise<RunMeta> {
	return readJsonFile<RunMeta>(join(runsDir(), runName, "run_meta.json"));
}
