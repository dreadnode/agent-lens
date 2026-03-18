import { json, error } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";
import { sessionDir } from "$lib/server/fs";
import { readFile, readdir, mkdir, writeFile, stat } from "node:fs/promises";
import { join } from "node:path";
import { env } from "$env/dynamic/private";

interface VariantEdit {
	path: string; // JSON path like "messages[14].content[0].text"
	original: string;
	replacement: string;
}

interface ResampleRequest {
	runName: string;
	sessionIndex: number;
	requestIndex: number;
	count: number;
	variant?: {
		label: string;
		edits: VariantEdit[];
	};
}

interface VariantMeta {
	label: string;
	base_request_index: number;
	edits: VariantEdit[];
	created_at: string;
}

/**
 * Build replay headers from captured headers, replacing auth.
 */
function buildHeaders(
	capturedHeaders: Record<string, string>,
	apiKey: string,
	targetUrl: string,
): Record<string, string> {
	const headers: Record<string, string> = { ...capturedHeaders };
	if (targetUrl.includes("openrouter.ai")) {
		headers["Authorization"] = `Bearer ${apiKey}`;
		delete headers["x-api-key"];
	} else {
		headers["x-api-key"] = apiKey;
		delete headers["Authorization"];
	}
	for (const key of Object.keys(headers)) {
		if (key.toLowerCase().startsWith("x-stainless")) {
			delete headers[key];
		}
	}
	delete headers["Connection"];
	delete headers["Accept-Encoding"];
	return headers;
}

/**
 * Apply a JSON path edit to request data.
 * Supports paths like "messages[14].content[0].text" or "messages[14].content[0].thinking"
 */
function applyEdit(data: Record<string, unknown>, edit: VariantEdit): void {
	const segments = edit.path.replace(/\[(\d+)\]/g, ".$1").split(".");
	let current: unknown = data;

	for (let i = 0; i < segments.length - 1; i++) {
		const seg = segments[i];
		if (current === null || current === undefined) return;
		if (Array.isArray(current)) {
			current = current[parseInt(seg)];
		} else if (typeof current === "object") {
			current = (current as Record<string, unknown>)[seg];
		}
	}

	const lastSeg = segments[segments.length - 1];
	if (current !== null && current !== undefined && typeof current === "object") {
		if (Array.isArray(current)) {
			current[parseInt(lastSeg)] = edit.replacement;
		} else {
			(current as Record<string, unknown>)[lastSeg] = edit.replacement;
		}
	}
}

/**
 * Call the API once (non-streaming).
 */
async function callApi(
	url: string,
	headers: Record<string, string>,
	requestData: Record<string, unknown>,
): Promise<Record<string, unknown>> {
	const resp = await fetch(url, {
		method: "POST",
		headers,
		body: JSON.stringify(requestData),
	});

	if (!resp.ok) {
		const text = await resp.text();
		throw new Error(`API error ${resp.status}: ${text.slice(0, 500)}`);
	}

	return resp.json();
}

/**
 * Load samples from a directory.
 */
async function loadSamples(dirPath: string): Promise<object[]> {
	try {
		const files = await readdir(dirPath);
		const sampleFiles = files
			.filter((f) => f.startsWith("sample_") && f.endsWith(".json") && !f.includes("error"))
			.sort();

		return Promise.all(
			sampleFiles.map(async (f) => {
				const content = await readFile(join(dirPath, f), "utf-8");
				return JSON.parse(content);
			}),
		);
	} catch {
		return [];
	}
}

/**
 * Find the next variant ID for a request (v01, v02, ...).
 */
async function nextVariantId(resamplesDir: string, pad: string): Promise<string> {
	try {
		const entries = await readdir(resamplesDir);
		const variantNums = entries
			.filter((e) => e.startsWith(`request_${pad}_v`))
			.map((e) => parseInt(e.match(/_v(\d+)$/)?.[1] || "0"))
			.filter((n) => n > 0);
		const next = variantNums.length > 0 ? Math.max(...variantNums) + 1 : 1;
		return `v${String(next).padStart(2, "0")}`;
	} catch {
		return "v01";
	}
}

/**
 * Parse an SSE response file to extract the assistant's content blocks.
 * Handles interleaved blocks (multiple blocks streaming concurrently).
 * Returns an array of content blocks (text, thinking, tool_use, etc.)
 */
async function parseResponseContent(
	dir: string,
	pad: string,
): Promise<Record<string, unknown>[] | null> {
	try {
		const respPath = join(dir, "raw_dumps", `response_${pad}.txt`);
		const sseBody = await readFile(respPath, "utf-8");
		// Track blocks by index (SSE can interleave multiple blocks)
		const activeBlocks = new Map<number, Record<string, unknown>>();
		const finishedBlocks: { index: number; block: Record<string, unknown> }[] = [];

		for (const chunk of sseBody.split("\n\n")) {
			const lines = chunk.trim().split("\n");
			let eventType: string | null = null;
			let dataStr: string | null = null;
			for (const line of lines) {
				if (line.startsWith("event: ")) eventType = line.slice(7).trim();
				else if (line.startsWith("data: ")) dataStr = line.slice(6);
			}
			if (!eventType || !dataStr) continue;
			try {
				const data = JSON.parse(dataStr);
				const idx: number = data.index ?? 0;
				if (eventType === "content_block_start") {
					const block = { ...data.content_block };
					if (block.type === "text") block.text = "";
					if (block.type === "thinking") block.thinking = "";
					activeBlocks.set(idx, block);
				} else if (eventType === "content_block_delta") {
					const block = activeBlocks.get(idx);
					if (!block) continue;
					const delta = data.delta;
					if (delta?.type === "text_delta" && block.type === "text") {
						block.text = (block.text as string) + (delta.text || "");
					} else if (delta?.type === "thinking_delta" && block.type === "thinking") {
						block.thinking = (block.thinking as string) + (delta.thinking || "");
					} else if (delta?.type === "input_json_delta" && block.type === "tool_use") {
						block._inputJson =
							((block._inputJson as string) || "") + (delta.partial_json || "");
					}
				} else if (eventType === "content_block_stop") {
					const block = activeBlocks.get(idx);
					if (block) {
						// Parse accumulated tool_use input
						if (block.type === "tool_use" && block._inputJson) {
							try {
								block.input = JSON.parse(block._inputJson as string);
							} catch {
								// leave input as-is
							}
							delete block._inputJson;
						}
						finishedBlocks.push({ index: idx, block });
						activeBlocks.delete(idx);
					}
				}
			} catch {
				// skip malformed
			}
		}
		// Sort by original index order
		finishedBlocks.sort((a, b) => a.index - b.index);
		const blocks = finishedBlocks.map((fb) => fb.block);
		return blocks.length > 0 ? blocks : null;
	} catch {
		return null;
	}
}

/** Load the raw request + headers for a given request index */
async function loadRawRequest(dir: string, pad: string) {
	const rawPath = join(dir, "raw_dumps", `request_${pad}.json`);
	const content = await readFile(rawPath, "utf-8");
	const requestData = JSON.parse(content) as Record<string, unknown>;

	const hdrPath = join(dir, "raw_dumps", `request_${pad}_headers.json`);
	let targetUrl: string;
	let capturedHeaders: Record<string, string>;
	try {
		const hdrContent = await readFile(hdrPath, "utf-8");
		const hdrData = JSON.parse(hdrContent);
		targetUrl = hdrData.target;
		capturedHeaders = hdrData.headers || {};
	} catch {
		targetUrl =
			(env.ANTHROPIC_BASE_URL || "https://api.anthropic.com").replace(/\/$/, "") +
			"/v1/messages";
		capturedHeaders = {
			"anthropic-version": "2023-06-01",
			"content-type": "application/json",
		};
	}

	return { requestData, targetUrl, capturedHeaders };
}

/** GET: load existing resample results + variants */
export const GET: RequestHandler = async ({ url }) => {
	const runName = url.searchParams.get("runName");
	const rawSessionIndex = url.searchParams.get("sessionIndex") || "0";
	const requestIndex = parseInt(url.searchParams.get("requestIndex") || "0");

	if (!runName || !requestIndex) {
		return error(400, "Missing runName, sessionIndex, or requestIndex");
	}

	// Support both plain numbers ("2") and replicate keys ("2_r01")
	const sessionKey = rawSessionIndex.includes("_") ? rawSessionIndex : parseInt(rawSessionIndex);
	const dir = sessionDir(runName, sessionKey);
	const pad = String(requestIndex).padStart(3, "0");
	const resamplesDir = join(dir, "resamples");

	// Load vanilla samples
	const samples = await loadSamples(join(resamplesDir, `request_${pad}`));

	// Load variants
	interface VariantResult {
		id: string;
		label: string;
		edits: VariantEdit[];
		samples: object[];
	}
	const variants: VariantResult[] = [];

	try {
		const entries = await readdir(resamplesDir);
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
				const meta = JSON.parse(metaContent) as VariantMeta;
				label = meta.label;
				edits = meta.edits;
			} catch {
				// no variant.json
			}

			const vSamples = await loadSamples(vPath);
			if (vSamples.length > 0 || edits.length > 0) {
				variants.push({ id: vid, label, edits, samples: vSamples });
			}
		}
	} catch {
		// no resamples dir
	}

	// Optionally load raw request messages + response content for the editor
	let rawMessages: unknown[] | undefined;
	let responseContent: unknown[] | undefined;
	if (url.searchParams.get("includeRaw") === "true") {
		try {
			const raw = await loadRawRequest(dir, pad);
			rawMessages = raw.requestData.messages as unknown[];
		} catch {
			// no raw dump
		}
		// Also parse the response to get the assistant's output content blocks
		responseContent = (await parseResponseContent(dir, pad)) ?? undefined;
	}

	return json({ samples, variants, rawMessages, responseContent });
};

/** POST: run new resamples (vanilla or variant) */
export const POST: RequestHandler = async ({ request }) => {

	const body = (await request.json()) as ResampleRequest;
	const { runName, sessionIndex, requestIndex, count, variant } = body;

	if (!runName || !requestIndex || !count) {
		return error(400, "Missing required fields");
	}

	const dir = sessionDir(runName, sessionIndex);
	const pad = String(requestIndex).padStart(3, "0");

	// Load raw request
	let raw;
	try {
		raw = await loadRawRequest(dir, pad);
	} catch {
		return error(404, `No raw dump found for request ${requestIndex}`);
	}

	let { requestData } = raw;
	const { targetUrl, capturedHeaders } = raw;

	// Resolve API key based on target
	const isOpenRouter = targetUrl.includes("openrouter.ai");
	const apiKey = isOpenRouter ? env.OPENROUTER_API_KEY : env.ANTHROPIC_API_KEY;
	if (!apiKey) {
		const keyName = isOpenRouter ? "OPENROUTER_API_KEY" : "ANTHROPIC_API_KEY";
		return error(500, `${keyName} not configured`);
	}

	// Force non-streaming
	requestData.stream = false;
	// Remove SDK-specific fields that aren't part of the public API
	delete requestData.context_management;
	delete requestData.metadata;

	// Determine output directory (always keyed off the original requestIndex)
	let resampleDir: string;
	const resamplesDir = join(dir, "resamples");

	if (variant) {
		// Apply edits to a deep copy
		requestData = JSON.parse(JSON.stringify(requestData));
		for (const edit of variant.edits) {
			applyEdit(requestData, edit);
		}
		// Thinking blocks are read-only in the editor, so signatures stay valid.
		// If someone manually tampers with thinking via the CLI, the API will
		// return a clear 400 error.

		// Assign variant ID
		const vid = await nextVariantId(resamplesDir, pad);
		resampleDir = join(resamplesDir, `request_${pad}_${vid}`);
		await mkdir(resampleDir, { recursive: true });

		// Save variant metadata + edited request
		const meta: VariantMeta = {
			label: variant.label,
			base_request_index: requestIndex,
			edits: variant.edits,
			created_at: new Date().toISOString(),
		};
		await writeFile(join(resampleDir, "variant.json"), JSON.stringify(meta, null, 2));
		await writeFile(join(resampleDir, "request.json"), JSON.stringify(requestData, null, 2));
	} else {
		resampleDir = join(resamplesDir, `request_${pad}`);
		await mkdir(resampleDir, { recursive: true });
	}

	const headers = buildHeaders(capturedHeaders, apiKey, targetUrl);

	// Find next sample number
	let nextNum = 1;
	try {
		const existing = await readdir(resampleDir);
		const sampleNums = existing
			.filter((f) => f.startsWith("sample_") && f.endsWith(".json"))
			.map((f) => parseInt(f.match(/sample_(\d+)/)?.[1] || "0"))
			.filter((n) => n > 0);
		if (sampleNums.length > 0) {
			nextNum = Math.max(...sampleNums) + 1;
		}
	} catch {
		// dir fresh
	}

	// Run resamples
	const samples: Record<string, unknown>[] = [];
	for (let i = 0; i < count; i++) {
		const sampleNum = nextNum + i;
		try {
			const response = await callApi(targetUrl, headers, requestData);
			const samplePath = join(
				resampleDir,
				`sample_${String(sampleNum).padStart(2, "0")}.json`,
			);
			await writeFile(samplePath, JSON.stringify(response, null, 2));
			samples.push(response);
		} catch (e) {
			const errMsg = e instanceof Error ? e.message : String(e);
			samples.push({ error: errMsg });
			const errPath = join(
				resampleDir,
				`sample_${String(sampleNum).padStart(2, "0")}_error.json`,
			);
			await writeFile(errPath, JSON.stringify({ error: errMsg }));
		}
	}

	return json({ samples, variantId: variant ? resampleDir.split("_").pop() : undefined });
};
