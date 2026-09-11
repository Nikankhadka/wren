import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ConfirmDialog } from "./ConfirmDialog";

function dialog(overrides: Partial<Parameters<typeof ConfirmDialog>[0]> = {}) {
  return renderToStaticMarkup(
    <ConfirmDialog
      open
      title="Remove the Sunday special?"
      description="Customers will no longer see it on your page."
      confirmLabel="Remove"
      onCancel={() => {}}
      onConfirm={() => {}}
      {...overrides}
    />,
  );
}

describe("ConfirmDialog", () => {
  it("renders the title, description and labels inside a dialog", () => {
    const html = dialog();
    expect(html).toContain('role="dialog"');
    expect(html).toContain("Remove the Sunday special?");
    expect(html).toContain("Customers will no longer see it on your page.");
    expect(html).toContain(">Remove</span>");
    expect(html).toContain(">Cancel</span>");
    expect(html).toContain('data-testid="confirm-accept"');
  });

  it("renders a destructive accept for the danger tone, primary otherwise", () => {
    expect(dialog({ tone: "danger" })).toContain("bg-danger");
    expect(dialog()).toContain("bg-brand");
    expect(dialog({ tone: "danger" })).not.toContain("bg-brand");
  });

  it("disables both buttons and marks the dialog busy while working", () => {
    const html = dialog({ working: true });
    expect(html).toContain('aria-busy="true"');
    // Accept is loading (disabled with a spinner), cancel is plain disabled.
    const disabledCount = html.split("disabled").length - 1;
    expect(disabledCount).toBeGreaterThanOrEqual(2);
  });

  it("honours a custom cancel label", () => {
    expect(dialog({ cancelLabel: "Keep it" })).toContain(">Keep it</span>");
  });

  it("renders nothing at all while closed", () => {
    // No mounted shell, no empty heading, no stray testids - so
    // `confirm-accept` is unique while open even with one hook per layout,
    // page, and sheet on the same screen.
    expect(dialog({ open: false })).toBe("");
  });
});
