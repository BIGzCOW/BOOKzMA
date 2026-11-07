# N-01 Smoke Test Checklist

Status: in progress. This checklist is for owner execution in Telegram and must remain in progress until live verification is actually performed.

## Scope
This is a bot smoke test for the main Telegram flow and should be run only on a safe, allowed environment. It does not count as complete until the owner or a verified operator actually executes it in Telegram.

## Checklist

### 1. Start flow
- [ ] Run `/start` in a fresh user context.
- [ ] Confirm the main menu renders correctly.
- [ ] Confirm the bot does not crash on first launch.

### 2. Main menu and submenus
- [ ] Confirm the main keyboard includes Home, Profile, Personal Library, Mesbak, Study Buddy, and More.
- [ ] Open Profile and verify the submenu works.
- [ ] Open Settings and verify the reminder/timezone controls work.
- [ ] Open More and verify the expected options appear.
- [ ] Open Today, Reports, Settings, Challenges, and League from the Mesbak menu.
- [ ] Confirm both exit paths from Mesbak return to the primary keyboard.

### 3. Reading flow and summary
- [ ] Confirm reading actions work from the main flow.
- [ ] Confirm the weekly summary appears and is populated correctly.
- [ ] Confirm the read flow does not duplicate or create a false second read when retried.

### 4. Profile and support flows
- [ ] Open the profile flow and ensure the expected actions are reachable.
- [ ] Confirm the support path remains accessible and the ticket flow is stable.

### 5. Onboarding and return flow
- [ ] Run the onboarding flow for a new user.
- [ ] Confirm the welcome-back flow for a returning user behaves as expected.
- [ ] Confirm the Mesbak entry point is still available during onboarding.

### 6. Reminder and availability checks
- [ ] Confirm reminder times are accepted and displayed correctly.
- [ ] Confirm timezone changes are accepted and reflected in the UI.
- [ ] Confirm there is no fallback to a broken or duplicated menu state.

### 7. Message exit behavior
- [ ] Verify that leaving Mesbak from the keyboard returns to the main keyboard.
- [ ] Verify that leaving Mesbak from the inline settings flow also returns to the main keyboard.

### 8. Bot return / recovery checks
- [ ] Confirm a restarted bot resumes without getting stuck in a stale state.
- [ ] Confirm the user can continue from the main menu after recovering from an error.

## Current status
- This has not been executed in a live Telegram environment yet.
- It remains intentionally marked as in progress instead of complete.
- The owner should run it and record the actual results before marking the feature as complete.

## Risk
This document is a checklist only. It is not a substitute for real Telegram verification. Until the live run happens, the repo must not claim N-01 is fully complete.
