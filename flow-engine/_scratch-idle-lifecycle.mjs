import { openAccountBrowser, closeAccountBrowser } from "./lib/accounts.js";

const ACCOUNT_ID = "0edfb022-bcda-4691-a7dc-4a8d9a4c4b0d";

console.log("[idle-lifecycle] opening account browser (production openAccountBrowser, default options)");
const { page } = await openAccountBrowser(ACCOUNT_ID);
console.log("[idle-lifecycle] browser open, page created. No navigation, no Flow, no generation.");

console.log("[idle-lifecycle] idling 90 seconds...");
await new Promise((r) => setTimeout(r, 90000));

console.log("[idle-lifecycle] closing via production closeAccountBrowser (normal shutdown path)");
await closeAccountBrowser(ACCOUNT_ID);
console.log("[idle-lifecycle] closed. done.");
