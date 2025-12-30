# Contributing to Docker Internals Guide

Thank you for your interest in contributing! This document provides guidelines for contributing to this project.

## 🎯 How to Contribute

### Reporting Issues

Before creating an issue, please check if it already exists. When reporting:

**For bugs:**
- Describe the issue clearly
- Include your OS and Docker version
- Provide steps to reproduce
- Include error messages and logs
- Mention which test failed

**For feature requests:**
- Describe the proposed feature
- Explain why it would be useful
- Provide examples if applicable

### Code Contributions

1. **Fork the repository**
2. **Create a feature branch** (`git checkout -b feature/your-feature`)
3. **Make your changes**
4. **Test thoroughly** on Ubuntu 24.04 (minimum)
5. **Commit with clear messages**
6. **Push to your fork**
7. **Open a pull request**

## 📝 Code Standards

### Shell Scripts (Bash)

- Use `#!/bin/bash` shebang
- Follow Google Shell Style Guide basics
- Include descriptive function names
- Add comments for complex logic
- Use `set -euo pipefail` for safety
- Test with shellcheck if possible

**Example:**
```bash
#!/bin/bash
set -euo pipefail

# Check if Docker is running
check_docker() {
    if ! docker info &>/dev/null; then
        echo "Error: Docker daemon not running"
        return 1
    fi
}
```

### Testing Requirements

All new features must:
- ✅ Work on Ubuntu 24.04
- ✅ Handle errors gracefully
- ✅ Provide clear output
- ✅ Not require manual cleanup
- ✅ Be documented in README

### Documentation

- Update README.md if adding features
- Add inline comments for complex code
- Include usage examples
- Document prerequisites

## 🔧 Areas for Contribution

### High Priority
- [ ] Windows WSL2 compatibility testing
- [ ] macOS Docker Desktop compatibility
- [ ] Additional performance benchmarks
- [ ] Security profile examples
- [ ] Error handling improvements

### Medium Priority
- [ ] Kubernetes integration tests
- [ ] CI/CD examples (GitHub Actions, GitLab CI)
- [ ] Prometheus metrics exporter
- [ ] GUI dashboard for results
- [ ] Docker Compose benchmarks

### Low Priority (Nice to Have)
- [ ] Support for Podman
- [ ] Cloud-specific tests (AWS ECS, GKE)
- [ ] Internationalization
- [ ] Video tutorials

## 🧪 Testing Your Changes

Before submitting:

```bash
# Test the main toolkit
sudo ./toolkit/docker-analysis-toolkit.sh

# Test on clean system
docker system prune -af
sudo ./toolkit/docker-analysis-toolkit.sh

# Check for errors
bash -n ./toolkit/docker-analysis-toolkit.sh
```

## 📋 Pull Request Process

1. **Update documentation** - README, comments, etc.
2. **Test thoroughly** - Multiple runs, different scenarios
3. **Keep commits atomic** - One logical change per commit
4. **Write clear PR description**:
   - What does it do?
   - Why is it needed?
   - How was it tested?
5. **Link related issues** - Use "Fixes #123" syntax
6. **Be responsive** - Address review comments promptly

### PR Title Format

- `feat: Add GPU performance test`
- `fix: Handle missing strace gracefully`
- `docs: Update installation instructions`
- `test: Add CI pipeline for Ubuntu`

## 🤝 Code of Conduct

### Our Standards

- **Be respectful** - Treat everyone with respect
- **Be constructive** - Focus on improving the project
- **Be patient** - Maintainers review in their spare time
- **Be collaborative** - Help others when you can

### Unacceptable Behavior

- Harassment or discriminatory language
- Trolling or insulting comments
- Personal or political attacks
- Publishing others' private information

## 💬 Communication

- **GitHub Issues** - Bug reports, feature requests
- **Pull Requests** - Code contributions, discussions
- **Discussions** - General questions, ideas

## 🏆 Recognition

Contributors will be:
- Listed in README.md (optional)
- Mentioned in release notes
- Given credit in documentation

## 📞 Questions?

Not sure about something? Open an issue with the "question" label or start a discussion!

---

**Thank you for contributing to Docker Internals Guide!** 🎉

Your contributions help the community better understand and optimize Docker containers.