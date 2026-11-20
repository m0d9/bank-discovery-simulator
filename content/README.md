# Adding a client: a guide for faculty

Each client is a YAML file in `content/clients/`, and each product one in `content/products/`, editable without code. Write one `name: value` per line, indent with spaces (never tabs), and start comments with `#`.

## 1. What's in a client file

| Part | Who sees it | What it holds |
|---|---|---|
| `card` | Students, on the client list | Name, headline, the client's first words |
| `persona` | The AI client, who plays it | Who the client is and how they talk |
| `open_facts` | Anyone who asks | What the client tells anyone |
| `hidden_facts` | Students who ask the right questions | What the student has to earn |
| `needs` | Students, after the interview | The answer key |
| `coach_notes` | Only the AI coach | Key questions, common mistakes |

After the wrap-up, the feedback page shows everything but the coach notes. Keep hidden facts out of `persona` and `open_facts`, or the client may share them too early.

## 2. How disclosure works

Hidden facts start locked. After each student message, an AI "gate" checks it against each fact's `unlock_when`, without ever seeing the facts.

- `unlock_when`: what the student must ask, one per line: "asks…" or "follows up on her remark that…".
- `signal` (optional): a vague hint the client may drop once while the fact is locked.
- `requires` (optional): facts that must unlock first.
- `unlock_on_product_pitch` (optional): the products the fact rules out. Proposing one makes the client reveal the fact. If it came out earlier, the product's feedback card says «كانت المقابلة قد كشفت ما يستبعد هذا المنتج» ("The client had already said something that rules this out"), provided a need lists the product as unsuitable.
- `example_questions`: one to three questions that should unlock the fact. Test runs ask the first.

**Writing `unlock_when`:** ✓ "asks how quickly her customers pay"; ✗ "asks a relevant question".

- **Name a specific topic, not a mood or a theme.** After a pitch, Noura's "…or money worries" let "What would worry you about it?" unlock `late-payments` (3 of 3). "…or difficulty covering salaries or suppliers" cut that to 1 in 12.
- **Describe the student's question, not the client's situation.** The gate over-unlocks after a pitch: "…for when cash is short" unlocked `late-payments` in 2 of 3 runs, though it asked nothing.
- **Hints make the follow-up easier, by design.** After Khalid says "We've had to turn down some work", even "Do you need any financing?" counts as a follow-up and unlocks his trucks; asked cold, it unlocks nothing. So hard clients should drop hints sparingly.
- **Match the difficulty.** A hard client gets no line a general question would match, such as "asks what the company would need financing for".

## 3. Writing the answer key

Each need has a `description`, `evidence_facts` (the facts that reveal it, which must all unlock), `suitable_products` (file names without `.yaml`) and `unsuitable_products`, each with a `reason` a banker would accept. A recommendation is **unsuitable** if any need lists it so, else **suitable** if any need does, else "not in the answer key". If nothing fits, set `no_catalogue_fit: true`, leave `suitable_products: []`, and say in `referral_note` where to refer the client.

## 4. Step by step

1. Copy `content/_templates/client.yaml` to `content/clients/<id>.yaml`, where `<id>` is its `id`.
2. Replace every value; the comments explain each field.
3. Run `make validate-content`. It prints `✓ 8 products, 6 clients`, or each problem (section 6).
4. Run `make chat CLIENT=<id> DEBUG=1` (`scripts/chat.py --client <id> --debug`). Ask a general question, then each fact's first example question, and read what `unlocked this turn` shows.
5. Commit the file, or send it to whoever maintains the app.

**Products** work the same way, from `content/_templates/product.yaml`. Under `aliases`, list other names that identify the product unmistakably, such as "Murabaha" or «مرابحة», but no everyday words like "overdraft". The coach's suggested questions must not name products, aliases included.

## 5. Languages

The interface is fully bilingual; Arabic conversations are experimental.

**Give Arabic** (`ar` beside `en`) for the card, need descriptions, unsuitable reasons, the referral note and product fields. Otherwise the Arabic page shows English, and `make test` fails. The terms:

- Conventional products charge «فائدة» and lend with a «قرض»; call them «قائم على الفائدة».
- Islamic products pay «ربح» or charge «أجرة», never «فائدة»; call them «متوافق مع الشريعة».
- Write Western digits with «ريال قطري», as in «نحو 50,000 ريال قطري».
- Mark fictional prices "(fictional)" and «(أرقام افتراضية)».

**`gender`** decides how the coach refers to the client in Arabic: «العميلة» or «العميل».

**Keep in English:** persona, open facts, hidden facts, signals, `unlock_when`, example questions and coach notes. They are inputs to the AI models, and the client still replies in the student's language.

## 6. Common validation errors

Each message names the file and the field, as in `x.yaml › persona.gender: Field required`.

| Message | Fix |
|---|---|
| `must match the file name` | Make the `id` and the file name the same. |
| `unknown product`, `unknown hidden fact` | Use an existing product file name or fact id. |
| `Extra inputs are not permitted` | A misspelt field name: copy it from the template. |
| `Field required` | Add the missing field, such as `gender: female`. |
| `circular requirement` | Two facts require each other: remove one `requires`. |
| `must have importance: critical` | Mark the most important fact `critical`. |
| `list at least one product` | Add a suitable product, or see section 3. |
| `expected <block end>`, `found character '\t'` | Indent with spaces, aligned with the lines around it. |
| `Settings are missing or invalid` | Copy `.env.example` to `.env`. |
