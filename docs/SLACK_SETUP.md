# Creating the Slack app (step by step, no coding required)

This creates a "bot" — a robot member of your Slack workspace that is allowed
to read the #doyoulikefitness channel on our behalf. At the end you'll have a
**bot token**: a long password-like string starting with `xoxb-` that our
code uses to talk to Slack.

Total time: about 10 minutes. You need to be signed in to your Slack
workspace in your browser.

## Step 1 — Create the app

1. Go to **https://api.slack.com/apps** in your browser.
2. Click the green **Create New App** button.
3. Choose **From scratch**.
4. App Name: `Blueprint Fitness Bot` (or anything you like).
5. "Pick a workspace to develop your app in": choose your team's workspace.
6. Click **Create App**. You'll land on the app's settings page.

## Step 2 — Give the bot permission to read the channel

Slack makes you spell out exactly what an app is allowed to do. These are
called **scopes**. We only need read access.

1. In the left sidebar, click **OAuth & Permissions**.
2. Scroll down to **Scopes → Bot Token Scopes**.
3. Click **Add an OAuth Scope** and add each of these, one at a time:
   - `channels:history` — read messages in public channels the bot is in
   - `channels:read` — see the list of channels (so we can find #doyoulikefitness)
   - `users:read` — see members' names (so we can print "Sam" instead of a user ID)

> **Is #doyoulikefitness a private channel?** (Private channels show a lock
> icon 🔒 instead of #.) If so, also add `groups:history` and `groups:read`.

## Step 3 — Install the app to your workspace

1. Still on the **OAuth & Permissions** page, scroll to the top.
2. Click **Install to Workspace** (you may need workspace-admin approval —
   if Slack says an admin has to approve it, ask them and come back).
3. Review the permissions screen and click **Allow**.
4. You're returned to the OAuth & Permissions page. At the top you'll now see
   **Bot User OAuth Token** — a string starting with `xoxb-`.
5. Click **Copy**. This is the token our code needs.

> ⚠️ **Treat this token like a password.** Anyone who has it can read your
> channels. Don't post it in Slack or email. We'll keep it in a `.env` file
> that git is configured to never upload.

## Step 4 — Invite the bot into the channel

Bots can only read channels they've been invited to (just like a person).

1. Open Slack and go to **#doyoulikefitness**.
2. Type this message and send it:
   ```
   /invite @Blueprint Fitness Bot
   ```
3. Slack will confirm the bot was added to the channel.

## Step 5 — Put the token where the code can find it

1. In the project folder, find the file named `.env.example`.
2. Make a copy of it and name the copy exactly `.env`
3. Open `.env` in any text editor and paste your token right after the `=`
   sign on the `SLACK_BOT_TOKEN=` line — no quotes, no spaces.
4. Save the file. Done!

Now follow "Running Milestone 1" in the main [README](../README.md).

## If something goes wrong

| What you see | What it means | Fix |
|---|---|---|
| `invalid_auth` | The token is wrong or incomplete | Re-copy the token from OAuth & Permissions; check for missing characters |
| `channel_not_found` | The bot can't see the channel | Private channel? Add the `groups:*` scopes (Step 2) and re-install the app |
| `not_in_channel` | The bot isn't a member of the channel | Do Step 4 — invite the bot |
| `missing_scope` | A permission wasn't added | Re-check Step 2, then **re-install** the app (Step 3) — scope changes only take effect after re-installing |
