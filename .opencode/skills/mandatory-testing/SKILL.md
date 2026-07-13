# Mandatory Testing

Use this skill whenever code is modified.

## Goal

Prevent regressions and detect issues immediately.

## Workflow

After every meaningful code change:

1. Compile the project.
2. Fix all compilation errors.
3. Run existing tests.
4. Fix failing tests before continuing.
5. Review logs for warnings and errors.
6. Confirm the application still starts correctly.

## Large Changes

If more than 3 files are modified:

1. Stop.
2. Compile.
3. Run tests.
4. Summarize the current status.
5. Continue only if validation passes.

## Forbidden

* Continuing development with failing tests.
* Ignoring compiler errors.
* Making multiple changes without validation.

## Completion Criteria

A task is not finished until validation succeeds.
