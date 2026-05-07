import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ArtifactFrame } from "../../src/components/ArtifactFrame";

describe("ArtifactFrame", () => {
  it("renders the empty placeholder when artifact is null", () => {
    render(<ArtifactFrame artifact={null} />);
    expect(
      screen.getByText(/no chart yet/i),
    ).toBeInTheDocument();
    expect(screen.queryByTitle("Generated chart")).not.toBeInTheDocument();
  });

  it("renders an iframe with the absolute artifact URL when artifact is plotly_html", () => {
    render(
      <ArtifactFrame
        artifact={{
          artifact_id: "abc",
          url: "/artifacts/abc",
          type: "plotly_html",
        }}
      />,
    );
    const iframe = screen.getByTitle("Generated chart") as HTMLIFrameElement;
    expect(iframe).toBeInTheDocument();
    expect(iframe.getAttribute("src")).toBe("http://localhost:8000/artifacts/abc");
  });

  it("renders the iframe with sandbox='allow-scripts' and NOT allow-same-origin", () => {
    render(
      <ArtifactFrame
        artifact={{
          artifact_id: "abc",
          url: "/artifacts/abc",
          type: "plotly_html",
        }}
      />,
    );
    const iframe = screen.getByTitle("Generated chart");
    // Load-bearing for FR-021 / SC-009: the sandbox attribute must be exactly
    // "allow-scripts". Widening this in a future refactor should fail this test.
    expect(iframe.getAttribute("sandbox")).toBe("allow-scripts");
    const sandbox = iframe.getAttribute("sandbox") ?? "";
    expect(sandbox).not.toContain("allow-same-origin");
    expect(sandbox).not.toContain("allow-forms");
    expect(sandbox).not.toContain("allow-popups");
  });

  it("renders the empty placeholder for an unknown artifact type", () => {
    render(
      <ArtifactFrame
        artifact={
          {
            artifact_id: "abc",
            url: "/artifacts/abc",
            type: "unknown_type",
          } as never
        }
      />,
    );
    expect(screen.getByText(/no chart yet/i)).toBeInTheDocument();
    expect(screen.queryByTitle("Generated chart")).not.toBeInTheDocument();
  });
});
