# Discord rehearsal for v0.3

Status: Rehearsal Bot is installed and running in H.LFO Rehearsal. The owner reported the initial start/end flow worked. Performer buttons and pause/resume/accidental-end recovery are now posted for hands-on testing.
The live website and production bot stay running throughout this rehearsal.

## What is needed from the owner

A separate Discord test server and a separate Discord test application/bot.
If these already exist, provide only the location of their private configuration
file. Keep tokens and client secrets out of chat. No production bot token is needed
for the test bot; a read-only production configuration reference is used locally
only to check that application, token, and server differ.

If they do not exist:

1. Create a private test server, such as H.LFO Rehearsal. Invite only the testers.
2. Create a new application, such as H.LFO Rehearsal Bot, in the Discord Developer
   Portal. Leave the existing production application unchanged.
3. Install that new application to the test server with bot and applications.commands
   scopes. Discord's official setup guide explains application creation and server
   installation: https://github.com/discord/discord-api-docs/blob/main/developers/quick-start/getting-started.mdx
4. The current gateway code requests Server Members and Presence intents; enable
   those for the TEST application. Message Content intent is not required.
5. Make a Verified role and a rehearsal text channel. Assign Verified manually to
   test performers. For the performance flow, the bot needs View Channel, Send
   Messages, and Read Message History; a thread also needs Send Messages in Threads.
   Role management is not needed if testers receive Verified manually.
6. Save the new application's settings privately using the provided
   deploy/performance-rehearsal.env.example as a template. Use a new test database
   directory and a new session secret. Add a test OAuth client secret/callback only
   if testing the website organizer controls through Discord login as well.

## Prepared developer checks

Read-only separation check (does not log credentials or contact Discord):

    python -m scripts.check_performance_rehearsal \
      --env-file /absolute/path/to/.env.rehearsal \
      --production-env /absolute/path/to/the/existing/.env \
      --database-root /absolute/path/to/work/rehearsal-live

The explicit test file is checked rather than merged with the shell environment.
The test app/token/server must differ from the reference production settings.
Unrelated announcements, reports, and onboarding must be disabled. The database
must be a file-backed SQLite database within the designated test directory.
These checks do not prove token validity or Discord channel permissions.

Offline end-to-end rehearsal, safe to run before any Discord setup:

    python -m scripts.rehearse_performances --output-dir ../rehearsal-offline-NEW

The output directory must not exist. The script creates only a fresh synthetic
database, upgrades it through Alembic, and simulates a 25-performer evening. It
reports the results as JSON. It makes no network requests. Do not attach a real bot
to this completed offline simulation; the live rehearsal gets its own fresh DB.

Once the private test configuration is available, the development agent can check
it, prepare that separate DB, verify test bot identity, and start the test process
with those explicit settings. No production cutover is part of this runbook.

## Live acceptance scenarios

Use one organizer and preferably two real test accounts. Automated tests simulate
25 performers; do not create fake Discord user accounts to populate the test server.

1. Publish one TEST event and enable performances for its test channel/thread.
   Confirm a draft never posts its stage board and accepts no performer signup.
2. Register two Verified testers through /perform action. Check /perform setlist
   and /perform mystatus; attendance RSVP counts must stay unchanged.
3. Withdraw the first tester and register them again. They fill the earliest eligible
   vacancy; the other tester keeps their position. Review retained history.
4. Check in a tester. They are arrived but not ready. Use Ready to perform separately.
5. Activate the event. Confirm only the allowlisted organizer can start next.
6. Start and end the first set. The board must show no one playing until the
   organizer explicitly starts the next. Test an immediate handoff.
7. Repeat with a house-music wait. Original times remain unchanged while projected
   times move forward. A delayed event must still accept a future queue vacancy
   even if that position's original time is overdue.
8. Check next/on-deck mentions, timing, and channel permission behavior. Leads can
   be shortened in a separate test event so a rehearsal need not last several hours.
9. Try an old stage control after readiness/queue changes. It must request a refresh
   and must not start the wrong person. Repeated actions must not advance twice.
10. Restart ONLY the test bot during an active set. It must restore the current
    performer, arrival/readiness, stage buttons, and delivery records without starting
    or ending anything automatically.
11. Pause/resume, skip an unavailable performer, close/reopen registration, and
    unpublish/republish the TEST event. Confirm the intended suspended behavior.
12. End the event. The final set sheet stays stored, upcoming indicators clear,
    and no further preparation notices are delivered.

Record observed results, permission failures, duplicate notices, and screenshots
from the test server. Only after acceptance should a production rollout be reviewed.

## Additional acceptance: interruptions and phone controls

Use the member buttons on the stage board to register, report arrival, and mark
ready separately. My status replies privately. Test these in the Discord mobile
app; automated callback tests are not a substitute for hands-on phone acceptance.

During a set, tap Organizer: pause set and confirm the remaining clock is held.
Wait, then tap Organizer: resume set; the same performer continues with the remaining
time. No next performer may start while a paused set remains current. If the event
queue is also paused, resume queue progression separately.

End a test set, then use Restore last set before starting another performer. It
should recover the same actual start and remaining clock, retaining the mistaken
end action in history. Verify recovery is rejected after another set has started.
Repeat after a test-bot restart with a paused set; it must remain paused.
