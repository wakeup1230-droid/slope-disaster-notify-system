# Release Checklist

## Before Merge dev -> main

- [ ] All PR checks are green
- [ ] Integration behavior validated on `dev`
- [ ] No unresolved review comments
- [ ] No critical open bugs for release scope
- [ ] Release notes drafted

## After Merge to main

- [ ] `release-main` workflow triggered successfully
- [ ] Deployment status confirmed
- [ ] Smoke test completed on production
- [ ] Rollback instructions confirmed
