# Onboarding interview

Purpose: build or complete a person's profile (`about-<person>.md`) by interviewing them — not
guessing. Captures skills, strengths and weaknesses from a project standpoint, and how they
want to work.

## When it runs
Trigger when `whoami` shows a user whose `about-<user>.md` is missing or marked
`profil_status: ofullständig`. Ask first if they have 5–10 minutes.

## How
- One question at a time via AskUserQuestion. Let them speak freely (voice dictation works well).
- Push back on vague answers. Aim for ~12–16 questions; adapt.
- This is a colleague, not an interrogation. Frame "weaknesses" as *where do you want the
  assistant to take work off your plate*.

## Cover
1. Role & projects. 2. Skills. 3. Strengths from a project view. 4. Weak spots / where they want
support. 5. How they want to work (pace, decision style, when to interrupt vs leave alone).
6. Preferences & dislikes (text, tone, format). 7. Goals.

## After
Compile into `about-<person>.md`: condensed prose + bullets, no raw Q&A. Set
`profil_status: klar` + `uppdaterad: <date>`. Save via `memory_write` (git commit). Show a short
summary and ask if anything should be corrected.

## Privacy
Profiles live in `shared/`, read by the assistant for the person's projects. Store only what's
relevant to the collaboration.
