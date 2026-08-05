# Implementation Plan: Dashboard Assessment & Gap Analysis

## Overview

This plan implements a comprehensive dashboard assessment and gap analysis system for LeadGen AI. The system will audit customer and admin dashboards, identify gaps against competitive SaaS benchmarks, and generate actionable reports with MoSCoW prioritization.

**Implementation Language**: Python 3.12+

**Key Deliverables**:
- Feature inventory scanner for HTML/JavaScript dashboards
- Gap analysis engine with competitive benchmarking
- UX quality evaluator with WCAG checklist
- MoSCoW prioritization system
- Markdown and JSON report generators
- Report parser for CI/CD integration
- Regression detection (diff mode)

## Tasks

- [ ] 1. Set up project structure and core data models
  - Create directory structure (`app/platform/`, `data/`, `fixtures/`, `tests/`)
  - Define core data models using Python dataclasses (`FeatureStatus`, `FeatureCategory`, `Impact`, `Effort`, `MoSCoW`, `Severity` enums)
  - Implement data classes: `Feature`, `Gap`, `UXIssue`, `BacklogItem`, `AssessmentData`, `Evidence`
  - Create configuration for file paths and thresholds
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [ ] 2. Implement Dashboard Scanner Module
  - [ ] 2.1 Create HTML parser with BeautifulSoup4
    - Implement `scan_html(filepath)` to extract DOM structure
    - Identify UI component types (KPI cards, charts, tables, buttons, forms)
    - Extract element metadata (IDs, classes, text content)
    - Handle malformed HTML gracefully with error recovery
    - _Requirements: 1.1, 2.1, 3.1_

  - [ ] 2.2 Implement JavaScript API endpoint extraction
    - Implement `extract_api_calls(js_content)` using regex patterns
    - Find fetch/axios/XMLHttpRequest patterns in inline scripts
    - Extract endpoint paths, HTTP methods, and usage context
    - Parse query parameters and request bodies
    - _Requirements: 1.3, 2.1, 3.1_

  - [ ] 2.3 Build component categorizer
    - Implement `categorize_component(element)` classification logic
    - Distinguish: visualization (Chart.js), data_table (tbody), action (buttons/forms), navigation (nav/sidebar), real-time (WebSocket)
    - Use heuristics: element type, class names, parent structure
    - _Requirements: 1.4_

  - [ ] 2.4 Create feature status assessor
    - Implement `assess_status(feature)` to determine completeness
    - Check for broken links, empty elements, error messages
    - Classify as: complete (functional + connected), partial (UI present but no API), broken (errors/placeholders)
    - _Requirements: 1.5, 2.1_

  - [ ] 2.5 Generate feature inventory JSON output
    - Implement JSON schema writer for scanner output
    - Include: dashboard_name, scan_timestamp, file_metadata, features array, api_endpoints
    - Write to `data/feature_inventory.jsonl` (one JSON per line for versioning)
    - _Requirements: 1.6, 2.2, 3.2_

- [ ] 3. Build Feature Inventory Store
  - Create `FeatureInventory` data class with completeness metrics
  - Implement JSONL storage reader/writer
  - Calculate completeness score: `(complete_features / total_features) * 100`
  - Generate summary statistics: total, complete, partial, broken counts
  - _Requirements: 1.6, 2.4, 7.1_

- [ ] 4. Create Competitive Benchmarks Database
  - [ ] 4.1 Define competitive feature schema
    - Create JSON structure for competitor features
    - Fields: competitor name, feature_category, features array (name, description, prevalence 1-8, tier, examples)
    - _Requirements: 4.1, 4.2_

  - [ ] 4.2 Populate benchmark data for customer dashboard
    - Research and document 30+ competitive features from HubSpot, Mixpanel, Stripe, ChartMogul, Intercom, Salesforce
    - Categorize by prevalence: table_stakes (6+ competitors), standard (3-5), advanced (1-2)
    - Store in `data/competitive_features.json`
    - _Requirements: 4.1, 4.2, 10.1_

  - [ ] 4.3 Populate benchmark data for admin dashboard
    - Research features from Retool, Forest Admin, Django Admin, Zendesk, Grafana, Datadog
    - Focus on: search, bulk actions, filters, audit logs, analytics, alerts, RBAC
    - Add to `data/competitive_features.json` with admin category
    - _Requirements: 4.1, 4.2, 10.2_

- [ ] 5. Implement Gap Analysis Engine
  - [ ] 5.1 Create gap detection logic
    - Implement `identify_gaps(inventory, benchmarks)` comparison
    - Match features by name similarity and category
    - Create `Gap` records for missing competitive features
    - Calculate prevalence from benchmark data
    - _Requirements: 4.3, 4.4_

  - [ ] 5.2 Build impact scoring system
    - Implement `score_gap_impact(gap)` using prevalence and category
    - High impact: table_stakes (prevalence ≥6) OR blocks core workflow
    - Medium impact: standard features (prevalence 3-5)
    - Low impact: advanced features (prevalence ≤2)
    - _Requirements: 4.3, 6.2_

  - [ ] 5.3 Create effort estimation
    - Implement `estimate_effort(gap)` based on backend_dependency and complexity
    - High effort: new backend services, database changes, external integrations (5+ days)
    - Medium effort: new API endpoints, moderate frontend work (2-5 days)
    - Low effort: frontend-only, CSS/UI polish (<2 days)
    - _Requirements: 4.3, 6.2, 9.1, 9.2, 9.3_

  - [ ] 5.4 Calculate competitive parity score
    - Formula: `(implemented_features / total_competitive_features) * 100`
    - Generate score per dashboard (customer, admin)
    - _Requirements: 4.4, 10.3_

- [ ] 6. Build UX Quality Evaluator
  - [ ] 6.1 Create UX evaluation checklist
    - Define 10 evaluation dimensions: loading_states, error_states, empty_states, action_feedback, form_validation, touch_targets, contrast_ratios, focus_indicators, screen_reader_support, responsive_breakpoints
    - Create JSON checklist with criteria, severity levels, WCAG mappings
    - Store in `data/ux_checklist.json`
    - _Requirements: 5.1, 5.2_

  - [ ] 6.2 Implement checklist evaluator
    - Manual checklist runner that prompts for each criterion (semi-automated)
    - Check for: presence of loading spinners, error message elements, empty state content
    - Use heuristics: detect skeleton screens, toast notification divs, ARIA labels
    - _Requirements: 5.1, 5.2, 5.3_

  - [ ] 6.3 Create WCAG accessibility checker
    - Check contrast ratios programmatically (parse CSS, extract colors)
    - Detect ARIA labels and semantic HTML usage
    - Flag missing alt text, form labels, heading structure
    - Classify violations by WCAG level (A, AA, AAA)
    - _Requirements: 5.1, 5.2, 5.4_

  - [ ] 6.4 Generate UX issue records
    - Create `UXIssue` objects with: issue_name, dimension, severity, wcag_violation flag, user_impact, remediation
    - Calculate UX quality score: `((total_criteria - unresolved_issues) / total_criteria) * 100`
    - _Requirements: 5.4, 5.5_

- [ ] 7. Implement Scoring System
  - Create score calculation functions for all metrics
  - Feature completeness: `(complete_features / total_planned_features) * 100`
  - Competitive parity: `(implemented_competitive_features / total_competitive_features) * 100`
  - UX quality: `((total_criteria - unresolved_issues) / total_criteria) * 100`
  - Apply score thresholds: ≥90% Complete, 75-89% Mostly Complete, <75% Incomplete
  - _Requirements: 2.4, 3.4, 4.4, 5.5, 7.1, 7.2, 7.3_

- [ ] 8. Build MoSCoW Prioritization Engine
  - [ ] 8.1 Implement classification algorithm
    - Create `classify_moscow(gap, issues)` function
    - Must Have: WCAG critical violations OR prevalence ≥6 + high impact OR blocks core workflow
    - Should Have: prevalence ≥3 + high impact OR multiple user requests OR significant UX improvement
    - Could Have: prevalence ≤2 OR low effort + medium impact
    - Won't Have: requires backend redesign OR conflicts with product vision
    - _Requirements: 6.1, 6.2_

  - [ ] 8.2 Create priority rank calculator
    - Implement `calculate_priority_rank(item)` scoring formula
    - Rank = `moscow_score + (impact_score * 10) - (effort_score * 2)`
    - Weight MoSCoW highest (must_have=100, should_have=50, could_have=20, wont_have=0)
    - _Requirements: 6.2, 6.3_

  - [ ] 8.3 Generate prioritized backlog
    - Sort gaps and issues by priority rank (descending)
    - Create `BacklogItem` objects with estimated effort in days
    - Group by MoSCoW category
    - _Requirements: 6.3, 6.4_

  - [ ] 8.4 Build roadmap synthesizer
    - Aggregate must-have items into Sprint 1 (2 weeks / 10 days)
    - Distribute should-have items across Sprint 2-3
    - Generate effort estimates and completion target dates
    - _Requirements: 6.4_

- [ ] 9. Checkpoint - Verify core assessment logic
  - Run scanner on sample dashboard fixtures
  - Validate gap detection against test competitive features
  - Check MoSCoW classification for expected categorization
  - Ensure all scores calculate correctly
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. Implement Report Generator
  - [ ] 10.1 Create Markdown report template
    - Design Jinja2 template for `DASHBOARD_ASSESSMENT_REPORT.md`
    - Sections: Executive Summary, Current State Inventory, Gap Analysis, UX Quality Assessment, Prioritized Backlog, Roadmap to Completion, Backend Dependencies, Appendix
    - Include tables, formatted lists, and score summaries
    - _Requirements: 8.1, 8.2_

  - [ ] 10.2 Build JSON metrics exporter
    - Generate `dashboard_metrics.json` with structured data
    - Include: assessment_id, generated_at, dashboard_versions, scores dict, counts dict, backend_impact, estimated_effort
    - Ensure JSON is valid and well-formatted
    - _Requirements: 8.1, 8.4_

  - [ ] 10.3 Implement backend dependency analyzer
    - Create `identify_backend_dependencies(gaps)` function
    - Classify gaps: frontend-only, backend+frontend, backend-heavy
    - Propose API endpoints: path, method, purpose, complexity
    - Generate `BACKEND_DEPENDENCIES.md` report
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [ ] 10.4 Create report file writers
    - Implement `generate_reports(assessment_data)` orchestrator
    - Write Markdown report to `docs/DASHBOARD_ASSESSMENT_REPORT.md`
    - Write JSON metrics to `docs/dashboard_metrics.json`
    - Write backlog to `docs/PRIORITIZED_BACKLOG.md`
    - Handle file write errors gracefully
    - _Requirements: 8.1, 8.2, 8.3_

- [ ] 11. Build Assessment Report Parser
  - [ ] 11.1 Create Markdown parser
    - Implement `parse(report_path)` to extract structured data from Markdown
    - Parse sections using regex and Markdown structure
    - Extract: executive summary scores, feature tables, gap tables, issue lists, backlog items
    - _Requirements: 11.1, 11.2_

  - [ ] 11.2 Implement table parser
    - Create `parse_table(table_markdown)` to convert Markdown tables to list of dicts
    - Handle multi-line cells and escaped pipes
    - Validate table structure (headers, rows)
    - _Requirements: 11.2_

  - [ ] 11.3 Build pretty printer (inverse)
    - Implement `format(data)` to regenerate Markdown from structured data
    - Use same Jinja2 template as report generator
    - Enable round-trip: parse → print → parse should preserve structure
    - _Requirements: 11.3, 11.4_

  - [ ]* 11.4 Write round-trip validation test
    - Test: parse report → format to Markdown → parse again → compare structures
    - Assert all scores, gaps, issues, and backlog items are preserved
    - _Requirements: 11.4_

- [ ] 12. Implement Regression Detector
  - [ ] 12.1 Create assessment comparator
    - Implement `compare(baseline, current)` to diff two assessments
    - Detect regressions: features that changed from complete → broken or partial
    - Detect improvements: gaps that were closed
    - Calculate score deltas: percentage point changes in all metrics
    - _Requirements: 12.1, 12.2_

  - [ ] 12.2 Build regression report generator
    - Create `RegressionReport` data class
    - Fields: regressions list, improvements list, score_deltas dict
    - Generate Markdown diff report
    - _Requirements: 12.3, 12.4_

  - [ ] 12.3 Implement CI exit code logic
    - Exit 0: No significant regressions
    - Exit 1: Feature completeness dropped >5%
    - Exit 2: WCAG critical violations introduced
    - Exit 3: Must-have items increased
    - _Requirements: 12.5_

- [ ] 13. Create Main Assessment Orchestrator
  - Implement `DashboardAssessment` class as main entry point
  - Orchestrate: scan → inventory → gap analysis → UX evaluation → prioritization → report generation
  - Support CLI modes: `--mode=full`, `--mode=diff --baseline=id`, `--mode=ci`
  - Handle errors gracefully with rollback on critical failures
  - _Requirements: All requirements integrated_

- [ ] 14. Write Unit Tests
  - [ ]* 14.1 Test scanner module
    - Test: extract KPI cards from known HTML structure
    - Test: identify Chart.js visualizations
    - Test: find fetch API calls with various patterns
    - Test: handle malformed HTML gracefully

  - [ ]* 14.2 Test gap analysis
    - Test: identify missing features from competitive list
    - Test: calculate prevalence correctly
    - Test: score impact/effort accurately

  - [ ]* 14.3 Test scoring system
    - Test: feature completeness calculation (10/20 complete = 50%)
    - Test: UX quality score with various issue counts
    - Test: score thresholds classify correctly

  - [ ]* 14.4 Test MoSCoW prioritization
    - Test: WCAG critical → must_have
    - Test: high prevalence + high impact → must_have
    - Test: low prevalence → could_have
    - Test: priority rank calculation

  - [ ]* 14.5 Test report parser round-trip
    - Test: parse executive summary section
    - Test: extract gap tables
    - Test: parse UX issue lists
    - Test: handle missing sections gracefully
    - Test: round-trip parse → print → parse preserves structure

  - [ ]* 14.6 Test regression detector
    - Test: detect feature status change (complete → broken)
    - Test: identify closed gaps
    - Test: calculate score deltas
    - Test: generate correct exit codes

- [ ] 15. Write Integration Test
  - [ ]* 15.1 Test full assessment workflow
    - Create sample dashboard HTML files as fixtures
    - Create sample competitive features JSON
    - Run full assessment end-to-end
    - Verify reports are generated correctly
    - Validate JSON metrics match Markdown report

  - [ ]* 15.2 Test regression detection workflow
    - Run baseline assessment
    - Modify fixture to simulate feature breakage
    - Run current assessment
    - Verify regression is detected and score delta is negative

- [ ] 16. Checkpoint - Run complete test suite
  - Execute all unit tests and integration tests
  - Verify test coverage for critical paths
  - Fix any failing tests
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 17. Perform Manual Assessment
  - Run assessment on actual `frontend/customer_dashboard.html` and `frontend/admin_dashboard.html`
  - Verify all 26 customer dashboard features are cataloged
  - Verify all 34 admin dashboard features are cataloged
  - Review gap list against competitive products manually
  - Validate UX issue severity classifications
  - Check MoSCoW prioritization makes business sense
  - Ensure report is readable and actionable for stakeholders
  - _Requirements: All requirements validated_

- [ ] 18. Final Integration and Documentation
  - Create CLI entry point: `python -m app.platform.dashboard_assessment`
  - Add command-line argument parsing (argparse)
  - Write user documentation in `docs/DASHBOARD_ASSESSMENT_GUIDE.md`
  - Document API usage examples
  - Create sample competitive features database
  - Verify CI integration works correctly with exit codes
  - _Requirements: 12.5, all requirements complete_

## Notes

- **This is an AUDIT/DOCUMENTATION feature** - no code implementation of identified gaps, only analysis and reporting
- **No property-based testing** - this feature is not suitable for PBT (documentation tool, not algorithmic logic)
- Tasks marked with `*` are optional test-related tasks and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Testing strategy focuses on unit tests with examples rather than property-based tests
- Manual validation is critical for this audit tool - manual assessment task (#17) is essential

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1", "3", "4.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "4.2", "4.3", "6.1"] },
    { "id": 3, "tasks": ["2.4", "5.1", "6.2"] },
    { "id": 4, "tasks": ["2.5", "5.2", "5.3", "6.3"] },
    { "id": 5, "tasks": ["5.4", "6.4", "7"] },
    { "id": 6, "tasks": ["8.1", "8.2"] },
    { "id": 7, "tasks": ["8.3", "8.4", "10.1", "10.3", "11.1"] },
    { "id": 8, "tasks": ["10.2", "10.4", "11.2", "12.1"] },
    { "id": 9, "tasks": ["11.3", "12.2"] },
    { "id": 10, "tasks": ["11.4", "12.3", "13", "14.1", "14.2", "14.3"] },
    { "id": 11, "tasks": ["14.4", "14.5", "14.6", "15.1"] },
    { "id": 12, "tasks": ["15.2"] },
    { "id": 13, "tasks": ["17", "18"] }
  ]
}
```
