import { error } from "@sveltejs/kit";
import type { PageServerLoad } from "./$types";
import { loadRunMeta } from "$lib/server/runs";
import { sessionDir, readJsonFile, fileExists } from "$lib/server/fs";
import { sessionKey } from "$lib/types/run";
import type { Trajectory } from "$lib/types/atif";
import { join } from "node:path";

interface SessionTrajectory {
	key: string;
	trajectory: Trajectory | null;
	hasRawDumps: boolean;
}

export const load: PageServerLoad = async ({ params }) => {
	let run;
	try {
		run = await loadRunMeta(params.name);
	} catch {
		throw error(404, `Run not found: ${params.name}`);
	}

	const sessionTrajectories: SessionTrajectory[] = [];
	for (const session of run.sessions) {
		const key = sessionKey(session);
		const dir = sessionDir(params.name, key);
		let trajectory: Trajectory | null = null;
		let hasRawDumps = false;

		const trajPath = join(dir, "trajectory.json");
		if (await fileExists(trajPath)) {
			try {
				trajectory = await readJsonFile<Trajectory>(trajPath);
			} catch {
				// skip malformed trajectory
			}
		}

		hasRawDumps = await fileExists(join(dir, "raw_dumps"));
		sessionTrajectories.push({ key, trajectory, hasRawDumps });
	}

	return { run, sessionTrajectories };
};
