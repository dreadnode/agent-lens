import { error } from "@sveltejs/kit";
import type { PageServerLoad } from "./$types";
import type { Trajectory, Step } from "$lib/types/atif";
import type { ApiCapture } from "$lib/types/api-capture";
import { readJsonFile, readJsonlFile, readTextFile, sessionDir, fileExists, runPath } from "$lib/server/fs";
import { join } from "node:path";
import { readFile, readdir } from "node:fs/promises";
import yaml from "js-yaml";

/**
 * Parse an SSE response file to check if it contains text or thinking content blocks.
 * Returns true if the response starts a new "turn" (has text/thinking, not just tool_use).
 */
function responseHasTextContent(sseBody: string): boolean {
	for (const block of sseBody.split("\n\n")) {
		const lines = block.trim().split("\n");
		let eventType: string | null = null;
		let dataStr: string | null = null;
		for (const line of lines) {
			if (line.startsWith("event: ")) eventType = line.slice(7).trim();
			else if (line.startsWith("data: ")) dataStr = line.slice(6);
		}
		if (eventType === "content_block_start" && dataStr) {
			try {
				const data = JSON.parse(dataStr);
				const type = data?.content_block?.type;
				if (type === "text" || type === "thinking") return true;
			} catch {
				// skip malformed
			}
		}
	}
	return false;
}

function getMessageText(msg: string | { type: string; text?: string }[]): string {
	if (typeof msg === "string") return msg;
	if (!Array.isArray(msg)) return "";
	return msg
		.filter((p: { type: string; text?: string }) => p.type === "text" && p.text)
		.map((p: { type: string; text?: string }) => p.text!)
		.join("\n");
}

/**
 * Count the number of agent groups that ChatView will produce.
 * Must mirror the grouping logic in ChatView.svelte exactly.
 */
function countAgentGroups(steps: Step[]): number {
	let count = 0;
	let groupHasToolCalls = false;

	for (const step of steps) {
		if (step.source !== "agent") {
			groupHasToolCalls = false;
			continue;
		}

		const hasThinking = !!step.reasoning_content;
		const hasText = !!getMessageText(step.message).trim();
		const hasToolCalls = !!(step.tool_calls && step.tool_calls.length > 0);

		if (count === 0 || ((hasThinking || hasText) && groupHasToolCalls)) {
			count++;
			groupHasToolCalls = false;
		}

		if (hasToolCalls) groupHasToolCalls = true;
	}
	return count;
}

/**
 * Scan response SSE files in raw_dumps/ and return request indices
 * whose responses contain text/thinking content blocks.
 */
async function getTextResponseIndices(rawDumpsDir: string): Promise<number[]> {
	const indices: number[] = [];
	try {
		const files = await readdir(rawDumpsDir);
		const responseFiles = files
			.filter((f) => /^response_\d+\.txt$/.test(f))
			.sort();

		for (const file of responseFiles) {
			const match = file.match(/^response_(\d+)\.txt$/);
			if (!match) continue;
			const reqIdx = parseInt(match[1]);
			try {
				const sseBody = await readFile(join(rawDumpsDir, file), "utf-8");
				if (responseHasTextContent(sseBody)) {
					indices.push(reqIdx);
				}
			} catch {
				// skip unreadable
			}
		}
	} catch {
		// ignore readdir errors
	}
	return indices;
}

export const load: PageServerLoad = async ({ params }) => {
	const dir = sessionDir(params.runName, params.sessionIndex);
	let trajectory: Trajectory;
	try {
		trajectory = await readJsonFile<Trajectory>(join(dir, "trajectory.json"));
	} catch {
		error(404, `Session not found: ${params.runName}/session ${params.sessionIndex}`);
	}

	// Load session prompt from config.yaml
	let sessionPrompt: string | null = null;
	try {
		const configText = await readTextFile(join(runPath(params.runName), "config.yaml"));
		const config = yaml.load(configText) as any;
		const sessionConf = config?.sessions?.find(
			(s: any) => s.session_index === parseInt(params.sessionIndex),
		);
		sessionPrompt = sessionConf?.prompt ?? null;
	} catch {
		// config may not exist
	}

	// Check which requests have raw dumps available
	let hasRawDumps = false;
	const rawDumpsDir = join(dir, "raw_dumps");
	if (await fileExists(rawDumpsDir)) {
		hasRawDumps = true;
	}

	// Build mainRequestIndices: map group index → API request index.
	// Strategy: try api_captures main-agent filter first, fall back to scanning all responses.
	// Pick whichever matches the actual group count from the trajectory.
	let mainRequestIndices: number[] = [];

	if (hasRawDumps) {
		const groupCount = countAgentGroups(trajectory.steps);

		// Approach 1: use api_captures to filter to main-agent requests,
		// then filter by response content (text/thinking)
		let mainOnlyIndices: number[] = [];
		const capturesPath = join(dir, "api_captures.jsonl");
		if (await fileExists(capturesPath)) {
			try {
				const captures = await readJsonlFile<ApiCapture>(capturesPath);
				const mainReqIndices = captures
					.filter((c) => !c.agent_context || c.agent_context === "main")
					.map((c) => c.request_index);

				for (const reqIdx of mainReqIndices) {
					const respPath = join(rawDumpsDir, `response_${String(reqIdx).padStart(3, "0")}.txt`);
					try {
						const sseBody = await readFile(respPath, "utf-8");
						if (responseHasTextContent(sseBody)) {
							mainOnlyIndices.push(reqIdx);
						}
					} catch {
						// skip missing
					}
				}
			} catch {
				// ignore
			}
		}

		if (mainOnlyIndices.length === groupCount) {
			// api_captures classification is correct
			mainRequestIndices = mainOnlyIndices;
		} else {
			// Approach 2: scan ALL response files (handles misclassification, mixed subagent trajectories)
			const allTextIndices = await getTextResponseIndices(rawDumpsDir);
			if (allTextIndices.length === groupCount) {
				mainRequestIndices = allTextIndices;
			} else {
				// Neither matches exactly — use the closer one
				const mainDiff = Math.abs(mainOnlyIndices.length - groupCount);
				const allDiff = Math.abs(allTextIndices.length - groupCount);
				mainRequestIndices = mainDiff <= allDiff ? mainOnlyIndices : allTextIndices;
			}
		}
	}

	return {
		trajectory,
		mainRequestIndices,
		hasRawDumps,
		sessionPrompt,
	};
};
