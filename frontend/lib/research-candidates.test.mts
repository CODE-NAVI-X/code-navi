import assert from "node:assert/strict";
import test from "node:test";

import {
  resolveEffectiveCandidates,
  shouldRefreshSearchCandidates,
  shouldShowSearchCandidates,
} from "./research-candidates.ts";

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
