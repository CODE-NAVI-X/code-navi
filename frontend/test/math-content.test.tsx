import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MathContent } from "@/components/learning/MathContent";

describe("MathContent", () => {
  it("renders inline and bare LaTeX formulas with KaTeX classes", () => {
    const raw = "从数学形式看，卷积层第k个输出通道在位置(i,j)的响应为: y_{i,j,k} = \\sigma(\\sum_{c}\\sum_{u,v} w_{u,v,c,k} \\cdot x_{i+u,j+v,c} + b_k)，其中w为滤波器权重，b为偏置，\\sigma为非线性函数。";
    const { container } = render(<MathContent text={raw} />);

    expect(screen.getByText(/从数学形式看/)).toBeInTheDocument();
    expect(screen.getByText(/其中w为滤波器权重/)).toBeInTheDocument();
    // KaTeX outputs elements with class "katex"
    const katexElements = container.querySelectorAll(".katex");
    expect(katexElements.length).toBeGreaterThan(0);
  });

  it("renders explicit $...$ and $$...$$ math delimiters", () => {
    const raw = "欧拉公式: $e^{i\\pi} + 1 = 0$ 以及高斯积分: $$\\int_{-\\infty}^{\\infty} e^{-x^2} dx = \\sqrt{\\pi}$$";
    const { container } = render(<MathContent text={raw} />);

    const katexElements = container.querySelectorAll(".katex");
    expect(katexElements.length).toBe(2);
  });
});
