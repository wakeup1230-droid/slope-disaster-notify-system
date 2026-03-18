# Versioning Policy

## Version Standard

- Follow SemVer: `MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]`
- Tag format: `v<version>` (example: `v2.4.0-rc.1`)

## Branch to Version Mapping

- `feature/*` -> `X.Y.Z-alpha.N`
- `dev` -> `X.Y.Z-beta.N`
- `test` -> `X.Y.Z-rc.N`
- `main` -> `X.Y.Z`
- `hotfix/*` -> `X.Y.(Z+1)`

## Lifecycle

1. Start feature with `alpha` versions
2. After merge to `dev`, use `beta`
3. Promote to `test`, use `rc`
4. After verification, publish stable on `main`

## Increment Rules

- PATCH: backward-compatible bug fix
- MINOR: backward-compatible feature
- MAJOR: breaking change

## Required Artifacts per release

- `VERSION` file updated
- Annotated git tag created
- Release notes or changelog entry updated
