import type { PageServerLoad } from "./$types";
import type { Trajectory } from "$lib/types/atif";
import { readJsonFile, sessionDir } from "$lib/server/fs";
import { join } from "node:path";

export const load: PageServerLoad = async ({ params }) => {
	const dir = sessionDir(params.runName, params.sessionIndex);
	const trajectory = await readJsonFile<Trajectory>(
		join(dir, params.filename)
	);

	// Extract the parent tool_use_id so we can find the subagent's return value
	const parentToolUseId = (trajectory.extra as Record<string, unknown>)?.parent_tool_use_id as string | undefined;

	// Try to find the subagent's return value from the parent trajectory
	let returnValue: string | null = null;
	if (parentToolUseId) {
		try {
			const parentTrajectory = await readJsonFile<Trajectory>(join(dir, "trajectory.json"));
			for (const step of parentTrajectory.steps) {
				if (!step.observation?.results) continue;
				for (const r of step.observation.results) {
					if (r.source_call_id === parentToolUseId) {
						returnValue = typeof r.content === "string"
							? r.content
							: Array.isArray(r.content)
								? r.content.filter((p: any) => p.type === "text").map((p: any) => p.text).join("\n")
								: null;
					}
				}
			}
		} catch {
			// Parent trajectory may not exist or be readable
		}
	}

	return {
		trajectory,
		sessionIndex: params.sessionIndex,
		filename: params.filename,
		returnValue,
	};
};
