# Contributing to LeadGen AI Voice Agent

Thank you for your interest in contributing! This document provides guidelines and instructions for contributing.

## Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Focus on the issue, not the person
- Help others learn and grow

## Getting Started

### Prerequisites

- Python 3.10+
- Docker & Docker Compose
- Git
- Node.js 18+ (for frontend)

### Setup Development Environment

```bash
# 1. Fork and clone the repository
git clone https://github.com/YOUR_USERNAME/leadgenrationaivoiceagent.git
cd leadgenrationaivoiceagent

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Install pre-commit hooks
pre-commit install

# 5. Copy environment file
cp .env.example .env
# Edit .env with your API keys

# 6. Run tests
pytest tests/ -v
```

## Development Workflow

### 1. Create a Branch

```bash
# For features
git checkout -b feature/your-feature-name

# For bug fixes
git checkout -b fix/issue-description

# For documentation
git checkout -b docs/what-you-are-documenting
```

### 2. Make Changes

- Write clean, readable code
- Follow existing code style
- Add tests for new features
- Update documentation

### 3. Run Quality Checks

```bash
# Format code
make format

# Run linters
make lint

# Run tests
make test

# Run all pre-commit hooks
make pre-commit
```

### 4. Commit Changes

Follow conventional commit format:

```
type(scope): description

[optional body]

[optional footer]
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Formatting
- `refactor`: Code restructuring
- `test`: Adding tests
- `chore`: Maintenance

Examples:
```bash
git commit -m "feat(voice-agent): add Hindi language support"
git commit -m "fix(scraper): handle rate limiting in Google Maps"
git commit -m "docs(readme): update installation instructions"
```

### 5. Push and Create PR

```bash
git push origin your-branch-name
```

Then create a Pull Request on GitHub.

## Pull Request Guidelines

### PR Title
- Use conventional commit format
- Be descriptive but concise

### PR Description
Include:
- What changes were made
- Why the changes were needed
- How to test the changes
- Screenshots (if UI changes)

### PR Checklist
- [ ] Tests pass locally
- [ ] Code follows style guidelines
- [ ] Documentation updated
- [ ] No secrets committed
- [ ] Changelog updated (if applicable)

## Code Style

### Python
- Follow PEP 8
- Use type hints
- Maximum line length: 100 characters
- Use meaningful variable names

```python
# Good
async def process_lead(lead: Lead, campaign_id: str) -> ProcessResult:
    """Process a lead and return the result."""
    ...

# Bad
async def pl(l, c):
    ...
```

### Docstrings
Use Google-style docstrings:

```python
def calculate_lead_score(lead: Lead, weights: Dict[str, float]) -> int:
    """
    Calculate the lead score based on various factors.
    
    Args:
        lead: The lead to score
        weights: Scoring weights for different factors
        
    Returns:
        Score between 0-100
        
    Raises:
        ValueError: If weights are invalid
    """
```

## Testing Guidelines

### Test Structure
```
tests/
??? conftest.py          # Shared fixtures
??? test_api.py          # API endpoint tests
??? test_voice_agent.py  # Voice agent tests
??? test_production_ready.py  # Production checks
??? integration/         # Integration tests
```

### Writing Tests
```python
class TestLeadScoring:
    """Test lead scoring functionality."""
    
    def test_high_score_for_qualified_lead(self, qualified_lead):
        """Qualified leads should receive high scores."""
        score = calculate_lead_score(qualified_lead)
        assert score >= 70
    
    @pytest.mark.asyncio
    async def test_async_scoring(self, lead_factory):
        """Test async scoring pipeline."""
        leads = [lead_factory() for _ in range(10)]
        scores = await score_leads_batch(leads)
        assert len(scores) == 10
```

### Running Tests
```bash
# All tests
pytest

# Specific file
pytest tests/test_api.py

# With coverage
pytest --cov=app --cov-report=html

# Fast mode (stop on first failure)
pytest -x --ff
```

## Documentation

### Where to Document
- **README.md**: Project overview, quick start
- **docs/**: Detailed documentation
- **Code comments**: Complex logic explanation
- **Docstrings**: Function/class documentation

### API Documentation
- Update OpenAPI schemas in route definitions
- Add examples for request/response models
- Document error responses

## Architecture Decisions

For significant changes, create an ADR (Architecture Decision Record):

```markdown
# ADR-001: Use Vertex AI for LLM

## Status
Accepted

## Context
Need to choose LLM provider for voice agent.

## Decision
Use Google Vertex AI with Gemini models.

## Consequences
- Lower latency in Asia-Pacific
- Cost-effective at scale
- Vendor lock-in to GCP
```

## Getting Help

- **Questions**: Open a Discussion on GitHub
- **Bugs**: Open an Issue with reproduction steps
- **Security**: Email security@leadgenai.com

## Recognition

Contributors will be recognized in:
- CHANGELOG.md
- README.md contributors section
- Release notes

---

Thank you for contributing to LeadGen AI! ??
