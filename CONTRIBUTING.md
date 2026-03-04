# Contributing to OpenClaw Tor Network

Thank you for your interest in contributing!

## Development Setup

```bash
git clone https://github.com/incept5/openclaw-tor-network.git
cd openclaw-tor-network
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## Testing

```bash
# Run unit tests
pytest tests/

# Run integration test (requires Tor)
./tests/e2e_test.sh
```

## Code Style

- Follow PEP 8
- Use type hints
- Add docstrings to all public functions

## Pull Request Process

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a PR

## Security

If you discover a security vulnerability, please email security@incept5.dev instead of opening a public issue.
