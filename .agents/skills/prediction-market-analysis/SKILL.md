```markdown
# prediction-market-analysis Development Patterns

> Auto-generated skill from repository analysis

## Overview
This skill covers the core development patterns and conventions used in the `prediction-market-analysis` Python codebase. It guides contributors in writing consistent, maintainable code, structuring files, handling imports/exports, and following commit and testing practices. While no specific frameworks or automated workflows are detected, this skill ensures you align with the project's established standards.

## Coding Conventions

### File Naming
- Use **snake_case** for all Python file names.
  - Example: `market_data_loader.py`, `prediction_engine.py`

### Import Style
- Use **relative imports** within the package.
  - Example:
    ```python
    from .utils import calculate_odds
    from .data_loader import load_market_data
    ```

### Export Style
- Use **named exports** (i.e., explicitly define what is exported).
  - Example:
    ```python
    __all__ = ['calculate_odds', 'MarketPredictor']
    ```

### Commit Messages
- Follow **conventional commit** style with prefixes:
  - `feat`: New features
  - `test`: Test-related changes
  - `docs`: Documentation updates
- Keep commit messages concise (average ~42 characters).
  - Example: `feat: add market trend analysis module`

## Workflows

### Adding a New Feature
**Trigger:** When implementing new functionality  
**Command:** `/add-feature`

1. Create a new Python file using snake_case if needed.
2. Write code using relative imports for internal modules.
3. Define `__all__` for named exports.
4. Commit changes with a `feat:` prefix.
   - Example: `feat: implement outcome probability estimator`

### Writing and Running Tests
**Trigger:** When adding or updating tests  
**Command:** `/run-tests`

1. Create test files matching the `*.test.*` pattern (e.g., `market_analysis.test.py`).
2. Write tests for new or updated modules.
3. Run tests using your preferred Python test runner (e.g., `pytest`, `unittest`).
4. Commit test changes with a `test:` prefix.
   - Example: `test: add tests for odds calculation`

### Updating Documentation
**Trigger:** When updating or adding documentation  
**Command:** `/update-docs`

1. Edit or create documentation files as needed.
2. Commit changes with a `docs:` prefix.
   - Example: `docs: update usage section in README`

## Testing Patterns

- Test files follow the `*.test.*` naming convention.
  - Example: `market_data_loader.test.py`
- The specific test framework is not enforced; use your preferred Python testing tool.
- Place tests alongside or near the modules they test for easier maintenance.

## Commands

| Command        | Purpose                                   |
|----------------|-------------------------------------------|
| /add-feature   | Scaffold and commit a new feature module  |
| /run-tests     | Run all tests in the codebase             |
| /update-docs   | Update or add documentation files         |
```