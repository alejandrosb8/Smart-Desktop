# Contributing to Smart Desktop

Thanks for your interest in contributing! Here’s how to help:

## Getting started

- Fork the repository and create a feature branch from `main`.
- Use a virtual environment and install requirements from `requirements.txt`.
- Run the app locally with `python main.py` to validate your changes.

## Guidelines

- Keep the UI simple and accessible. Prefer ttk widgets and follow the existing tabbed layout.
- Avoid breaking public behavior: keep existing options (Preview, Organize, Revert, Clean, SKIP, exclusions, thinking, categories).
- When adding a new option, wire it through: UI → config.json → backend function parameters.
- Log user-facing actions via the central logger to surface in the Log tab.
- Prefer small, focused PRs with a clear description and screenshots if UI changes.

## Code style

- Python 3.11+ syntax is allowed; prefer typing where it helps readability.
- Keep functions small and focused. Extract helpers when logic grows.
- Handle exceptions cleanly and notify users via message boxes where appropriate.

## Testing

- Manual testing steps should be included in the PR description (e.g., preview, apply, revert, clean).
- If you change classification behavior, include a brief note about risk/impact.

## Security

- Never log API keys or sensitive content.
- Keep key storage via `keyring`; avoid adding plaintext secrets to files.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
