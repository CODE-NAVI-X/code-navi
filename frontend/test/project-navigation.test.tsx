import { createElement, type ReactNode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ProjectCodeNavigationPage from "@/app/(student)/learning/projects/page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams("project_id=project-1"),
}));

vi.mock("next/link", () => ({
  default: ({ children, ...props }: { children?: ReactNode; href: string }) =>
    createElement("a", props, children),
}));

const project = {
  project_id: "project-1",
  name: "navigation-demo",
  files: [
    {
      path: "src/model.py",
      kind: "python" as const,
      size: 600,
      symbols: [
        {
          kind: "function" as const,
          name: "target_function",
          line: 40,
          signature: "def target_function():",
          docstring_summary: "",
        },
      ],
    },
    {
      path: "README.md",
      kind: "markdown" as const,
      size: 14,
      symbols: [],
    },
  ],
  metrics: { files: 2, bytes: 614, lines: 40 },
};

const modelContent = Array.from({ length: 40 }, (_, index) =>
  index === 39 ? "def target_function():" : `line ${index + 1}`,
).join("\n");

function jsonResponse(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as Response;
}

describe("project code navigation", () => {
  const originalScrollIntoView = Element.prototype.scrollIntoView;
  let scrollIntoView: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    scrollIntoView = vi.fn();
    Object.defineProperty(Element.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/v1/practice/projects/project-1")) {
          return jsonResponse(project);
        }
        if (url.endsWith("/api/v1/practice/projects/project-1/files/src/model.py")) {
          return jsonResponse({
            project_id: project.project_id,
            path: "src/model.py",
            content: modelContent,
            symbols: project.files[0].symbols,
          });
        }
        if (url.endsWith("/api/v1/practice/projects/project-1/files/README.md")) {
          return jsonResponse({
            project_id: project.project_id,
            path: "README.md",
            content: "README content",
            symbols: [],
          });
        }
        throw new Error(`Unexpected request: ${url}`);
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    Object.defineProperty(Element.prototype, "scrollIntoView", {
      configurable: true,
      value: originalScrollIntoView,
    });
  });

  it("scrolls and highlights a symbol after its file content loads", async () => {
    render(<ProjectCodeNavigationPage />);

    const symbol = await screen.findByRole("button", { name: /target_function/ });
    fireEvent.click(symbol);

    await waitFor(() => {
      const targetLine = document.querySelector('[data-line-number="40"]');
      expect(targetLine).toHaveAttribute("aria-current", "location");
      expect(targetLine).toHaveClass("bg-amber-500/25");
      expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "center" });
    });
  });

  it("clears the previous symbol target when a normal file is selected", async () => {
    render(<ProjectCodeNavigationPage />);

    fireEvent.click(await screen.findByRole("button", { name: /target_function/ }));
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledTimes(1));
    const callsBeforeNormalFile = scrollIntoView.mock.calls.length;

    fireEvent.click(screen.getByRole("button", { name: "README.md" }));

    await waitFor(() => {
      expect(screen.getByText(/README content/)).toBeInTheDocument();
      expect(document.querySelector('[aria-current="location"]')).toBeNull();
      expect(scrollIntoView).toHaveBeenCalledTimes(callsBeforeNormalFile);
    });
  });
});
