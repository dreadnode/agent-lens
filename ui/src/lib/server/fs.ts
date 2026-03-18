import { readFile, readdir, stat } from "node:fs/promises";
import { join } from "node:path";
import { RUNS_DIR } from "$env/static/private";

export function runsDir(): string {
	return RUNS_DIR || "../runs";
}

export async function readJsonFile<T>(path: string): Promise<T> {
	const content = await readFile(path, "utf-8");
	return JSON.parse(content) as T;
}

export async function readJsonlFile<T>(path: string): Promise<T[]> {
	const content = await readFile(path, "utf-8");
	return content
		.trim()
		.split("\n")
		.filter(Boolean)
		.map((line) => JSON.parse(line) as T);
}

export async function readTextFile(path: string): Promise<string> {
	return readFile(path, "utf-8");
}

export async function fileExists(path: string): Promise<boolean> {
	try {
		await stat(path);
		return true;
	} catch {
		return false;
	}
}

export async function listDirectories(dir: string): Promise<string[]> {
	try {
		const entries = await readdir(dir, { withFileTypes: true });
		return entries
			.filter((e) => e.isDirectory())
			.map((e) => e.name)
			.sort();
	} catch {
		return [];
	}
}

export function runPath(runName: string): string {
	return join(runsDir(), runName);
}

/**
 * Get session directory path. Accepts a number (plain session) or
 * string like "2_r01" (replicate).
 */
export function sessionDir(runName: string, sessionKey: number | string): string {
	if (typeof sessionKey === "number") {
		const idx = String(sessionKey).padStart(2, "0");
		return join(runPath(runName), `session_${idx}`);
	}
	// Parse "2_r01" → "session_02_r01"
	const match = sessionKey.match(/^(\d+)_r(\d+)$/);
	if (match) {
		const idx = match[1].padStart(2, "0");
		const rep = match[2].padStart(2, "0");
		return join(runPath(runName), `session_${idx}_r${rep}`);
	}
	// Plain number as string
	const idx = sessionKey.padStart(2, "0");
	return join(runPath(runName), `session_${idx}`);
}
