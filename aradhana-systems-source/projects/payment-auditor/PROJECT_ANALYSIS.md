# Project Architecture Analysis

## 1. Repository Structure Overview

The project is structured into several top-level directories, indicating a clear separation of concerns.

- `ai-prompts`: Contains AI prompt files, likely for internal tool usage or documentation.
- `audit`: Likely contains audit-related files or modules.
- `backend`: The core of the backend services, including API routes, business logic, and database interactions.
- `database`: Dedicated directory for database-related files, potentially migrations or initial data.
- `docs`: Documentation files for the project.
- `frontend`: The user interface application, built with modern web technologies.
- `parsers`: Contains various parsing logic, possibly for different data formats or external inputs.
- `reconciliation`: Modules specifically for the reconciliation engine.
- `sample_data`: Example data for testing or development.
- `scripts`: Utility scripts for various tasks (e.g., IMAP smoke test, Prime invoice probe).
- `tests`: Comprehensive test suite for the entire application.
- `.env.example`: Example environment variables.
- `.gitignore`: Specifies intentionally untracked files to ignore.
- `AI_RULES.md`: Guidelines or rules for AI interactions.
- `docker-compose.yml`: Defines multi-container Docker application.
- `PROJECT_ANALYSIS.md`: This analysis document.
- `README.md`: Project README file.
- `reconciliation_engine.py`: A Python module for reconciliation logic (also present in `backend`).
- `review_queue.py`: A Python module for managing review queues (also present in `backend`).
- `schemas.py`: Python module defining data schemas (also present in `backend`).

## 2. Key Component Identification

### Frontend
- **Framework:** React (TypeScript) based on `main.tsx`, `App.tsx`, and `vite.config.ts`.
- **Pages:**
    - `frontend/src/pages/DashboardPage.tsx`
    - `frontend/src/pages/EscalationsPage.tsx`
    - `frontend/src/pages/ReportsPage.tsx`
    - `frontend/src/pages/ReviewsPage.tsx`
- **Components:**
    - `frontend/src/components/EscalationTable.tsx`
    - `frontend/src/components/ReportSummaryCard.tsx`
    - `frontend/src/components/ReviewTable.tsx`
    - `frontend/src/components/StatCard.tsx`
- **Styling:** `App.css`, `Dashboard.css`, `index.css`.
- **API Client:** `frontend/src/api/client.ts` (likely for interacting with the backend API).
- **Mock API:** `frontend/src/mockApi.ts` (for development/testing).

### Backend
- **Core Application:** `backend/main.py` (FastAPI application entry point).
- **Authentication/Authorization:** `backend/auth.py`, `backend/rbac.py`.
- **Database:** `backend/database.py` (connection and session management), `backend/models.py` (SQLAlchemy models), `backend/erp_models.py` (ERP specific models).
- **API Routes:** Defined in `backend/api_routes.py`.
- **Services:**
    - `backend/audit_service.py`
    - `backend/bank_alert_normalizer.py`
    - `backend/bank_transaction_builder.py`
    - `backend/bank_transaction.py`
    - `backend/daily_reconciliation_runner.py`
    - `backend/daily_summary.py`
    - `backend/email_ingestion_pipeline.py`
    - `backend/email_parser.py`
    - `backend/imap_collector.py`
    - `backend/ornate_adapter.py`
    - `backend/owner_escalation.py`
    - `backend/owner_report.py`
    - `backend/prime_adapter.py`
    - `backend/reconciliation_engine.py` (also a top-level file)
    - `backend/reconciliation_orchestrator.py`
    - `backend/review_queue_manager.py`
    - `backend/review_queue.py` (also a top-level file)
    - `backend/sms_parser.py`
- **Prime Robot:** `backend/prime_robot/` directory containing:
    - `checkpoint_manager.py`
    - `daybook_navigator.py`
    - `idle_monitor.py`
    - `launcher.py`
    - `models.py`

### Routes
- `backend/api_routes.py`: Defines the various API endpoints.

### API Services
- **Audit Service:** `backend/audit_service.py`
- **Bank Transaction Services:** `backend/bank_transaction_builder.py`, `backend/bank_transaction.py`
- **Email Ingestion:** `backend/email_ingestion_pipeline.py`, `backend/email_parser.py`, `backend/imap_collector.py`
- **Reconciliation:** `backend/reconciliation_engine.py`, `backend/reconciliation_orchestrator.py`, `backend/daily_reconciliation_runner.py`
- **Review Queue:** `backend/review_queue.py`, `backend/review_queue_manager.py`
- **Reporting:** `backend/daily_summary.py`, `backend/owner_report.py`
- **ERP Adapters:** `backend/ornate_adapter.py`, `backend/prime_adapter.py`
- **Owner Escalation:** `backend/owner_escalation.py`

### Models
- `backend/models.py`: Defines core application database models.
- `backend/erp_models.py`: Defines models specific to ERP systems.
- `backend/schemas.py`: Pydantic schemas for data validation and serialization (used for API request/response).

### Existing Dashboard Pages
- `frontend/src/pages/DashboardPage.tsx`
- `frontend/src/pages/EscalationsPage.tsx`
- `frontend/src/pages/ReportsPage.tsx`
- `frontend/src/pages/ReviewsPage.tsx`

## 3. Project Architecture Summary

The Aradhana Payment Auditor project follows a client-server architecture, with a React-based frontend and a FastAPI-based Python backend.

- **Frontend (React/TypeScript):** Provides the user interface, including dashboards for various operational aspects like escalations, reports, and reviews. It interacts with the backend through a dedicated API client. Mock API is available for development.
- **Backend (FastAPI/Python):** Serves as the application's core logic. It handles:
    - **API Endpoints:** Defined in `api_routes.py`, exposing functionalities to the frontend.
    - **Authentication and Authorization:** Managed by `auth.py` and `rbac.py`.
    - **Database Interactions:** Handled via SQLAlchemy models in `models.py` and `erp_models.py`, with `database.py` managing connections.
    - **Business Logic:** Implemented across various service modules like `audit_service.py`, `reconciliation_orchestrator.py`, `review_queue_manager.py`, etc.
    - **Data Ingestion and Processing:** Includes modules for email ingestion (`email_ingestion_pipeline.py`, `email_parser.py`, `imap_collector.py`), SMS parsing (`sms_parser.py`), and bank transaction processing (`bank_transaction_builder.py`, `bank_alert_normalizer.py`).
    - **ERP Integration:** Adapters for external ERP systems like Ornate (`ornate_adapter.py`) and Prime (`prime_adapter.py`).
    - **Reconciliation Engine:** Core reconciliation logic is present in `reconciliation_engine.py` and orchestrated by `reconciliation_orchestrator.py` with daily runs handled by `daily_reconciliation_runner.py`.
    - **Prime Robot:** A dedicated set of modules (`prime_robot` directory) for interacting with the Prime ERP system, including checkpoint management, daybook navigation, and idle monitoring.
- **Data Models and Schemas:** SQLAlchemy models define the database structure, while Pydantic schemas (`schemas.py`) are used for API request/response validation and serialization, ensuring data consistency and clear API contracts.
- **Tests:** A comprehensive `tests` directory indicates a commitment to code quality and reliability.
- **Deployment:** `docker-compose.yml` suggests a Docker-based deployment strategy.

The overall architecture promotes modularity and separation of concerns, making it scalable and maintainable. The existence of multiple parsing and adapter modules highlights the system's role in integrating with various external financial systems and data sources.

## 4. Missing Components Analysis

Based on the existing file structure and identified components, here's an analysis of what might be missing for each feature:

### Prime ERP Extraction Robot
- **Existing:** `backend/prime_robot/` contains `checkpoint_manager.py`, `daybook_navigator.py`, `idle_monitor.py`, `launcher.py`, and `models.py`. This suggests the core robot functionality for interacting with Prime ERP is either present or in development. `backend/prime_adapter.py` also exists for Prime ERP integration.
- **Missing:**
    - **Configuration Management:** A robust way to configure the robot's extraction parameters (e.g., what data to extract, schedules, credentials) outside of code.
    - **Orchestration/Scheduling:** A dedicated mechanism to trigger, schedule, and manage multiple robot runs. This could be integrated with `daily_reconciliation_runner.py` or a separate scheduler.
    - **Error Handling & Reporting:** More explicit error handling specific to the robot's extraction process, with mechanisms to report failures to administrators.
    - **Data Validation/Transformation Pipelines:** Post-extraction processes to validate and transform the extracted ERP data before it's used by the reconciliation engine.

### Reconciliation Queue
- **Existing:** `backend/review_queue.py`, `backend/review_queue_manager.py` handle the backend logic. `frontend/src/pages/ReviewsPage.tsx` and `frontend/src/components/ReviewTable.tsx` provide a frontend interface.
- **Missing:**
    - **Advanced Filtering/Sorting:** More sophisticated options for users to filter and sort items in the review queue.
    - **Workflow Integration:** Clear definitions and implementations of the "workflow" for items in the queue (e.g., states like "pending," "reviewed," "escalated," "resolved").
    - **User Assignments:** Functionality to assign review queue items to specific users or teams.
    - **Audit Trail for Review Actions:** Logging of who performed what action on a review queue item and when.

### Audit Logs
- **Existing:** `backend/audit_service.py` indicates a service for auditing is present.
- **Missing:**
    - **Comprehensive Logging Strategy:** Clear definitions of what events should be audited across the application (e.g., user logins, data modifications, reconciliation results).
    - **Storage and Retrieval:** A dedicated mechanism for storing audit logs (e.g., a specific database table, a logging service) and an efficient way to retrieve them.
    - **Frontend Interface:** A dedicated dashboard or page in the frontend to view, search, and filter audit logs.
    - **Retention Policies:** Configuration for how long audit logs are retained.

### Prime Robot Monitoring
- **Existing:** `backend/prime_robot/idle_monitor.py` suggests some form of basic monitoring for the robot's idle state.
- **Missing:**
    - **Real-time Status Dashboard:** A frontend dashboard to display the real-time operational status of the Prime ERP extraction robot (running, idle, failed, last run, next run).
    - **Performance Metrics:** Collection and display of metrics like extraction duration, number of records processed, errors encountered.
    - **Alerting System:** Integration with an alerting system (e.g., email, Slack) to notify administrators of robot failures, prolonged idle states, or other critical events.
    - **Detailed Run Logs:** Easy access to detailed logs of each robot run for debugging and auditing purposes.

### Owner Escalation Dashboard
- **Existing:** `backend/owner_escalation.py`, `backend/owner_report.py` for backend logic, and `frontend/src/pages/EscalationsPage.tsx`, `frontend/src/components/EscalationTable.tsx` for the frontend.
- **Missing:**
    - **Escalation Rule Management:** A system to define and manage rules for when and how an escalation occurs (e.g., thresholds, conditions).
    - **Notification System:** Integration with email or other communication channels to automatically notify owners of new escalations.
    - **Escalation Lifecycle Management:** Features to track the status of an escalation (e.g., open, in progress, resolved), assign owners, and add comments/notes.
    - **Reporting on Escalation Trends:** Analytics and reporting features to identify patterns in escalations and improve processes.

## 5. Detailed Implementation Plan

This plan outlines the implementation strategy for the identified missing components, prioritizing an MVP approach for each to deliver incremental value.

### Phase 1: Foundational Enhancements & Core Features (MVP)

#### Prime ERP Extraction Robot
- **Goal:** Enable configurable and triggerable Prime ERP extraction with basic status tracking.
- **File Changes:**
    - `backend/prime_robot/models.py`: Add a new SQLAlchemy model `PrimeRobotConfig` for storing configuration (e.g., ERP credentials, extraction parameters, schedule metadata).
    - `backend/prime_robot/launcher.py`: Modify to load configuration from `PrimeRobotConfig` and include logic to update a `PrimeRobotRun` status (new model) after each run.
    - `backend/prime_robot/orchestrator.py` (NEW FILE): A new module to handle scheduling and triggering of robot runs based on `PrimeRobotConfig`. This will interact with `launcher.py`.
    - `backend/api_routes.py`: Add new endpoints:
        - `POST /prime-robot/config`: To create/update `PrimeRobotConfig`.
        - `GET /prime-robot/config`: To retrieve `PrimeRobotConfig`.
        - `POST /prime-robot/run`: To manually trigger a robot run.
        - `GET /prime-robot/status`: To get the latest run status.
    - `backend/schemas.py`: Add Pydantic schemas for `PrimeRobotConfig` and `PrimeRobotRun` for API validation.
    - `tests/test_prime_robot.py` (NEW FILE/UPDATE): Add tests for new API endpoints and orchestration logic.
- **Dependencies:** Existing `backend/prime_robot` modules, `backend/prime_adapter.py`, `backend/database.py`, `backend/models.py`.
- **Risks:**
    - Complexity of securely storing and retrieving ERP credentials.
    - Ensuring idempotence for scheduled runs.
    - Potential for data inconsistencies if extraction fails midway.

#### Reconciliation Queue
- **Goal:** Enhance review queue with advanced filtering, sorting, and basic workflow states.
- **File Changes:**
    - `backend/models.py`: Add a `status` field (e.g., enum: `pending`, `in_review`, `resolved`, `escalated`) to the `ReviewQueueItem` model.
    - `backend/review_queue_manager.py`: Update query methods to accept filtering and sorting parameters based on `status` and other fields. Add a method to update the `status` of a `ReviewQueueItem`.
    - `backend/api_routes.py`: Modify `GET /review-queue` to accept query parameters for filtering and sorting. Add a `PUT /review-queue/{item_id}/status` endpoint.
    - `backend/schemas.py`: Update `ReviewQueueItem` schema to include `status`. Add new request schemas for filtering/sorting.
    - `frontend/src/pages/ReviewsPage.tsx`: Implement UI for filtering (e.g., dropdown for status) and sorting table columns.
    - `frontend/src/components/ReviewTable.tsx`: Update to display `status` and handle sorting logic. Implement actions to update item status.
    - `tests/test_review_queue.py`: Add tests for new filtering, sorting, and status update functionalities.
- **Dependencies:** Existing `review_queue` modules, `frontend` components, `backend/database.py`.
- **Risks:**
    - Performance degradation with complex queries on large review queues without proper indexing.
    - Ensuring consistent state transitions for workflow.

#### Audit Logs
- **Goal:** Implement a basic audit logging mechanism with storage and a minimal frontend viewer.
- **File Changes:**
    - `backend/models.py`: Add a new SQLAlchemy model `AuditLog` with fields like `event_type`, `user_id`, `timestamp`, `details` (JSONB), `resource_id`, `resource_type`.
    - `backend/audit_service.py`: Enhance `AuditService` to include methods for recording various types of audit events throughout the application (e.g., user login, configuration changes, review item updates). Integrate this service into relevant backend operations.
    - `backend/api_routes.py`: Add new endpoints:
        - `GET /audit-logs`: To retrieve a paginated list of audit logs, with optional filters (e.g., by `event_type`, `user_id`, `timestamp_range`).
    - `backend/schemas.py`: Add Pydantic schema for `AuditLog` for API response.
    - `frontend/src/pages/AuditLogsPage.tsx` (NEW FILE): A new page to display audit logs in a table.
    - `frontend/src/components/AuditLogsTable.tsx` (NEW FILE): A new component to render the audit log table with basic filtering and pagination.
    - `frontend/src/api/client.ts`: Add new API client methods for audit logs.
    - `tests/test_audit_service.py`: Add tests for audit log creation and retrieval.
- **Dependencies:** `backend/database.py`, `backend/schemas.py`.
- **Risks:**
    - High volume of logs impacting database performance or storage costs.
    - Ensuring sensitive information is not logged inadvertently.

#### Prime Robot Monitoring
- **Goal:** Provide a basic real-time dashboard for Prime Robot status.
- **File Changes:**
    - `backend/models.py`: Introduce a `PrimeRobotRun` model to track individual robot execution instances (start time, end time, status, error details).
    - `backend/prime_robot/launcher.py`: Update to create and update `PrimeRobotRun` records during execution.
    - `backend/api_routes.py`: Add new endpoints:
        - `GET /prime-robot/latest-runs`: To retrieve the status of recent robot runs.
    - `backend/schemas.py`: Add Pydantic schema for `PrimeRobotRun`.
    - `frontend/src/pages/PrimeRobotMonitoringPage.tsx` (NEW FILE): A new page to display the status of Prime Robot runs.
    - `frontend/src/components/PrimeRobotStatusCard.tsx` (NEW FILE): A component to show the latest robot status (e.g., running, success, failed, last run time).
    - `frontend/src/api/client.ts`: Add new API client methods for robot monitoring.
    - `tests/test_prime_robot_monitoring.py` (NEW FILE): Add tests for status reporting.
- **Dependencies:** `backend/prime_robot` modules, `backend/database.py`.
- **Risks:**
    - Ensuring timely and accurate status updates from the robot.
    - Frontend polling frequency impacting backend load.

#### Owner Escalation Dashboard
- **Goal:** Enhance the escalation dashboard with lifecycle management and basic notification hooks.
- **File Changes:**
    - `backend/models.py`: Add a `status` field (e.g., `open`, `acknowledged`, `resolved`, `closed`) to the `OwnerEscalation` model. Add `assigned_to` field (user ID).
    - `backend/owner_escalation.py`: Update logic to manage escalation `status` transitions. Add methods for assigning escalations.
    - `backend/notification_service.py` (NEW FILE): A new service to handle sending notifications (e.g., email stubs) when an escalation is created or its status changes.
    - `backend/api_routes.py`: Add new endpoints:
        - `PUT /escalations/{escalation_id}/status`: To update escalation status.
        - `PUT /escalations/{escalation_id}/assign`: To assign an escalation to a user.
        - `POST /escalations/{escalation_id}/notify`: To trigger a notification.
    - `backend/schemas.py`: Update `OwnerEscalation` schema with `status` and `assigned_to`. Add request schemas for status updates and assignment.
    - `frontend/src/pages/EscalationsPage.tsx`: Implement UI for updating status, assigning escalations, and triggering notifications.
    - `frontend/src/components/EscalationTable.tsx`: Update to display `status` and `assigned_to` and provide actions for management.
    - `tests/test_owner_escalation.py`: Add tests for new status, assignment, and notification logic.
- **Dependencies:** `backend/owner_escalation.py`, `frontend` components, `backend/database.py`.
- **Risks:**
    - Complexity of integrating with external notification systems.
    - Defining clear and actionable escalation workflows.

### Phase 2: Advanced Features & Refinements (Future Work)

- **Prime ERP Extraction Robot:**
    - Implement a fully-fledged scheduler (e.g., using Celery Beat or APScheduler).
    - Develop a dedicated robot monitoring dashboard with historical run data and performance trends.
    - Implement robust data validation and transformation pipelines post-extraction.
- **Reconciliation Queue:**
    - Implement user assignment and role-based access for queue items.
    - Develop a comprehensive audit trail for all actions taken on review items.
    - Integrate with communication tools for notifications on new or updated items.
- **Audit Logs:**
    - Implement advanced search and analytics features for audit logs.
    - Integrate with an external logging solution (e.g., ELK stack).
    - Implement automated log archiving and retention policies.
- **Prime Robot Monitoring:**
    - Integrate with an external monitoring system (e.g., Prometheus, Grafana).
    - Implement anomaly detection for robot behavior.
    - Provide deep-dive analytics into robot performance and success rates.
- **Owner Escalation Dashboard:**
    - Develop a rule engine for automated escalation creation based on predefined criteria.
    - Integrate with more sophisticated communication and incident management platforms.
    - Implement reporting and analytics on escalation frequency, resolution times, and recurring issues.

### General Dependencies for all Phases

- **Backend:** FastAPI, SQLAlchemy, Pydantic, database (e.g., PostgreSQL).
- **Frontend:** React, TypeScript, React Router, state management library (e.g., React Query, Redux).
- **Tooling:** Docker, Poetry/Pip (for Python dependencies), npm/yarn (for Node.js dependencies).
- **CI/CD:** Existing CI/CD pipelines will need to be updated to include new tests and deployment steps.

### General Risks

- **API Versioning:** Ensuring backward compatibility for API changes, especially with new features.
- **Performance:** Potential performance bottlenecks as data volume and features grow.
- **Security:** Maintaining strong security practices, especially with credential management for ERP systems and access to audit logs.
- **Testing:** Ensuring comprehensive test coverage for all new features and integrations.
- **Deployment Complexity:** Increased complexity in deployment and maintenance with new services and configurations.