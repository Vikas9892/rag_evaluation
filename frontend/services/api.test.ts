import { HttpResponse, http, delay, type JsonBodyType } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { ApiError } from "./api-error";
import { apiBaseUrl, getHealth, getMetrics, postQuery, streamQuery } from "./api";

const BASE = "http://localhost:8000";
const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

/** Assert the call rejects with an ApiError and hand it back for inspection. */
async function expectApiError(promise: Promise<unknown>): Promise<ApiError> {
  const error = await promise.then(
    () => null,
    (e: unknown) => e,
  );
  expect(error, "expected the call to reject").toBeInstanceOf(ApiError);
  return error as ApiError;
}

describe("apiBaseUrl", () => {
  it("falls back to localhost when unset", () => {
    expect(apiBaseUrl()).toBe(BASE);
  });

  it("strips a trailing slash so paths do not double up", () => {
    process.env.NEXT_PUBLIC_API_URL = "http://api.test/";
    expect(apiBaseUrl()).toBe("http://api.test");
    delete process.env.NEXT_PUBLIC_API_URL;
  });
});

describe("getHealth", () => {
  it("returns the parsed body", async () => {
    server.use(
      http.get(`${BASE}/health`, () => HttpResponse.json({ status: "healthy" })),
    );
    await expect(getHealth()).resolves.toEqual({ status: "healthy" });
  });

  it("sends Content-Type", async () => {
    let seen: string | null = null;
    server.use(
      http.get(`${BASE}/health`, ({ request }) => {
        seen = request.headers.get("content-type");
        return HttpResponse.json({ status: "healthy" });
      }),
    );
    await getHealth();
    expect(seen).toBe("application/json");
  });
});

describe("getMetrics", () => {
  it("returns the parsed body", async () => {
    const body = {
      total_queries: 2,
      avg_retrieval_ms: 36.2,
      avg_generation_ms: 447.3,
      errors: 0,
    };
    server.use(http.get(`${BASE}/metrics`, () => HttpResponse.json(body)));
    await expect(getMetrics()).resolves.toEqual(body);
  });
});

describe("postQuery", () => {
  it("posts the question", async () => {
    let body: unknown;
    server.use(
      http.post(`${BASE}/query`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ answer: "ok" });
      }),
    );
    await postQuery("what is a deadlock?");
    expect(body).toEqual({ question: "what is a deadlock?" });
  });

  it("omits top_k when not given, rather than sending null", async () => {
    let body: Record<string, unknown> = {};
    server.use(
      http.post(`${BASE}/query`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ answer: "ok" });
      }),
    );
    await postQuery("q");
    expect("top_k" in body).toBe(false);
  });

  it("includes top_k when given", async () => {
    let body: unknown;
    server.use(
      http.post(`${BASE}/query`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ answer: "ok" });
      }),
    );
    await postQuery("q", { topK: 10 });
    expect(body).toEqual({ question: "q", top_k: 10 });
  });
});

describe("error mapping", () => {
  const cases = [
    { status: 400, kind: "bad_request", retryable: false },
    { status: 422, kind: "bad_request", retryable: false },
    { status: 404, kind: "not_found", retryable: false },
    { status: 429, kind: "rate_limited", retryable: true },
    { status: 503, kind: "unavailable", retryable: false },
    { status: 504, kind: "timeout", retryable: true },
    { status: 500, kind: "server", retryable: true },
  ] as const;

  for (const { status, kind, retryable } of cases) {
    it(`maps ${status} to "${kind}" (retryable: ${retryable})`, async () => {
      server.use(http.get(`${BASE}/health`, () => new HttpResponse(null, { status })));
      const error = await expectApiError(getHealth());
      expect(error.kind).toBe(kind);
      expect(error.status).toBe(status);
      expect(error.retryable).toBe(retryable);
    });
  }

  it("surfaces FastAPI's detail as the user message", async () => {
    server.use(
      http.get(`${BASE}/health`, () =>
        HttpResponse.json({ detail: "Index not available" }, { status: 503 }),
      ),
    );
    const error = await expectApiError(getHealth());
    expect(error.detail).toBe("Index not available");
    expect(error.userMessage).toBe("Index not available");
  });

  it("summarises a 422 validation list instead of stringifying objects", async () => {
    server.use(
      http.post(`${BASE}/query`, () =>
        HttpResponse.json({ detail: [{ msg: "a" }, { msg: "b" }] }, { status: 422 }),
      ),
    );
    const error = await expectApiError(postQuery("q"));
    // The messages themselves, not a count of them: see the validation-error
    // tests below for the field-qualified form FastAPI actually sends.
    expect(error.detail).toBe("a; b");
  });

  it("falls back to its own message when the body has no detail", async () => {
    server.use(http.get(`${BASE}/health`, () => new HttpResponse(null, { status: 500 })));
    const error = await expectApiError(getHealth());
    expect(error.userMessage).toContain("500");
  });

  it("maps an unreachable server to network", async () => {
    server.use(http.get(`${BASE}/health`, () => HttpResponse.error()));
    const error = await expectApiError(getHealth());
    expect(error.kind).toBe("network");
    expect(error.retryable).toBe(true);
  });

  it("maps a slow response to timeout", async () => {
    server.use(
      http.get(`${BASE}/health`, async () => {
        await delay(200);
        return HttpResponse.json({ status: "healthy" });
      }),
    );
    // 5 ms deadline via an external signal, so the test does not wait 5 s.
    const error = await expectApiError(getHealth(AbortSignal.timeout(5)));
    expect(error.kind).toBe("timeout");
  });

  it("distinguishes a caller cancellation from a timeout", async () => {
    // A navigation or superseded query must not be reported as a failure.
    server.use(
      http.get(`${BASE}/health`, async () => {
        await delay(200);
        return HttpResponse.json({ status: "healthy" });
      }),
    );
    const controller = new AbortController();
    const promise = getHealth(controller.signal);
    controller.abort();
    const error = await expectApiError(promise);
    expect(error.kind).toBe("cancelled");
    expect(error.retryable).toBe(false);
  });

  it("maps a non-JSON 200 body to parse", async () => {
    server.use(http.get(`${BASE}/health`, () => new HttpResponse("not json")));
    const error = await expectApiError(getHealth());
    expect(error.kind).toBe("parse");
    expect(error.retryable).toBe(false);
  });
});

describe("streamQuery", () => {
  function sse(...frames: string[]): Response {
    return new HttpResponse(frames.map((f) => `data: ${f}\n\n`).join(""), {
      headers: { "Content-Type": "text/event-stream" },
    });
  }

  async function collect(question = "q") {
    const events = [];
    for await (const event of streamQuery(question)) events.push(event);
    return events;
  }

  it("yields each event in order", async () => {
    server.use(
      http.post(`${BASE}/stream`, () =>
        sse(
          JSON.stringify({ type: "sources", data: [] }),
          JSON.stringify({ type: "token", data: "Hello" }),
          JSON.stringify({ type: "token", data: " world" }),
          JSON.stringify({ type: "done" }),
        ),
      ),
    );
    expect(await collect()).toEqual([
      { type: "sources", data: [] },
      { type: "token", data: "Hello" },
      { type: "token", data: " world" },
      { type: "done" },
    ]);
  });

  it("reassembles a frame split across chunk boundaries", async () => {
    // The critical failure mode: naive per-chunk parsing loses tokens whenever
    // a frame straddles a network chunk.
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('data: {"type":"tok'));
        controller.enqueue(new TextEncoder().encode('en","data":"split"}\n\n'));
        controller.close();
      },
    });
    server.use(
      http.post(
        `${BASE}/stream`,
        () =>
          new HttpResponse(stream, {
            headers: { "Content-Type": "text/event-stream" },
          }),
      ),
    );
    expect(await collect()).toEqual([{ type: "token", data: "split" }]);
  });

  it("skips an undecodable frame instead of discarding the stream", async () => {
    server.use(
      http.post(`${BASE}/stream`, () =>
        sse("{ not json", JSON.stringify({ type: "token", data: "kept" })),
      ),
    );
    expect(await collect()).toEqual([{ type: "token", data: "kept" }]);
  });

  it("maps a failed stream request to an ApiError", async () => {
    server.use(
      http.post(`${BASE}/stream`, () =>
        HttpResponse.json({ detail: "GROQ_API_KEY is not set" }, { status: 503 }),
      ),
    );
    const error = await expectApiError(collect());
    expect(error.kind).toBe("unavailable");
    expect(error.userMessage).toBe("GROQ_API_KEY is not set");
  });
});

describe("validation errors", () => {
  async function detailFor(body: JsonBodyType): Promise<string | undefined> {
    server.use(
      http.get(`${BASE}/health`, () => HttpResponse.json(body, { status: 422 })),
    );
    try {
      await getHealth();
    } catch (error) {
      return (error as ApiError).detail;
    }
    return undefined;
  }

  it("names the field and the reason", async () => {
    // Rendering the raw payload puts "[object Object]" in front of the user;
    // a count tells them nothing they can act on.
    const detail = await detailFor({
      detail: [
        {
          type: "less_than_equal",
          loc: ["body", "top_k"],
          msg: "Input should be less than or equal to 20",
        },
      ],
    });

    expect(detail).toBe("top_k: Input should be less than or equal to 20");
  });

  it("drops the location prefix, which says nothing to a user", async () => {
    const detail = await detailFor({
      detail: [{ loc: ["query", "chunk_size"], msg: "Input should be >= 50" }],
    });

    expect(detail).toBe("chunk_size: Input should be >= 50");
    expect(detail).not.toContain("query");
  });

  it("joins several failures rather than reporting only the first", async () => {
    const detail = await detailFor({
      detail: [
        { loc: ["body", "top_k"], msg: "too large" },
        { loc: ["body", "question"], msg: "too short" },
      ],
    });

    expect(detail).toBe("top_k: too large; question: too short");
  });

  it("falls back to a count when the shape is not recognised", async () => {
    // Still better than nothing: the user learns the request was malformed.
    expect(await detailFor({ detail: [{ unexpected: true }] })).toBe(
      "1 validation error(s)",
    );
  });

  it("keeps a plain string detail as it is", async () => {
    expect(await detailFor({ detail: "Corpus has no index yet." })).toBe(
      "Corpus has no index yet.",
    );
  });
});
