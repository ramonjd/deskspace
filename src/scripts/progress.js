// What the player has done so far, kept in this browser so a reload doesn't
// lose it: a set of named steps ('unlocked', 'snake', 'read-duties' and so
// on). Private windows can refuse storage; then progress lasts the visit.

const KEY = 'cabin.progress';
const listeners = new Set();
let done = {};
try {
	done = JSON.parse(localStorage.getItem(KEY)) || {};
} catch {
	// Nothing saved, or no storage: start from scratch.
}

export const progress = {
	has: (step) => Boolean(done[step]),
	mark(step, value = true) {
		if (done[step] === value) return;
		done[step] = value;
		try {
			localStorage.setItem(KEY, JSON.stringify(done));
		} catch {
			// Kept for this visit only.
		}
		for (const listener of listeners) listener(step);
	},
	listen: (listener) => listeners.add(listener),
	reset() {
		done = {};
		try {
			localStorage.removeItem(KEY);
		} catch {
			// Nothing to remove.
		}
	},
};
