# Blueprint Fitness Dashboard

A fitness accountability dashboard for the Blueprint ultimate frisbee team.

Every week, each team member posts **1 throwing selfie** and **1 cardio
selfie** in the Slack channel **#doyoulikefitness** (both can be in a single
post). This project reads those posts from Slack, figures out what kind of
workout each one is, and shows everyone's weekly compliance on a web
dashboard.

## Build plan

| Milestone | What it does | Status |
|-----------|--------------|--------|
| 1 | Connect to Slack and print recent channel messages | ✅ Built — needs your Slack token to run |
| 2 | Classify each post as throwing / cardio / combined (keywords + emoji) | Not started |
| 3 | Store players and weekly submissions in SQLite (weeks run Mon–Sun) | Not started |
| 4 | Web dashboard: every player, weekly throwing ✓ / cardio ✓ | Not started |
| 5 | Filter players in/out; flag injuries so injured players are excused | Not started |
| 6 | Blue & white "blueprint" visual theme | Not started |

Ideas for later: automatic scheduled syncing, AI image classification of the
selfies themselves.

## Project structure

```
BlueprintDashboard/
├── README.md                    ← you are here
├── docs/
│   └── SLACK_SETUP.md           ← step-by-step guide to create the Slack app
├── requirements.txt             ← list of Python packages this project needs
├── .env.example                 ← template for your secret settings file
├── .gitignore                   ← tells git which files to never upload (like your token)
├── milestone1_check_slack.py    ← Milestone 1: prints recent channel messages
└── app/                         ← the real application code will grow here
    (empty for now — classification, database, and dashboard code arrive in
     Milestones 2–4)
```

## Running Milestone 1

**Step 1.** Create the Slack app and get your bot token — follow
[docs/SLACK_SETUP.md](docs/SLACK_SETUP.md). It takes about 10 minutes and
requires no coding.

**Step 2.** Make a copy of `.env.example` named `.env` and paste your token
into it. The `.env` file stays on your machine only — git is configured to
never upload it.

**Step 3.** In a terminal, from this project folder, run:

```bash
python3 -m venv .venv                # one-time: create a private Python sandbox
source .venv/bin/activate            # step into the sandbox
pip install -r requirements.txt      # one-time: install the Slack library
python milestone1_check_slack.py     # run the check!
```

If everything is wired up correctly, you'll see the last 20 messages from
#doyoulikefitness printed with names and dates. That means the pipeline
works and we can build everything else on top of it.

(You can also just tell Claude the token is ready and have it run the script
for you.)
