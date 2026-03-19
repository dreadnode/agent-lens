import type { PageServerLoad } from "./$types";
import type { ApiCapture } from "$lib/types/api-capture";
import { readJsonlFile, sessionDir, fileExists } from "$lib/server/fs";
import { readFile, readdir, stat } from "node:fs/promises";
import { join } from "node:path";

interface VariantEdit {
	path: string;
	original: string;
	replacement: string;
}

interface VariantInfo {
	id: string;
	label: string;
	edits: VariantEdit[];
	sampleCount: number;
}

interface ResampleGroup {
	requestIndex: number;
	sampleCount: number;
	variants: VariantInfo[];
}

export const load: PageServerLoad = async ({ params }) => {
	const dir = sessionDir(params.runName, params.sessionIndex);

	// Load API captures for context
	let mainRequestIndices: number[] = [];
	const capturesPath = join(dir, "api_captures.jsonl");
	if (await fileExists(capturesPath)) {
		try {
			const captures = await readJsonlFile<ApiCapture>(capturesPath);
			mainRequestIndices = captures
				.filter((c) => !c.agent_context || c.agent_context === "main")
				.map((c) => c.request_index);
		} catch {
			// ignore
		}
	}

	// Scan resample groups + variants
	const resampleGroups: ResampleGroup[] = [];
	const resamplesDir = join(dir, "resamples");
	if (await fileExists(resamplesDir)) {
		try {
			const entries = (await readdir(resamplesDir)).sort();

			// Group by base request index
			const requestIndices = new Set<number>();
			for (const entry of entries) {
				const match = entry.match(/^request_(\d+)(_v\d+)?$/);
				if (match) requestIndices.add(parseInt(match[1]));
			}

			for (const reqIdx of [...requestIndices].sort((a, b) => a - b)) {
				const pad = String(reqIdx).padStart(3, "0");

				// Count vanilla samples
				let sampleCount = 0;
				const vanillaDir = join(resamplesDir, `request_${pad}`);
				try {
					const files = await readdir(vanillaDir);
					sampleCount = files.filter(
						(f) => f.startsWith("sample_") && f.endsWith(".json") && !f.includes("error"),
					).length;
				} catch {
					// no vanilla dir
				}

				// Scan variant directories
				const variants: VariantInfo[] = [];
				const variantDirs = entries
					.filter((e) => e.startsWith(`request_${pad}_v`))
					.sort();

				for (const vDir of variantDirs) {
					const vPath = join(resamplesDir, vDir);
					const vStat = await stat(vPath);
					if (!vStat.isDirectory()) continue;

					const vid = vDir.match(/_v(\d+)$/)?.[0]?.slice(1) || vDir;
					let label = vid;
					let edits: VariantEdit[] = [];

					try {
						const metaContent = await readFile(join(vPath, "variant.json"), "utf-8");
						const meta = JSON.parse(metaContent);
						label = meta.label || vid;
						edits = meta.edits || [];
					} catch {
						// no variant.json
					}

					let vSampleCount = 0;
					try {
						const files = await readdir(vPath);
						vSampleCount = files.filter(
							(f) => f.startsWith("sample_") && f.endsWith(".json") && !f.includes("error"),
						).length;
					} catch {
						// empty
					}

					variants.push({ id: vid, label, edits, sampleCount: vSampleCount });
				}

				if (sampleCount > 0 || variants.length > 0) {
					resampleGroups.push({ requestIndex: reqIdx, sampleCount, variants });
				}
			}
		} catch {
			// ignore
		}
	}

	// Check if raw dumps exist
	let hasRawDumps = false;
	if (await fileExists(join(dir, "raw_dumps"))) {
		hasRawDumps = true;
	}

	return {
		sessionIndex: params.sessionIndex,
		resampleGroups,
		mainRequestIndices,
		totalMainRequests: mainRequestIndices.length,
		hasRawDumps,
	};
};
