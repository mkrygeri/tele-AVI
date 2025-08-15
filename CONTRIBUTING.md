# Contributing to AVI Load Balancer to Kentik Integration

We love your input! We want to make contributing to this project as easy and transparent as possible, whether it's:

- Reporting a bug
- Discussing the current state of the code
- Submitting a fix
- Proposing new features
- Becoming a maintainer

## Development Process

We use GitHub to host code, to track issues and feature requests, as well as accept pull requests.

## Pull Requests

Pull requests are the best way to propose changes to the codebase. We actively welcome your pull requests:

1. Fork the repo and create your branch from `main`.
2. If you've added code that should be tested, add tests.
3. If you've changed APIs, update the documentation.
4. Ensure the test suite passes.
5. Make sure your code lints.
6. Issue that pull request!

## Any contributions you make will be under the MIT Software License

In short, when you submit code changes, your submissions are understood to be under the same [MIT License](http://choosealicense.com/licenses/mit/) that covers the project. Feel free to contact the maintainers if that's a concern.

## Report bugs using Github's [issues](https://github.com/mkrygeri/tele-AVI/issues)

We use GitHub issues to track public bugs. Report a bug by [opening a new issue](https://github.com/mkrygeri/tele-AVI/issues/new); it's that easy!

## Write bug reports with detail, background, and sample code

**Great Bug Reports** tend to have:

- A quick summary and/or background
- Steps to reproduce
  - Be specific!
  - Give sample code if you can
- What you expected would happen
- What actually happens
- Notes (possibly including why you think this might be happening, or stuff you tried that didn't work)

People *love* thorough bug reports. I'm not even kidding.

## Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/mkrygeri/tele-AVI.git
   cd tele-AVI
   ```

2. **Install dependencies** (for mock server development)
   ```bash
   pip install -r requirements.txt
   ```

3. **Start the development environment**
   ```bash
   docker-compose -f docker-compose.testing.yml up -d
   ```

4. **Test your changes**
   ```bash
   python test-mock-avi.py
   ./validate-config.sh
   ```

## Testing

Before submitting a pull request, please ensure:

1. **Mock server tests pass**:
   ```bash
   python test-mock-avi.py
   ```

2. **Telegraf configuration is valid**:
   ```bash
   ./validate-config.sh
   ```

3. **Docker containers build and run**:
   ```bash
   docker-compose -f docker-compose.testing.yml up --build
   ```

## Code Style

- Follow existing code patterns
- Use meaningful variable names
- Add comments for complex logic
- Update documentation for any changes

## License

By contributing, you agree that your contributions will be licensed under its MIT License.

## References

This document was adapted from the open-source contribution guidelines for [Facebook's Draft](https://github.com/facebook/draft-js/blob/a9316a723f9e918afde44dea68b5f9f39b7d9b00/CONTRIBUTING.md)
