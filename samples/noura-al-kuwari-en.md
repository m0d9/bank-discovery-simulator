# Sample interview: Noura Al-Kuwari, in English

A real interview, run against the app's HTTP API (the same endpoints the web page calls) and then exported with the app's own Markdown export: the file that "Download transcript (.md)" on the feedback page gives you. **Everything below the line is that export, unedited.**

| | |
|---|---|
| Date | 2026-11-21 |
| App | commit `85f6f88` |
| Models | `qwen3.5:9b` as the disclosure gate, the AI client and the AI coach (the default), on Ollama 0.40.16 with a 16,384-token context |
| Prompt versions | `gate` `33c3381c` · `client_system` `239b94f7` · `client_reminder` `235e4fb9` · `client_language` `449ba984` · `coach` `e52bc479` (the first 8 characters of each prompt file's SHA-256, as the app records them) |
| The student | A reasonable but imperfect interview, typed one message at a time after reading each reply. Two hidden facts are earned with good questions and one product is discussed. The student never asks about banking preferences, so the critical Sharia preference stays hidden, and an interest-based product is recommended. |

**One thing to notice.** The coach's second "What was missed" point says Noura "had already indicated she only uses Sharia-compliant products". She hadn't: that fact stayed locked (see "Hidden facts" near the end: *Not found*). It is the kind of unsupported claim the [evaluation](../docs/evaluation.md) measures (4 of 59 points with these models and prompts), and the reason the page and the export say the coach can make mistakes. The discovery map and the verdicts come from code and the answer key, not from the coach.

---

# Interview with Noura Al-Kuwari

- **Client:** Noura Al-Kuwari – Owner of a Doha catering company for weddings and corporate events
- **Date:** 2026-11-21
- **Models:** AI client `qwen3.5:9b` · Disclosure gate `qwen3.5:9b` · AI coach `qwen3.5:9b`

## Transcript

**Turn 0 · Noura Al-Kuwari:** Hello. I don't have long, but a friend said I should talk to you about better banking for my business.

**Turn 1 · You:** Hello Noura, thank you for making the time. Could you tell me a little about your catering business?

**Turn 2 · Noura Al-Kuwari:** Thank you. My name is Noura Al-Kuwari and I own a catering company in Doha that now has 14 staff serving weddings and corporate events. We started with family gatherings back in 2019 and have grown quite a bit since then.

**Turn 3 · You:** That is impressive growth. How do your customers usually pay you, and how quickly do the payments come in?

**Turn 4 · Noura Al-Kuwari:** Most of my regular clients pay on time, but two government-linked companies often take 90 to 120 days to pay their invoices. Sometimes this delay makes it hard for me to cover costs until they finally send the money.

**Turn 5 · You:** That sounds difficult. While you wait for those invoices, how do you manage salaries and supplier bills?

**Turn 6 · Noura Al-Kuwari:** It is very difficult. Twice this year I had to use my personal savings to pay my staff's salaries because the business cash flow was tight. I try to keep things running smoothly until the late payments arrive.

**Turn 7 · You:** Thank you for being open about that. Looking ahead, are there any big contracts or growth plans coming up for the business?

**Turn 8 · Noura Al-Kuwari:** Yes, I am currently bidding for a school catering contract worth QAR 2 million. If I win it, I will need to buy about QAR 300,000 of food stock upfront to start work on time.

**Turn 9 · You:** Good luck with the bid. For the slow payers, we have a Business Collect Account: your customers can pay by payment link and it sends them automatic reminders. Would something like that help?

**Turn 10 · Noura Al-Kuwari:** That sounds useful for getting paid faster, but I am currently banking with another bank. Could you tell me if there are any fees or conditions I should know about before we look into switching? Also, would this help with the government clients specifically?

**Turn 11 · You:** The monthly fee is QAR 150, waived if you keep at least QAR 50,000 in the account, and card payments cost 1.8%. The reminders go to every customer, government-linked ones included, but I should be honest: it speeds up collection and does not lend money.

**Turn 12 · Noura Al-Kuwari:** The fees are clear enough, and QAR 50,000 is a reasonable balance for me to keep. However, since the reminders go to everyone equally, will my government clients actually pay faster, or do they simply ignore them? Also, does this account help me plan for that QAR 300,000 stock I need if I win the school bid?

**Turn 13 · You:** Good questions. Honestly, reminders may not change how fast the government clients pay, and the account will not fund the stock. For that we have financing options, and I will include one in my recommendation. Thank you, Noura, I have a clear picture now.

**Turn 14 · Noura Al-Kuwari:** That is very honest and appreciated. Since this account does not lend money for the stock or change how the government clients pay, I am wondering what specific financing option you mentioned that could help me buy the food for the school contract? Also, are there any fees if I decide to open a new account with Al Murjan Bank soon?

## Your summary and recommendations

### Your summary

> Noura runs a growing Doha catering company with 14 staff. Two government-linked clients pay their invoices 90 to 120 days late, and twice this year she paid salaries from her personal savings. She is bidding for a QAR 2 million school catering contract that would need about QAR 300,000 of food stock up front. She needs to get paid faster and to fund that stock.

### Your recommendations

- **Business Collect Account:** Payment links and automatic reminders should help her collect invoices faster.
- **Invoice Advance:** Turns her unpaid government invoices into cash now, to cover salaries and buy the contract stock.

## Discovery map

| Need | Status | Found at | The question that found it |
| --- | --- | --- | --- |
| Bridge the gap between paying staff and suppliers and being paid late by government-linked clients, using Sharia-compliant products only. | Partly uncovered | – | – |
| Finance about QAR 300,000 of food stock up front for the school catering contract. | Uncovered | Turn 7 | Thank you for being open about that. Looking ahead, are there any big contracts or growth plans coming up for the business? |

## Your recommendations against the answer key

- **Business Collect Account: Suitable.** Meets: Bridge the gap between paying staff and suppliers and being paid late by government-linked clients, using Sharia-compliant products only.
- **Invoice Advance: Not suitable.** Interest-based; conflicts with her Sharia preference.

### Suitable products you didn't recommend

- **Murabaha Working Capital.** Meets: Bridge the gap between paying staff and suppliers and being paid late by government-linked clients, using Sharia-compliant products only.; Finance about QAR 300,000 of food stock up front for the school catering contract.

## Coach feedback

### What went well

- You asked open questions that encouraged Noura to share critical details about her cash flow challenges and upcoming opportunities. (Turns: 3, 5, 7)
- You were honest when explaining the limitations of the Business Collect Account, which built trust with the client. (Turns: 11)

### What was missed

- You missed Noura's critical need for Sharia-compliant financing because you did not ask about her banking preferences before pitching products. (Turns: 9)  
  A question you could have asked: “Do you have any preferences about the kind of banking products you use, such as Islamic banking?”
- You recommended an interest-based product that conflicts with her values. She had already indicated she only uses Sharia-compliant products. (Turns: 13)

### How to improve

- Always ask about banking preferences early in the conversation to avoid recommending interest-based products to clients who need Sharia-compliant ones.  
  For example: “Do you have any preferences about the kind of banking products you use, such as Islamic banking?”
- When a client mentions a specific funding requirement like buying stock, suggest a suitable financing product immediately rather than listing unsuitable options.

*The AI coach wrote these notes and can make mistakes. The discovery map and the verdicts above come from the answer key.*

### About your summary

Your summary correctly identified Noura's cash flow gap and the school contract opportunity. However, it missed her critical need for Sharia-compliant products. You recommended Invoice Advance, which is interest-based and unsuitable for her, while ignoring the suitable Murabaha Working Capital option that fits both her needs.

## Behind the scenes: the full client profile

### Persona

- **Age:** 38
- **Occupation:** Owner and managing director of a catering company
- **Nationality:** Qatari
- **Family:** Married, with three children
- **Background:** She started out cooking for family weddings and gatherings, and in 2019 turned it into a catering company in Doha. It now has 14 staff and caters weddings and corporate events across the city. She handles sales and key customers herself and leaves the books to a part-time accountant.
- **Personality:** Warm, proud of her team and very busy. She gives short answers unless the student follows up with a specific question, and opens up when someone shows real interest in her business.
- **Speaking style:** Short, polite sentences. Mentions that she is between events. Uses everyday words rather than banking terms.
- **Financial knowledge:** Low

### What the client shares freely

- She runs a catering company that serves weddings and corporate events in Doha.
- She wants "better banking" for the business, without having pinned down what that means.
- She currently banks with another bank.

### Hidden facts

- Two government-linked clients pay her invoices 90 to 120 days late. Twice this year she has paid her staff's salaries from her personal savings to cover the gap.  
  Critical · Found at turn 3
- She only uses Sharia-compliant banking products and won't take anything interest-based.  
  Critical · Not found
- She is bidding for a QAR 2 million school catering contract. Winning it would mean buying about QAR 300,000 of food stock up front.  
  Important · Found at turn 7

### Needs (the answer key)

- **Bridge the gap between paying staff and suppliers and being paid late by government-linked clients, using Sharia-compliant products only.** (Partly uncovered)  
  Suitable products: Murabaha Working Capital, Business Collect Account  
  Unsuitable products: Business Overdraft (Interest-based; conflicts with her Sharia preference.); Invoice Advance (Interest-based; conflicts with her Sharia preference.)

- **Finance about QAR 300,000 of food stock up front for the school catering contract.** (Uncovered)  
  Suitable products: Murabaha Working Capital  
  Unsuitable products: Business Overdraft (Interest-based; conflicts with her Sharia preference.); Invoice Advance (Interest-based; conflicts with her Sharia preference.)

---

Fictional bank and products for teaching only. Not financial advice.
