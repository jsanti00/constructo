# Constructo

An AI agent that construction site engineers query from Telegram to get answers
about their own project: the budget, the drawings, the schedule, the contract.

It has been running in production since July 2026 on a commercial building
project, used daily by site engineers who are not its author.

## The problem

On a fixed unit-price contract, the contractor's margin is decided by whether
the work executed matches what was priced. That information exists, but it lives
in a 3,000-row budget spreadsheet, a folder of drawings, and a signed contract.
An engineer standing on site cannot query any of it, so the answer arrives days
later, by phone, or not at all.

## The design constraint that mattered

The hard part was not answering questions. It was **not being trusted blindly**.

A construction budget holds two very different kinds of number: what the signed
contract says, and what our own analysis estimates. Confusing them is how a
contractor commits to a price that does not hold. So every answer the agent
gives states which one it is using, names the file it came from, and says
plainly what is still unreconciled instead of smoothing it over.

The rule is: a wrong number should never be able to travel as an official one.

## How it works

```
Telegram  ->  bot_telegram.py  ->  cerebro.py  ->  claude (headless)  ->  project folder
```

| File | What it does |
|---|---|
| `agente/bot_telegram.py` | Talks to Telegram: receives questions, enforces the allowlist, sends back answers and any file the agent produced |
| `agente/cerebro.py` | The reasoning step. Runs `claude` in headless mode inside the project folder, with the excluded folders blocked, and collects what it wrote |
| `agente/config.py` | Settings you are meant to change: model, reasoning effort, memory depth |
| `comun/` | Templates and the hydration script used to set up a new project folder |

Design decisions worth naming:

- **One instance per project.** Same code, separate processes, each with its own
  bot token, its own allowlist, and its own data root. No instance can read
  another project's folder. Construction data is confidential per client.
- **The code holds no data.** The project folder is passed in through the
  `OBRA_RAIZ` environment variable, which is why this repository can be public
  while the projects stay private.
- **Some folders are invisible to the agent.** `_restringido/` holds material we
  deliberately keep out of its reach.
- **No API key.** The agent reasons by calling the local `claude` binary under a
  personal subscription, which is what made it cheap enough to run daily while
  it was still an experiment.

## What is deliberately not in this repository

No budgets, drawings, contracts, or client documents. Not a single figure from a
real project. Those belong to the contractors, not to me, and a public repository
is not the place for them. What is here is the machinery; the data stays where it
was produced.

Client and project names are replaced by aliases for the same reason.

## Running it

See `agente/README.md` for setup: creating the bot, installing dependencies,
collecting the Telegram user ids of the engineers, and storing the token.

Secrets live in `~/.config/agente-obra/.env`, never in the repository.

## A note on language

The code and its comments are in Spanish. The people who use this agent are
Colombian site engineers, and the person maintaining it is learning to read code
as he goes. Writing it in the language of its users was the point.
