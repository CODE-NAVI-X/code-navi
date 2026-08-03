import type { Metadata } from "next";

import { ResearchConversation } from "@/components/research/ResearchConversation";

export const metadata: Metadata = {
  title: "科研方向对话助手 | Code Navi",
  description: "通过自然多轮对话逐步明确研究方向、候选问题与信息缺口。",
};

export default function ResearchPage() {
  return <ResearchConversation />;
}
