import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { Composer } from "./Composer";

describe("Composer", () => {
  test("disables submit while blank or busy", () => {
    const onSubmit = vi.fn();
    const { rerender } = render(
      <Composer busy={false} draft="   " onChange={vi.fn()} onSubmit={onSubmit} />,
    );

    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();

    rerender(
      <Composer busy draft="Check FSI" onChange={vi.fn()} onSubmit={onSubmit} />,
    );

    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
  });

  test("submits the draft with the button and Enter key", () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <Composer busy={false} draft="Check Baner site" onChange={vi.fn()} onSubmit={onSubmit} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter" });

    expect(onSubmit).toHaveBeenNthCalledWith(1, "Check Baner site");
    expect(onSubmit).toHaveBeenNthCalledWith(2, "Check Baner site");
  });

  test("does not submit when Enter is used with Shift", () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <Composer busy={false} draft="Line one" onChange={vi.fn()} onSubmit={onSubmit} />,
    );

    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter", shiftKey: true });

    expect(onSubmit).not.toHaveBeenCalled();
  });

  test("reports draft changes", () => {
    const onChange = vi.fn();
    render(
      <Composer busy={false} draft="" onChange={onChange} onSubmit={vi.fn()} />,
    );

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "Survey No. 45/2, Baner" },
    });

    expect(onChange).toHaveBeenCalledWith("Survey No. 45/2, Baner");
  });

  test("shows Stop for a cancellable Live Turn", () => {
    const onStop = vi.fn().mockResolvedValue(undefined);
    render(
      <Composer
        busy
        canStop
        draft="Check Baner site"
        isStopping={false}
        onChange={vi.fn()}
        onStop={onStop}
        onSubmit={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Stop generating" }));

    expect(onStop).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "Send message" })).toBeNull();
  });
});
