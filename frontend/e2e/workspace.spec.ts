import { expect, test, type Page } from "@playwright/test";

/**
 * The whole product, once, against the real API.
 *
 * Every other test in this repository mocks the API. That is right for them —
 * they assert what the UI does with a response — but it means nothing checks
 * the seam this platform is actually made of: a file reaching the worker, the
 * worker finishing, and a question against the uploaded corpus being answered
 * from the uploaded documents rather than from the benchmark ones.
 *
 * That last part is the failure worth catching. When the query page ignored
 * the corpus parameter, every unit test still passed and the feature was
 * entirely broken: uploads were answered from a different corpus, which looks
 * exactly like bad retrieval.
 */

/** Content specific enough that an answer cannot come from the benchmark corpus. */
const DOCUMENT = `# Whistlebrook Deployment Notes

## Rollback
Whistlebrook rolls back by promoting the previous image tag, never by
reverting the migration. The rollback window is 45 minutes, after which the
schema change is considered load-bearing and the only path forward is a fix
forward.

## Ownership
The Whistlebrook service is owned by the Platform Reliability group and
paged through the peregrine rotation.
`;

const FILENAME = "whistlebrook-notes.md";

async function uploadDocument(page: Page, name: string, body: string) {
  await page.goto("/workspace");
  await page.setInputFiles('input[type="file"]', {
    name,
    mimeType: "text/markdown",
    buffer: Buffer.from(body),
  });
}

/** The row for a filename, whatever else is in the corpus. */
const documentRow = (page: Page, name: string) =>
  page.locator("li").filter({ hasText: name }).first();

test.describe("upload, index, and query your own documents", () => {
  test("a document walks from upload to READY and answers a question about itself", async ({
    page,
  }) => {
    await uploadDocument(page, FILENAME, DOCUMENT);

    const row = documentRow(page, FILENAME);
    await expect(row).toBeVisible();

    // Indexing is asynchronous and the list polls itself. Waiting for READY
    // rather than for a fixed delay is the assertion: it fails if the worker
    // never picks the job up.
    await expect(row.getByText("READY")).toBeVisible({ timeout: 120_000 });
    await expect(row).toContainText("chunks");

    // The link carries the corpus. If it stops doing so, the answer below
    // comes from the benchmark documents instead.
    const ask = row.getByRole("link", { name: /ask questions/i });
    await expect(ask).toHaveAttribute("href", /corpus=/);
    await ask.click();
    await expect(page).toHaveURL(/\/query\?.*corpus=/);

    await page.getByPlaceholder(/Ask a question/i).fill("What is the rollback window?");
    await page.getByPlaceholder(/Ask a question/i).press("Enter");

    // "ms total" only renders once the stream reports done, so this waits for
    // a whole answer rather than the first token.
    await expect(page.getByText(/ms total/)).toBeVisible({ timeout: 120_000 });

    const answer = page.locator("p[aria-live='polite']").first();
    await expect(answer).toContainText("45");

    // The sources must be the uploaded file. An answer that happened to be
    // right while citing the benchmark corpus is the bug this catches.
    const retrieval = page.getByRole("table");
    await expect(retrieval).toBeVisible();
    await expect(retrieval).toContainText(FILENAME);
  });

  test("the retrieval trace reports the stages that actually ran", async ({ page }) => {
    await page.goto(
      "/query?q=" +
        encodeURIComponent("Who owns Whistlebrook?") +
        "&corpus=workspace&retriever=hybrid",
    );
    await expect(page.getByText(/ms total/)).toBeVisible({ timeout: 120_000 });

    // Hybrid ran both retrievers, so both columns exist and the reranker's
    // does not — the table follows the results, not the request.
    await expect(page.getByRole("columnheader", { name: "Dense" })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "BM25" })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "Reranked" })).toHaveCount(0);
    await expect(page.getByText(/reranker did not run/i)).toBeVisible();

    // The pipeline diagram accounts for the time the answer took.
    await expect(page.getByText(/across \d+ stages/)).toBeVisible();
  });

  test("a question the documents cannot answer is declined, not invented", async ({
    page,
  }) => {
    await page.goto(
      "/query?q=" +
        encodeURIComponent("What is the capital of Portugal?") +
        "&corpus=workspace",
    );
    await expect(page.getByText(/ms total/)).toBeVisible({ timeout: 120_000 });

    const answer = await page.locator("p[aria-live='polite']").first().innerText();
    // Either the model abstains, or it says it cannot answer from the context.
    // What it must not do is answer "Lisbon" from its own training data.
    expect(answer.toLowerCase()).not.toContain("lisbon");
  });

  test("an unsupported file is refused before it is uploaded", async ({ page }) => {
    await page.goto("/workspace");

    // Dropped rather than picked: the file input filters by its accept
    // attribute, so this is the only path an unsupported type can arrive by.
    await page.locator("text=Drop documents here").evaluate((node) => {
      const file = new File(["binary"], "payload.exe", {
        type: "application/octet-stream",
      });
      const data = new DataTransfer();
      data.items.add(file);
      node
        .closest("div")!
        .dispatchEvent(new DragEvent("drop", { dataTransfer: data, bubbles: true }));
    });

    // Scoped to the list: Next's route announcer is also role="alert".
    await expect(page.locator('ul[role="alert"]')).toContainText("no parser");
  });

  test("deleting a document removes its chunks from the corpus", async ({ page }) => {
    await page.goto("/workspace");
    const row = documentRow(page, FILENAME);
    await expect(row.getByText("READY")).toBeVisible({ timeout: 120_000 });

    await row
      .getByRole("button", { name: new RegExp(`delete ${FILENAME}`, "i") })
      .click();

    // Gone from the list, not merely greyed out.
    await expect(documentRow(page, FILENAME)).toHaveCount(0, { timeout: 60_000 });

    // And gone from the index: the same question no longer finds the chunk.
    await page.goto(
      "/query?q=" +
        encodeURIComponent("What is the rollback window?") +
        "&corpus=workspace",
    );
    await expect(page.getByText(/ms total/)).toBeVisible({ timeout: 120_000 });
    const sources = await page.locator("body").innerText();
    expect(sources).not.toContain(FILENAME);
  });
});
