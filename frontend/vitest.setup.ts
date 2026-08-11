import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// React Testing Library does not auto-clean when globals are enabled via
// vitest.config rather than the RTL auto-cleanup entrypoint.
afterEach(() => {
  cleanup();
});
