import assert from "node:assert/strict";
import test from "node:test";

import {
  filterDisplayableEnglishCandidates,
  isDisplayableEnglishTitle,
  resolveEffectiveCandidates,
  shouldRefreshSearchCandidates,
  shouldShowSearchCandidates,
} from "./research-candidates.ts";

test("isDisplayableEnglishTitle qualification rules", () => {
  // Pure Chinese titles: excluded
  assert.equal(isDisplayableEnglishTitle("基于卷积神经网络的图像分类研究"), false);
  assert.equal(isDisplayableEnglishTitle("图数据库的分布式查询优化"), false);

  // Mixed Chinese-majority titles: excluded
  assert.equal(isDisplayableEnglishTitle("基于CNN与深度学习的SQL注入检测方法"), false);

  // Empty / null / whitespace: excluded
  assert.equal(isDisplayableEnglishTitle(""), false);
  assert.equal(isDisplayableEnglishTitle("   "), false);
  assert.equal(isDisplayableEnglishTitle(null), false);
  assert.equal(isDisplayableEnglishTitle(undefined), false);

  // Normal English titles: retained
  assert.equal(
    isDisplayableEnglishTitle("Semi-Supervised Classification with Graph Convolutional Networks"),
    true,
  );
  assert.equal(
    isDisplayableEnglishTitle("Deep Residual Learning for Image Recognition"),
    true,
  );

  // English titles with abbreviations, formulas, or author names: retained
  assert.equal(isDisplayableEnglishTitle("GATv2: Graph Attention Networks Reloaded"), true);
  assert.equal(
    isDisplayableEnglishTitle("Graph Convolutional Networks (Kipf and Welling, 2016)"),
    true,
  );
  assert.equal(
    isDisplayableEnglishTitle("A $p$-Laplacian Approach for Semi-Supervised Learning on Graphs"),
    true,
  );
  assert.equal(
    isDisplayableEnglishTitle("CNN-Based SQL Injection Detection with TextCNN"),
    true,
  );

  // Symbols/numbers only: excluded
  assert.equal(isDisplayableEnglishTitle("$123 + 456 = 579$"), false);
  assert.equal(isDisplayableEnglishTitle("(1998)"), false);
});

test("legacy bundles with Chinese candidate papers are filtered from display and selection", () => {
  const mixedCandidates = [
    { title: "基于卷积神经网络的图像分类研究", url: "https://arxiv.org/abs/2301.00001" },
    {
      title: "Semi-Supervised Classification with Graph Convolutional Networks",
      url: "https://arxiv.org/abs/1609.02907",
    },
    { title: "基于CNN与深度学习的SQL注入检测方法", url: "https://arxiv.org/abs/2303.00001" },
  ];

  const onlyChineseCandidates = [
    { title: "基于卷积神经网络的图像分类研究", url: "https://arxiv.org/abs/2301.00001" },
  ];

  // filterDisplayableEnglishCandidates filters out non-English
  const filtered = filterDisplayableEnglishCandidates(mixedCandidates);
  assert.equal(filtered.length, 1);
  assert.equal(
    filtered[0]?.title,
    "Semi-Supervised Classification with Graph Convolutional Networks",
  );

  // resolveEffectiveCandidates removes Chinese candidates
  const effective = resolveEffectiveCandidates(mixedCandidates, null);
  assert.equal(effective.length, 1);
  assert.equal(
    effective[0]?.title,
    "Semi-Supervised Classification with Graph Convolutional Networks",
  );

  // shouldShowSearchCandidates returns false when only Chinese candidates are present
  assert.equal(shouldShowSearchCandidates(onlyChineseCandidates, null), false);
  assert.equal(shouldShowSearchCandidates(mixedCandidates, null), true);
});


test("without current_paper, real search candidate cards are visible", () => {
  const candidates = [
    { title: "Paper 1", url: "https://arxiv.org/abs/1234.5678" },
    { title: "Paper 2", url: "https://arxiv.org/abs/2345.6789" },
  ];

  assert.equal(shouldShowSearchCandidates(candidates, null), true);
  assert.equal(
    shouldShowSearchCandidates(candidates, { current_paper: null, paper_history: [] }),
    true,
  );
  assert.equal(shouldRefreshSearchCandidates(null), true);
  assert.equal(
    shouldRefreshSearchCandidates({ current_paper: null, paper_history: [] }),
    true,
  );
  assert.deepEqual(resolveEffectiveCandidates(candidates, null), candidates);
});

test("when current_paper exists, candidate cards are hidden and suppressed", () => {
  const candidates = [
    { title: "Paper 1", url: "https://arxiv.org/abs/1234.5678" },
  ];
  const papers = {
    current_paper: {
      paper_id: "p1",
      title: "Paper 1",
      purpose: "replication_target",
    },
    paper_history: [],
  };

  assert.equal(shouldShowSearchCandidates(candidates, papers), false);
  assert.equal(shouldRefreshSearchCandidates(papers), false);
  assert.deepEqual(resolveEffectiveCandidates(candidates, papers), []);
});

test("after paper confirmation, incoming evidence bundle refresh does not re-display old candidates", () => {
  const papersWithSelectedPaper = {
    current_paper: {
      paper_id: "p-gcn",
      title: "Semi-Supervised Classification with Graph Convolutional Networks",
      purpose: "replication_target",
    },
    paper_history: [],
  };

  // Even if a subsequent turn fetches a newly indexed evidence bundle with 5 candidate papers:
  const newBundlePapers = [
    { title: "Candidate 1", url: "https://arxiv.org/abs/1111.1111" },
    { title: "Candidate 2", url: "https://arxiv.org/abs/2222.2222" },
  ];

  // Refresh must be skipped / gated
  assert.equal(shouldRefreshSearchCandidates(papersWithSelectedPaper), false);

  // Resolved candidates must be empty
  const effective = resolveEffectiveCandidates(newBundlePapers, papersWithSelectedPaper);
  assert.deepEqual(effective, []);

  // UI render condition must be false
  assert.equal(shouldShowSearchCandidates(effective, papersWithSelectedPaper), false);
  assert.equal(shouldShowSearchCandidates(newBundlePapers, papersWithSelectedPaper), false);
});

test("compare/cite history does not alter candidate card suppression when current_paper exists", () => {
  const papersWithCompareAndCiteHistory = {
    current_paper: {
      paper_id: "p-main",
      title: "Main Paper",
      purpose: "replication_target",
    },
    paper_history: [
      {
        paper_id: "p-comp",
        title: "Baseline Paper to Compare",
        purpose: "baseline_comparison",
      },
      {
        paper_id: "p-cite",
        title: "Related Work Paper to Cite",
        purpose: "citation_context",
      },
    ],
  };

  const candidates = [
    { title: "Old Candidate 1", url: "https://arxiv.org/abs/3333.3333" },
  ];

  assert.equal(
    shouldShowSearchCandidates(candidates, papersWithCompareAndCiteHistory),
    false,
  );
  assert.equal(
    shouldRefreshSearchCandidates(papersWithCompareAndCiteHistory),
    false,
  );
  assert.deepEqual(
    resolveEffectiveCandidates(candidates, papersWithCompareAndCiteHistory),
    [],
  );
});
