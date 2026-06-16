# Requirements Document: SaaS Infrastructure Upgrade

## Introduction

This document formalizes the business requirements for hardening LeadGenAI's production SaaS infrastructure with enterprise-grade multi-tenancy and scalability patterns. The system currently operates in production with a solid foundation (Postgres, Redis, Docker, PgBouncer, observability), but requires additional capabilities to meet 2026 SaaS best practices for tenant isolation, progressive feature rollout, resilience against external service failures, API discoverability, operational visibility, and automated security policy enforcement.

All requirements target a FREE stack architecture with incremental deployment capability, additive changes (no breaking modifications), and automation-first principles.

## Glossary

- **System**: The LeadGenAI production SaaS platform
- **Feature_Flag_Service**: Redis-backed service managing runtime feature toggles
- **Circuit_Breaker**: Distributed fault tolerance mechanism preventing cascading failures
- **RLS_Manager**: Automated Row-Level Security policy generator and enforcer
- **Tenant**: An isolated customer instance within the multi-tenant system
- **External_Service**: Third-party APIs including LLM providers, Vobiz telephony, SMTP, Maps API, and Pollinations
- **Policy**: A Postgres Row-Level Security rule enforcing tenant data isolation
- **Health_Service**: Per-tenant metrics tracking and reporting system
- **OpenAPI_Spec**: Machine-readable API documentation auto-generated from FastAPI endpoints

## Requirements

### Requirement 1: Feature Flag Management

**User Story:** As a platform administrator, I want to control feature availability at runtime, so that I can progressively roll out new capabilities and quickly disable problematic features without code deployment.

#### Acceptance Criteria

1. THE Feature_Flag_Service SHALL store feature flags in Redis with JSON serialization
2. THE Feature_Flag_Service SHALL support four feature states: disabled, enabled for all tenants, enabled for percentage rollout, and enabled for specific tenants
3. WHEN a feature flag does not exist in Redis, THE Feature_Flag_Service SHALL return false as a safe default
4. WHEN Redis is unavailable, THE Feature_Flag_Service SHALL fail safe by returning false for all feature checks
5. WHEN a feature flag state is set to disabled, THE Feature_Flag_Service SHALL return false for all evaluation requests regardless of tenant or user context
6. WHEN a feature flag state is set to enabled for all tenants, THE Feature_Flag_Service SHALL return true for all evaluation requests
7. WHEN a feature flag state is set to enabled for specific tenants and the requesting tenant is in the enabled list, THE Feature_Flag_Service SHALL return true
8. WHEN a feature flag state is set to percentage rollout, THE Feature_Flag_Service SHALL use deterministic hashing to assign tenants to buckets and return true if the bucket is below the configured percentage
9. THE Feature_Flag_Service SHALL cache flag evaluations in Redis with a 60-second TTL
10. THE Feature_Flag_Service SHALL provide administrative operations to create, update, retrieve, list, and delete feature flags

### Requirement 2: Circuit Breaker Protection

**User Story:** As a platform operator, I want external service failures to be contained and fast-failing, so that one degraded service does not cascade and bring down the entire system.

#### Acceptance Criteria

1. THE Circuit_Breaker SHALL track failure rates separately for each configured external service
2. THE Circuit_Breaker SHALL store circuit state in Redis for coordination across multiple application workers
3. WHEN Redis is unavailable, THE Circuit_Breaker SHALL fall back to local in-memory state for single-worker operation
4. WHEN a circuit is in closed state and consecutive failures reach the configured failure threshold, THE Circuit_Breaker SHALL transition the circuit to open state
5. WHEN a circuit is in open state and a request is received, THE Circuit_Breaker SHALL execute the provided fallback function if available
6. WHEN a circuit is in open state and no fallback is provided, THE Circuit_Breaker SHALL raise a CircuitOpenError
7. WHEN a circuit is in open state and the configured reset timeout has elapsed, THE Circuit_Breaker SHALL transition the circuit to half-open state
8. WHEN a circuit is in half-open state and a request succeeds, THE Circuit_Breaker SHALL transition the circuit to closed state and reset the failure counter
9. WHEN a circuit is in half-open state and a request fails, THE Circuit_Breaker SHALL transition the circuit back to open state
10. THE Circuit_Breaker SHALL apply the configured timeout to all wrapped external service calls
11. THE Circuit_Breaker SHALL record metrics including failure count, last failure timestamp, and state transitions
12. THE Circuit_Breaker SHALL wrap all external service calls including LLM providers, Vobiz telephony, SMTP email, Maps API, and Pollinations image generation

### Requirement 3: Row-Level Security Automation

**User Story:** As a security engineer, I want tenant data isolation enforced at the database level with automatically generated policies, so that tenant data cannot leak across boundaries even if application code has bugs.

#### Acceptance Criteria

1. THE RLS_Manager SHALL scan the database schema to identify all tables containing tenant identifier columns (client_id, tenant_id, or user_id)
2. WHEN a table is identified with a tenant identifier column, THE RLS_Manager SHALL generate a Row-Level Security policy using Postgres current_setting for tenant context
3. THE RLS_Manager SHALL create policies that apply to all operations including SELECT, INSERT, UPDATE, and DELETE
4. THE RLS_Manager SHALL apply policies idempotently by dropping existing policies with the same name before creating new ones
5. WHEN applying a policy to a table, THE RLS_Manager SHALL enable Row-Level Security on the table
6. WHEN applying a policy to a table, THE RLS_Manager SHALL force Row-Level Security to ensure it applies to table owners and roles with BYPASSRLS
7. THE RLS_Manager SHALL verify that generated policy SQL is syntactically valid before applying it
8. THE RLS_Manager SHALL provide a verification function that confirms all expected policies are active on their tables
9. THE RLS_Manager SHALL provide a safe rollback mechanism to disable Row-Level Security on a table
10. THE RLS_Manager SHALL log all policy creation, modification, and deletion operations for audit purposes

### Requirement 4: Tenant Context Management

**User Story:** As a developer, I want tenant context automatically set for database queries, so that Row-Level Security policies correctly filter data without manual context setting in every query.

#### Acceptance Criteria

1. WHEN a request enters the system with tenant identification, THE System SHALL extract the tenant identifier from the request context
2. WHEN a database connection is established for a request, THE System SHALL execute a SET LOCAL statement to configure the app.current_tenant session variable
3. THE System SHALL use the configured tenant context for the lifetime of the database transaction
4. WHEN multiple queries execute within a single transaction, THE System SHALL maintain the same tenant context for all queries
5. WHEN a transaction completes, THE System SHALL allow the session-local tenant context to be cleared automatically

### Requirement 5: OpenAPI Specification Generation

**User Story:** As an API consumer, I want machine-readable API documentation automatically generated from the codebase, so that I can integrate with the platform using accurate and up-to-date specifications.

#### Acceptance Criteria

1. THE System SHALL automatically generate an OpenAPI specification from FastAPI route definitions
2. THE System SHALL expose the OpenAPI specification at a standard endpoint accessible to authenticated users
3. THE System SHALL include request schemas, response schemas, parameter definitions, and authentication requirements in the specification
4. WHEN API routes are added or modified, THE System SHALL reflect those changes in the generated specification without manual updates
5. THE System SHALL serve the OpenAPI specification in JSON format compatible with standard OpenAPI tooling

### Requirement 6: Per-Tenant Health Metrics

**User Story:** As a platform operator, I want health metrics tracked separately for each tenant, so that I can identify tenant-specific issues and provide enterprise-level monitoring dashboards.

#### Acceptance Criteria

1. THE Health_Service SHALL record total request count for each tenant
2. THE Health_Service SHALL record successful request count for each tenant
3. THE Health_Service SHALL record failed request count for each tenant
4. THE Health_Service SHALL calculate and store average latency in milliseconds for each tenant
5. THE Health_Service SHALL calculate and store 95th percentile latency in milliseconds for each tenant
6. THE Health_Service SHALL calculate error rate as a percentage for each tenant
7. THE Health_Service SHALL store the last error message for each tenant
8. THE Health_Service SHALL store the timestamp of the last request for each tenant
9. THE Health_Service SHALL track which features are enabled for each tenant
10. WHEN a request completes, THE System SHALL record the request outcome and latency to the Health_Service
11. THE Health_Service SHALL provide an endpoint to retrieve health metrics for a specific tenant
12. THE Health_Service SHALL provide an endpoint to retrieve health metrics for all tenants

### Requirement 7: Circuit Breaker Configuration

**User Story:** As a platform operator, I want to configure circuit breaker parameters per external service, so that I can tune failure thresholds and timeouts based on each service's reliability characteristics.

#### Acceptance Criteria

1. THE System SHALL support configuring failure threshold for each external service
2. THE System SHALL support configuring request timeout in seconds for each external service
3. THE System SHALL support configuring reset timeout for circuit recovery for each external service
4. THE System SHALL support configuring the number of test requests in half-open state for each external service
5. WHEN circuit breaker configuration is provided for a service, THE Circuit_Breaker SHALL use those values instead of defaults

### Requirement 8: Feature Flag Administrative Interface

**User Story:** As a platform administrator, I want a user interface to manage feature flags, so that I can toggle features without writing code or directly manipulating Redis.

#### Acceptance Criteria

1. THE System SHALL provide an administrative endpoint to create new feature flags with key, state, description, and metadata
2. THE System SHALL provide an administrative endpoint to update existing feature flag state and configuration
3. THE System SHALL provide an administrative endpoint to retrieve a specific feature flag by key
4. THE System SHALL provide an administrative endpoint to list all feature flags
5. THE System SHALL provide an administrative endpoint to delete a feature flag
6. WHEN updating a feature flag, THE System SHALL record the update timestamp
7. WHEN creating a feature flag, THE System SHALL record the creation timestamp

### Requirement 9: Graceful Degradation

**User Story:** As a platform user, I want the system to continue operating with reduced functionality when external services fail, so that core workflows remain available during outages.

#### Acceptance Criteria

1. WHEN an external service is unavailable and a fallback function is configured, THE Circuit_Breaker SHALL execute the fallback function and return its result
2. WHEN the LLM provider circuit is open, THE System SHALL use a cached or simplified response for non-critical operations
3. WHEN the telephony service circuit is open, THE System SHALL queue call requests with a status indicating service unavailability
4. WHEN the email service circuit is open, THE System SHALL queue email messages for later delivery
5. WHEN the Maps API circuit is open, THE System SHALL skip geocoding enhancement and proceed with available data

### Requirement 10: RLS Policy Validation

**User Story:** As a security engineer, I want to verify that Row-Level Security policies are correctly applied, so that I can ensure tenant isolation is actively enforced before deploying to production.

#### Acceptance Criteria

1. THE RLS_Manager SHALL query the Postgres information schema to check if Row-Level Security is enabled on each table
2. THE RLS_Manager SHALL query the pg_policies system catalog to verify that expected policies exist
3. THE RLS_Manager SHALL return a report mapping each table to its policy active status
4. WHEN a policy is expected but not found, THE RLS_Manager SHALL report the table as having inactive or missing policies
5. THE RLS_Manager SHALL provide a summary count of tables with active policies versus total tables requiring policies

### Requirement 11: Monitoring Integration

**User Story:** As a DevOps engineer, I want circuit breaker state and tenant health metrics exposed to monitoring systems, so that I can set up alerts and dashboards for operational visibility.

#### Acceptance Criteria

1. THE System SHALL expose circuit breaker state (closed, open, half-open) via a metrics endpoint for each configured service
2. THE System SHALL expose failure count and last failure timestamp for each circuit breaker via a metrics endpoint
3. THE System SHALL expose per-tenant request counts, success rates, and latency percentiles via a metrics endpoint
4. THE System SHALL format metrics in a structure compatible with Prometheus or similar time-series monitoring systems
5. WHEN the metrics endpoint is queried, THE System SHALL return current values without triggering expensive calculations

### Requirement 12: Deployment Safety

**User Story:** As a platform operator, I want infrastructure changes to be incremental and reversible, so that I can deploy each pattern independently and roll back if issues arise.

#### Acceptance Criteria

1. THE System SHALL support enabling feature flags without code deployment
2. THE System SHALL support enabling circuit breakers without code deployment
3. THE System SHALL support applying Row-Level Security policies without application downtime
4. WHEN Row-Level Security is enabled on a table, THE System SHALL continue to serve queries without interruption
5. THE System SHALL provide a mechanism to disable a specific RLS policy without removing it permanently
6. WHEN a circuit breaker configuration is updated, THE System SHALL apply the new configuration without restarting the application

### Requirement 13: Multi-Worker Coordination

**User Story:** As a platform operator, I want circuit breaker state and feature flags to be consistent across multiple application worker processes, so that the system behaves predictably under load.

#### Acceptance Criteria

1. WHEN multiple application workers are running, THE Feature_Flag_Service SHALL use Redis to share flag state across all workers
2. WHEN multiple application workers are running, THE Circuit_Breaker SHALL use Redis to share circuit state across all workers
3. WHEN a circuit breaker state transition occurs in one worker, THE Circuit_Breaker SHALL propagate the state change to all other workers via Redis
4. WHEN a feature flag is updated via one worker, THE Feature_Flag_Service SHALL make the updated value available to all other workers within the cache TTL period
5. THE System SHALL use atomic Redis operations (WATCH/MULTI) to prevent race conditions when updating shared state

### Requirement 14: Performance Optimization

**User Story:** As a developer, I want feature flag checks and circuit breaker operations to have minimal performance overhead, so that protecting external calls does not significantly increase latency.

#### Acceptance Criteria

1. THE Feature_Flag_Service SHALL complete a cached feature flag evaluation in less than 1 millisecond
2. THE Feature_Flag_Service SHALL complete an uncached feature flag evaluation (Redis lookup) in less than 10 milliseconds
3. THE Circuit_Breaker SHALL add less than 1 millisecond of overhead when the circuit is closed and the operation succeeds
4. THE Circuit_Breaker SHALL fail fast (within 1 millisecond) when the circuit is open
5. THE Health_Service SHALL record request metrics asynchronously without blocking the response to the client

### Requirement 15: Automated Policy Generation Validation

**User Story:** As a developer adding new tables, I want Row-Level Security policies automatically generated for any table with tenant columns, so that I don't need to manually create policies and risk missing tenant isolation.

#### Acceptance Criteria

1. WHEN a new table is created with a client_id, tenant_id, or user_id column, THE RLS_Manager SHALL detect the table in its next scan
2. WHEN the RLS_Manager generates a policy, THE System SHALL validate that the tenant identifier column exists in the table
3. WHEN the RLS_Manager generates a policy, THE System SHALL validate that the Postgres current_setting function is available
4. WHEN the RLS_Manager attempts to apply an invalid policy, THE System SHALL log the error and continue processing other tables without failing completely
5. THE RLS_Manager SHALL provide a dry-run mode that generates policy SQL without applying it to the database
