# Decision records

Short records of the main design choices: the context, the decision, its consequences, and the evidence behind it. The pull requests they cite are this repository's merged milestones (#2 to #9).

| # | Decision | In short |
|---|---|---|
| [0001](0001-openai-compatible-model-layer.md) | OpenAI-compatible model layer only | One small package talks to any Chat Completions endpoint; nothing else imports a model SDK. |
| [0002](0002-gated-disclosure-with-verified-quotes.md) | Gated disclosure with verified quotes, not RAG | A gate that never sees the secrets decides what a question has earned; code checks its evidence. |
| [0003](0003-grounded-coach.md) | Grounded coach: analysis, model, code checks | Code computes the facts of the interview; the coach writes from them; code checks what it wrote. |
| [0004](0004-yaml-content-with-validation-and-hot-reload.md) | YAML content with validation and hot reload | Faculty edit plain files; strict validation names the file and field; a bad edit never takes the app down. |
| [0005](0005-one-default-model.md) | One default model; the swap is optional | `qwen3.5:9b` plays every role, so nothing swaps on a 16 GB GPU; a bigger coach is opt-in and experimental. |
| [0006](0006-no-login-no-database.md) | No login and no database | Sessions live in memory, the student keeps a Markdown export, and telemetry holds no message text. |
| [0007](0007-bilingual-ui-arabic-experimental.md) | Bilingual UI; Arabic conversations experimental | Every screen works in English and Arabic; the models' Arabic is labelled experimental, with its known issues. |
| [0008](0008-evaluation-fixed-judge-paired-replays.md) | Evaluation with a fixed judge and paired replays | One judge for every setup, and prompt changes measured on the same recorded interviews. |
