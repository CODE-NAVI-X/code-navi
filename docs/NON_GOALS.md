# NON-GOALS (FROZEN)

Amend only by explicit user decision. Record amendments in the changelog at the bottom.

The Code-Navi kernel is a minimal, platform-agnostic agent runtime for the first host, code-navi CLI.

- No UI ownership. CLI interaction design, Web UI, DingTalk/Lark/Telegram rendering, confirmations, buttons, cards, forms, and platform flows belong to hosts.
- No prompt or content ownership. Prompt templates, role prompts, workflow wording, and domain content belong to skills, workflows, hosts, or business packages.
- No business logic. Code navigation, teaching, research, ticket handling, approval, and other domain rules belong above the kernel.
- No eval harness in core. Benchmarks, scoring, regression harnesses, dataset loaders, and evaluation protocols may consume kernel traces but are not kernel runtime.
- No vector store or RAG implementation in core. Retrievers, embeddings, rerankers, vector databases, indexing, and RAG selection live outside core, though retrieved context may enter through tools or context sources.
- No multi-agent orchestration in v1 core. Scheduling, roles, agent-to-agent protocols, debate, voting, decomposition, and aggregation belong to orchestrators; v1 may keep run_id and parent_run_id.
- No plugin auto-discovery. Tools, providers, context sources, storage backends, and extensions must be explicitly registered by the host or package layer.
- No config file format ownership. Kernel may define KernelConfig, but hosts read YAML, TOML, JSON, INI, env files, CLI flags, or remote config and pass parsed objects.

Gate test:
- Add streaming token callbacks: IN if represented as ProviderStreamEvent through the provider interface, OUT if tied to a provider-native stream format.
- Add a memory/RAG layer: OUT for core retriever/vector store/ranking, IN only as an explicitly registered tool or context source.
- Support YAML config: OUT for core parsing or file format rules, IN only when host parses YAML into KernelConfig.

Changelog: 2026-07-08 initial freeze.
