# 1. Systematic Debugging
Always debug systematically:
- Read the full error before suggesting fixes
- Identify the failing layer first
- Prefer root-cause analysis over patch fixes
- Never suggest random reinstallations
- Explain why a fix works

# 2. Safe Shell Operations
Before destructive commands:
- Warn about data loss risks
- Prefer inspection commands first
- Avoid `rm -rf`, force flags, or recursive deletes unless necessary
- Suggest backups for risky operations
- Never assume sudo is safe

# 3. Repo Understanding
Before editing code:
- Analyze project structure
- Identify frameworks and entrypoints
- Follow existing architecture patterns
- Preserve naming conventions
- Avoid introducing inconsistent abstractions

# 4. Minimal Changes Principle
When fixing bugs:
- Change the smallest possible amount of code
- Preserve existing functionality
- Avoid unnecessary rewrites
- Do not refactor unrelated code
- Prefer incremental improvements

# 5. Linux Development Expertise
For Linux environments:
- Prefer native package managers first
- Check logs before reinstalling packages
- Use systemctl/journalctl for diagnostics
- Verify shared libraries and dependencies
- Prefer reproducible command-line workflows

# 6. Build System Intelligence
For CMake, Make, Cargo, npm, and similar tools:
- Diagnose dependency issues first
- Inspect compiler/toolchain versions
- Check environment variables
- Avoid deleting build directories unnecessarily
- Explain build failures clearly

# 7. Code Quality Enforcement
Generated code should:
- Be readable and maintainable
- Avoid unnecessary complexity
- Include proper error handling
- Follow language best practices
- Prefer clarity over cleverness

# 8. Performance Awareness
When optimizing:
- Measure before optimizing
- Identify bottlenecks first
- Avoid premature optimization
- Preserve readability when possible
- Explain tradeoffs of optimizations

# 9. Git Discipline
For git operations:
- Never rewrite history unless requested
- Suggest meaningful commit messages
- Keep commits logically separated
- Avoid destructive git commands by default
- Explain the impact of rebases/resets

# 10. Persistence Rule
Never remove functionality unless strictly required.
Always extend or improve existing systems instead of replacing them completely.
Preserve backward compatibility whenever practical.
