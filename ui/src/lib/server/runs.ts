import { join } from "node:path";
import { readdir } from "node:fs/promises";
import type { RunMeta } from "$lib/types/run";
import { runsDir, readJsonFile, listDirectories, fileExists } from "./fs";

/** Count resample samples and variants across all sessions in a run. */
async function countResamples(runDir: string): Promise<{ samples: number; variants: number }> {
	let samples = 0;
	let variants = 0;

	try {
		const entries = await readdir(runDir, { withFileTypes: true });
		const sessionDirs = entries
			.filter((e) => e.isDirectory() && e.name.startsWith("session_"))
			.map((e) => e.name);

		for (const sd of sessionDirs) {
			const resamplesDir = join(runDir, sd, "resamples");
			try {
				const resampleEntries = await readdir(resamplesDir, { withFileTypes: true });
				for (const re of resampleEntries) {
					if (!re.isDirectory()) continue;
					if (re.name.match(/^request_\d+_v\d+$/)) {
						// Variant directory
						variants++;
						const vFiles = await readdir(join(resamplesDir, re.name));
						samples += vFiles.filter((f) => f.startsWith("sample_") && f.endsWith(".json") && !f.includes("error")).length;
					} else if (re.name.match(/^request_\d+$/)) {
						// Vanilla resample directory
						const sFiles = await readdir(join(resamplesDir, re.name));
						samples += sFiles.filter((f) => f.startsWith("sample_") && f.endsWith(".json") && !f.includes("error")).length;
					}
				}
			} catch {
				// No resamples dir
			}
		}
	} catch {
		// Can't read run dir
	}

	return { samples, variants };
}

export async function listRuns(): Promise<RunMeta[]> {
	const base = runsDir();
	const dirs = await listDirectories(base);
	const runs: RunMeta[] = [];

	for (const dir of dirs) {
		const metaPath = join(base, dir, "run_meta.json");
		if (await fileExists(metaPath)) {
			try {
				const meta = await readJsonFile<RunMeta>(metaPath);
				const { samples, variants } = await countResamples(join(base, dir));
				meta.resample_count = samples;
				meta.variant_count = variants;
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
