# Demo script (about 4 minutes)

A walkthrough to record. Each step gives what to click and what to say.

**It covers:**
- the whole flow;
- a hidden fact being unlocked;
- the feedback page;
- the switch to Arabic;
- a live edit of a client's YAML file.

The interview lines are the ones used for the [sample interview](../samples/noura-al-kuwari-en.md). The client model varies, so her replies will differ a little.

## Before you record

1. **Start the app** with `make dev` and Ollama running, then open http://localhost:5173 in a 1440 px wide window.
2. **Warm the model.** Start a throwaway interview and send one message, because the first reply after a cold start takes several seconds.
3. **Open a terminal** at the repo root and start this. It prints each turn's unlocked fact ids, which is all the event log holds (no text):
   ```bash
   tail -n 0 -f data/events.jsonl | python3 -u -c "import sys, json; [print('turn', e['student_turn_no'], 'unlocked:', e['unlocked']) for e in map(json.loads, sys.stdin) if e['event'] == 'turn']"
   ```
4. **Open `content/clients/noura-al-kuwari.yaml`** in an editor.
5. **Keep the student lines below** ready to paste.

## The script

| Time | Click or type | Say |
|---|---|---|
| 0:00 | The client list. | "This is a practice tool for business students. They interview an AI bank client, recommend products, and get feedback from an AI coach. It runs on a free, open model on this laptop." |
| 0:15 | Point at the five cards, then **Start interview with Noura Al-Kuwari**. | "Each client is a YAML file: a persona, open facts, hidden facts the student has to earn, and an answer key. Noura runs a catering company. She opens vaguely, as real clients do." |
| 0:35 | Type: *Hello Noura, thank you for making the time. Could you tell me a little about your catering business?* | "She answers from her open facts: the company, the staff, how she started." |
| 0:50 | Type: *How do your customers usually pay you, and how quickly do the payments come in?* Point at the terminal: `unlocked: ['late-payments']`. | "That question earned a hidden fact. A separate gate model checked my message against the fact's unlock conditions. It never saw the fact itself, and it had to quote the condition it matched, which code verified. Only now does the client model receive the fact, so she tells me about the late government payments." |
| 1:25 | Type: *Looking ahead, are there any big contracts or growth plans coming up?* (`unlocked: ['big-contract']`) | "This fact could only unlock after the first one: facts can depend on each other." |
| 1:40 | Open the **Product catalogue**. Type: *For the slow payers, we have a Business Collect Account: your customers can pay by payment link and it sends them automatic reminders. Would something like that help?* | "Students can discuss products. The client now knows what that product does, and reacts to it." |
| 2:00 | **End interview**, then confirm. Write a short summary. Recommend **Business Collect Account** and **Invoice Advance**, each with a reason. **Submit wrap-up**. | "I'm making a typical mistake: I never asked about her banking preferences, and Invoice Advance is interest-based." |
| 2:20 | The feedback page. Wait about 10 s while the coach writes. | "First, code compares the interview with the answer key. Then the coach model writes from that analysis and the transcript." |
| 2:35 | Scroll: the counts, **What went well**, then click one of its **Turn** links. | "Every point cites my turns, and the link opens that message in the transcript." |
| 2:50 | **What was missed**, then the recommendations. | "I never found her Sharia preference, and the answer key marks Invoice Advance unsuitable. That verdict and the discovery map come from code, not the model. The page says the coach can make mistakes, and the evaluation measured it: about 7% of its points are unsupported." |
| 3:10 | **العربية** in the header. | "The whole interface works in Arabic, right to left. The coach writes its feedback again in Arabic. Arabic conversations are marked experimental, because the models' grammatical gender isn't reliable yet." |
| 3:30 | The editor: change Noura's `headline` (`en`), for example add "and school canteens", and save. Back in the browser, go to the client list and reload. | "Faculty edit content in YAML, with no code. The running app picked up the change within about 2 seconds." |
| 3:45 | Terminal: `make validate-content` prints `✓ 8 products, 5 clients`. | "One command checks every file, and an error names the file and the field. The guide in `content/README.md` shows how to write a new client from a template." |
| 3:55 | Undo the edit (`git checkout content/clients/noura-al-kuwari.yaml`). | "The evaluation, the architecture and the design decisions are in the repository. Thank you." |

**If a reply surprises you,** carry on. The point is the flow. If the gate doesn't unlock `late-payments` on the first try, ask the next example question from Noura's file: *Have you ever struggled to cover salaries or suppliers?*
