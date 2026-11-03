# ALPHA CodeGuard AI - Hackathon Demo Script (3-5 Minutes)

## Introduction (30 seconds)
**Speaker:** "Good [morning/afternoon], we're Team ALPHA presenting ALPHA CodeGuard AI - a professional multi-agent code review workspace powered by LangGraph orchestration."

**Action:** Show the dashboard/homepage of the application

## Problem Statement (30 seconds)
**Speaker:** "Developers spend countless hours manually reviewing code for bugs, security vulnerabilities, performance issues, and style problems. Traditional linters catch only basic issues, while human reviews are time-consuming and inconsistent."

## Solution - Multi-Agent Architecture (45 seconds)
**Speaker:** "ALPHA CodeGuard AI solves this with 5 specialized AI agents working together:"

**Show agent cards:**
1. **Bug Detection Agent** - Catches logical errors and runtime issues
2. **Security Analysis Agent** - Identifies vulnerabilities like SQL injection
3. **Performance Optimization Agent** - Finds inefficiencies
4. **Code Quality Agent** - Ensures maintainability
5. **Fix & Validation Agent** - Generates fixes with diffs and validates them

**Action:** Navigate to the Review Code page

## Live Demonstration (2 minutes)

### Step 1: Submit Vulnerable Code
**Action:** Upload or paste `demo/vulnerable_sample.py`

**Speaker:** "Let me demonstrate with a sample file containing common vulnerabilities..."

### Step 2: Show Agent Execution
**Action:** Show the Results page as agents process

**Speaker:** "Watch as all 5 agents analyze the code in parallel, coordinated by our LangGraph orchestrator. Each agent has a specific focus area."

### Step 3: Review Findings
**Action:** Walk through the findings

**Expected findings to highlight:**
- **Security Agent:** SQL injection in `get_user_data()`, command injection in `run_command()`, path traversal in `read_file()`, hardcoded credentials
- **Bug Detection Agent:** Division by zero in `divide_numbers()`
- **Performance Agent:** Inefficient O(n²) algorithm in `process_data()`
- **Code Quality Agent:** Style and maintainability issues

### Step 4: Show Fix Generation
**Action:** Click on a finding to show the fix suggestion

**Speaker:** "The Fix & Validation Agent generates proposed fixes with unified diffs and validates them using static analysis tools."

**Show:** Diff view showing before/after code

## Innovation & Impact (45 seconds)

**Speaker:**
- **Innovation:** "Our LangGraph orchestration enables true multi-agent collaboration with failure isolation - if one agent fails, others continue. We also provide actionable fixes with diffs, not just problem reports."
- **Impact:** "This saves developers hours of review time, catches critical security issues early, and improves code quality across teams. It works with 8+ languages and integrates seamlessly into development workflows."

## Conclusion (15 seconds)
**Speaker:** "ALPHA CodeGuard AI - comprehensive, intelligent, and actionable code review. Thank you!"

**Action:** Show final results dashboard with all findings

## Demo Tips
- Have the app running before starting
- If API key not configured, agents will show graceful degradation (empty findings) - still demonstrate the UI/flow
- Emphasize the multi-agent architecture and LangGraph orchestration
- Show the clean, professional UI
- Highlight the diff generation feature
