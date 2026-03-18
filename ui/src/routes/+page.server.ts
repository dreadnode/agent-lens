import type { PageServerLoad } from "./$types";
import { listRuns } from "$lib/server/runs";

export const load: PageServerLoad = async () => {
	const runs = await listRuns();
	return { runs };
};
