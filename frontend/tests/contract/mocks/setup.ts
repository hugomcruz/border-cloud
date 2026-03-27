import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

/**
 * MSW Node server for Vitest contract tests.
 * Import and extend handlers from each feature's handler file.
 * Start this server in Vitest setup files.
 */
export const server = setupServer();

export { http, HttpResponse };
