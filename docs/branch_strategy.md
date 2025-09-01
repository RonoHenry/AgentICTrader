# Branch Strategy

## Current Branches

### Main Branches
- `master`: Production-ready code
- `develop`: Main development branch
- `release/v1.0.0`: Current release preparation

### Feature Branches
- `feature/initial-setup`: Core infrastructure setup
- `feature/llm-integration`: LLM integration implementation
- `feature/trading-engine`: Trading engine development

### Maintenance Branches
- `bugfix/fix-fetch-errors`: Fixing data fetching issues
- `hotfix/urgent-patch`: Critical fixes for production

## Branching Strategy (Git Flow)

### Main Branches
1. **master**
   - Production code
   - Always stable
   - Tagged releases
   - Protected branch

2. **develop**
   - Main development branch
   - Integration branch
   - Source for feature branches
   - Pre-release testing

### Supporting Branches

1. **feature/**
   - Branch from: `develop`
   - Merge back to: `develop`
   - Naming: `feature/descriptive-name`
   - For new features development
   
2. **release/**
   - Branch from: `develop`
   - Merge back to: `master` and `develop`
   - Naming: `release/vX.Y.Z`
   - For release preparation
   
3. **hotfix/**
   - Branch from: `master`
   - Merge back to: `master` and `develop`
   - Naming: `hotfix/issue-description`
   - For urgent production fixes
   
4. **bugfix/**
   - Branch from: `develop`
   - Merge back to: `develop`
   - Naming: `bugfix/issue-description`
   - For non-urgent bug fixes

## Workflow

1. **Feature Development**
   ```bash
   git checkout develop
   git pull origin develop
   git checkout -b feature/new-feature
   # Make changes
   git commit -m "feat: add new feature"
   git push origin feature/new-feature
   # Create PR to develop
   ```

2. **Bug Fixes**
   ```bash
   git checkout develop
   git pull origin develop
   git checkout -b bugfix/fix-description
   # Fix bug
   git commit -m "fix: resolve issue"
   git push origin bugfix/fix-description
   # Create PR to develop
   ```

3. **Release Process**
   ```bash
   git checkout develop
   git pull origin develop
   git checkout -b release/v1.0.0
   # Version bump and final testing
   git commit -m "chore: bump version to 1.0.0"
   # Create PR to master and develop
   ```

4. **Hotfix Process**
   ```bash
   git checkout master
   git pull origin master
   git checkout -b hotfix/critical-fix
   # Fix critical issue
   git commit -m "fix: resolve critical issue"
   # Create PR to master and develop
   ```

## Branch Protection Rules

1. **master**
   - Require PR reviews
   - All tests must pass
   - No direct pushes
   - Signed commits required

2. **develop**
   - Require PR reviews
   - All tests must pass
   - No direct pushes

3. **release/**
   - Require PR reviews
   - All tests must pass
   - Version bump required

## Commit Message Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

Types:
- feat: New feature
- fix: Bug fix
- docs: Documentation
- style: Formatting
- refactor: Code restructure
- test: Testing
- chore: Maintenance

Example:
```
feat(trading): add pattern recognition

- Implement candlestick pattern detection
- Add unit tests for patterns
- Update documentation

Closes #123
```

## Testing Requirements

1. **Feature Branches**
   ```powershell
   .\run_tests.ps1 -UnitOnly  # During development
   .\run_tests.ps1  # Before PR
   ```

2. **Release Branches**
   ```powershell
   .\run_tests.ps1  # Full suite required
   .\run_tests.ps1 --cov-report=html  # Coverage check
   ```

## Code Review Process

1. Create PR with:
   - Clear description
   - Test results
   - Coverage report
   - Related issues

2. Reviewers check:
   - Code quality
   - Test coverage
   - Documentation
   - Performance impact

3. CI/CD checks:
   - All tests pass
   - Code style
   - Security scan
   - Coverage thresholds
