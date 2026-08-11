import { useQuery } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Providers } from "./providers";

function Consumer() {
  const { data } = useQuery({
    queryKey: ["smoke"],
    queryFn: () => Promise.resolve("resolved"),
  });
  return <span>{data ?? "pending"}</span>;
}

describe("Providers", () => {
  it("renders children", () => {
    render(
      <Providers>
        <p>child</p>
      </Providers>,
    );
    expect(screen.getByText("child")).toBeInTheDocument();
  });

  it("supplies a QueryClient to descendants", async () => {
    // useQuery throws without a provider, so resolving proves the wiring.
    render(
      <Providers>
        <Consumer />
      </Providers>,
    );
    expect(await screen.findByText("resolved")).toBeInTheDocument();
  });
});
