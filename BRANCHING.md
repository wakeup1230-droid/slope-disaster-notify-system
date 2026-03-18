# Branching Policy

## Branch Roles

- `main`: production-ready only
- `dev`: integration and testing
- `feature/*`: short-lived task branches

## Developer Flow

1. Sync base:
   - `git checkout dev`
   - `git pull origin dev`
2. Create feature:
   - `git checkout -b feature/<name>`
3. Work and push:
   - `git add .`
   - `git commit -m "feat: <what changed>"`
   - `git push -u origin feature/<name>`
4. Open PR:
   - `feature/<name>` -> `dev`
5. After QA on `dev`, create PR:
   - `dev` -> `main`

## Required Team Rules

- Never commit directly to `main`
- Pull before push
- Use clear commit messages (no `update` only)
- Require PR review before merge

## GitHub Branch Protection (Recommended)

For `main`:
- Require pull request before merge
- Require at least 1 approval
- Require status checks to pass
- Require conversation resolution

For `dev`:
- Require pull request before merge
- Require status checks to pass
