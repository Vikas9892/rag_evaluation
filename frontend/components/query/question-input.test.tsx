import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { QuestionInput } from "./question-input";

const noSuggestions: string[] = [];

describe("QuestionInput", () => {
  it("submits the typed question", async () => {
    const onSubmit = vi.fn();
    render(<QuestionInput suggestions={noSuggestions} onSubmit={onSubmit} />);

    await userEvent.type(
      screen.getByRole("combobox", { name: "Question" }),
      "what is ACID",
    );
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));

    expect(onSubmit).toHaveBeenCalledWith("what is ACID");
  });

  it("submits on Enter", async () => {
    const onSubmit = vi.fn();
    render(<QuestionInput suggestions={noSuggestions} onSubmit={onSubmit} />);

    await userEvent.type(
      screen.getByRole("combobox", { name: "Question" }),
      "what is a deadlock{Enter}",
    );

    expect(onSubmit).toHaveBeenCalledWith("what is a deadlock");
  });

  it("trims before submitting", async () => {
    const onSubmit = vi.fn();
    render(<QuestionInput suggestions={noSuggestions} onSubmit={onSubmit} />);

    await userEvent.type(
      screen.getByRole("combobox", { name: "Question" }),
      "  padded  ",
    );
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));

    expect(onSubmit).toHaveBeenCalledWith("padded");
  });

  it("refuses to submit a whitespace-only question", async () => {
    // The API answers this with a 400, so the round trip is pure waste.
    const onSubmit = vi.fn();
    render(<QuestionInput suggestions={noSuggestions} onSubmit={onSubmit} />);

    await userEvent.type(
      screen.getByRole("combobox", { name: "Question" }),
      "   {Enter}",
    );

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("disables Ask until there is something to ask", async () => {
    render(<QuestionInput suggestions={noSuggestions} onSubmit={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();

    await userEvent.type(screen.getByRole("combobox", { name: "Question" }), "x");
    expect(screen.getByRole("button", { name: "Ask" })).toBeEnabled();
  });

  it("seeds the draft from the URL question", () => {
    render(
      <QuestionInput
        defaultValue="from the url"
        suggestions={noSuggestions}
        onSubmit={vi.fn()}
      />,
    );
    expect(screen.getByRole("combobox", { name: "Question" })).toHaveValue(
      "from the url",
    );
  });

  it("does not resubmit while a request is in flight", async () => {
    const onSubmit = vi.fn();
    render(
      <QuestionInput
        defaultValue="pending one"
        suggestions={noSuggestions}
        isPending
        onSubmit={onSubmit}
      />,
    );

    expect(screen.getByRole("button", { name: /ask/i })).toBeDisabled();
    await userEvent.type(screen.getByRole("combobox", { name: "Question" }), "{Enter}");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  describe("clear", () => {
    it("appears only once there is text", async () => {
      render(<QuestionInput suggestions={noSuggestions} onSubmit={vi.fn()} />);
      expect(
        screen.queryByRole("button", { name: "Clear question" }),
      ).not.toBeInTheDocument();

      await userEvent.type(screen.getByRole("combobox", { name: "Question" }), "x");
      expect(screen.getByRole("button", { name: "Clear question" })).toBeInTheDocument();
    });

    it("empties the input", async () => {
      render(
        <QuestionInput
          defaultValue="remove me"
          suggestions={noSuggestions}
          onSubmit={vi.fn()}
        />,
      );

      await userEvent.click(screen.getByRole("button", { name: "Clear question" }));

      expect(screen.getByRole("combobox", { name: "Question" })).toHaveValue("");
    });

    it("does not submit", async () => {
      // A clear button of type="submit" inside a form would ask the question.
      const onSubmit = vi.fn();
      render(
        <QuestionInput
          defaultValue="remove me"
          suggestions={noSuggestions}
          onSubmit={onSubmit}
        />,
      );

      await userEvent.click(screen.getByRole("button", { name: "Clear question" }));

      expect(onSubmit).not.toHaveBeenCalled();
    });
  });

  describe("suggestions", () => {
    it("offers a matching past question", async () => {
      render(
        <QuestionInput
          suggestions={["what is ACID", "what is a deadlock", "explain paging"]}
          onSubmit={vi.fn()}
        />,
      );

      await userEvent.type(screen.getByRole("combobox", { name: "Question" }), "deadl");

      expect(
        await screen.findByRole("option", { name: "what is a deadlock" }),
      ).toBeVisible();
      expect(
        screen.queryByRole("option", { name: "explain paging" }),
      ).not.toBeInTheDocument();
    });

    it("fills the input when a suggestion is chosen", async () => {
      const onSubmit = vi.fn();
      render(<QuestionInput suggestions={["what is ACID"]} onSubmit={onSubmit} />);

      await userEvent.type(screen.getByRole("combobox", { name: "Question" }), "ACI");
      await userEvent.click(await screen.findByRole("option", { name: "what is ACID" }));

      expect(screen.getByRole("combobox", { name: "Question" })).toHaveValue(
        "what is ACID",
      );
    });

    it("shows no list at all when there is no history", async () => {
      // An empty popup announcing itself on every keystroke is worse than none.
      render(<QuestionInput suggestions={noSuggestions} onSubmit={vi.fn()} />);

      await userEvent.type(
        screen.getByRole("combobox", { name: "Question" }),
        "anything",
      );

      expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    });
  });
});
